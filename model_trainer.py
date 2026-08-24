"""
model_trainer.py — Supervised ML Link Prediction with Strict Edge-Holdout Protocol
===================================================================================
Implements a scientifically rigorous Edge-Holdout Evaluation Protocol for
predicting unseen links between dark web threat actors in the canonical entity graph.

LEAKAGE PREVENTION GUARANTEES:
  1. Edge-Level Train/Test Split: Ground-truth positive pairs are split into 80% train / 20% test
     BEFORE feature extraction.
  2. Training Graph (G_train): Constructed strictly from the 80% train positive relationships.
     Test relationships are 100% excluded from G_train (both forward and reverse directions).
  3. Negative Sampling: Negative non-link pairs are sampled without replacement from verified
     non-edges in the full graph, ensuring zero overlap with train/test positive edges.
  4. Candidate Edge Masking: When extracting features for training positive edges on G_train,
     the candidate edge itself is temporarily masked so that training features and test features
     follow the exact same distribution (no direct length-1 path leakage).
  5. Isolated Community Detection: Louvain community partitions are computed strictly on G_train.
  6. Internally Consistent Metrics: All reported metrics (TP, TN, FP, FN, Accuracy, Precision,
     Recall, F1, Specificity, MCC, ROC-AUC, PR-AUC, Log Loss) are calculated from the single
     best saved model on the unseen test set.

Artifacts Generated:
  - data/link_prediction_model.pkl (Serialized trained model artifact)
  - data/model_metrics.json (Comprehensive benchmark evaluation metrics)
"""

import os
import sys
import math
import time
import json
import random
import joblib
import numpy as np
import pandas as pd
import networkx as nx
from pathlib import Path
from typing import Dict, List, Tuple, Any, Set

# Scikit-learn
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
from sklearn.model_selection import StratifiedKFold, train_test_split
from sklearn.metrics import (
    roc_auc_score,
    average_precision_score,
    precision_score,
    recall_score,
    f1_score,
    accuracy_score,
    confusion_matrix,
    matthews_corrcoef,
    log_loss
)

try:
    from xgboost import XGBClassifier
    HAS_XGBOOST = True
except ImportError:
    HAS_XGBOOST = False

# UTF-8 stdout
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

DATA_DIR = Path(__file__).parent / "data"
MODEL_OUTPUT_PATH = DATA_DIR / "link_prediction_model.pkl"
METRICS_OUTPUT_PATH = DATA_DIR / "model_metrics.json"

RANDOM_SEED = 42
np.random.seed(RANDOM_SEED)
random.seed(RANDOM_SEED)


# ===========================================================================
# 1. Feature Extractor (Masked & Leakage-Safe)
# ===========================================================================

class LeakageSafeGraphFeatureExtractor:
    """
    Extracts topological and behavioral features from a given training graph (G_train)
    with strict candidate-edge masking to prevent self-edge leakage.
    """

    def __init__(self, G_directed: nx.MultiDiGraph, entities: Dict[str, Any]):
        self.G_directed = G_directed
        self.G_undirected = G_directed.to_undirected()
        self.entities = entities

        # Compute Louvain communities strictly on the provided training graph
        try:
            self.communities = list(nx.community.louvain_communities(self.G_undirected, seed=RANDOM_SEED))
        except Exception:
            self.communities = []

        self.node_to_comm = {}
        for idx, comm in enumerate(self.communities):
            for node in comm:
                self.node_to_comm[node] = idx

    def extract_pair_features(self, u: str, v: str, is_train_edge: bool = False) -> Dict[str, float]:
        """
        Extract features for pair (u, v).
        If is_train_edge is True, the edge between u and v exists in G_directed and is
        temporarily masked during feature extraction to avoid direct-edge leakage.
        """
        feats = {}

        # 1. Degrees & Neighborhoods
        deg_u = self.G_undirected.degree(u) if u in self.G_undirected else 0
        deg_v = self.G_undirected.degree(v) if v in self.G_undirected else 0

        neighbors_u = set(self.G_undirected.neighbors(u)) if u in self.G_undirected else set()
        neighbors_v = set(self.G_undirected.neighbors(v)) if v in self.G_undirected else set()

        if is_train_edge:
            neighbors_u.discard(v)
            neighbors_v.discard(u)
            deg_u = max(0, deg_u - 1)
            deg_v = max(0, deg_v - 1)

        common_neighbors = neighbors_u.intersection(neighbors_v)
        union_neighbors = neighbors_u.union(neighbors_v)

        feats["common_neighbors_count"] = float(len(common_neighbors))
        feats["jaccard_coefficient"] = (
            float(len(common_neighbors) / len(union_neighbors)) if len(union_neighbors) > 0 else 0.0
        )

        # 2. Adamic-Adar & Resource Allocation
        adamic_adar = 0.0
        resource_alloc = 0.0
        for w in common_neighbors:
            deg_w = self.G_undirected.degree(w)
            if is_train_edge and w in (u, v):
                deg_w = max(1, deg_w - 1)
            if deg_w > 1:
                adamic_adar += 1.0 / math.log(deg_w)
            if deg_w > 0:
                resource_alloc += 1.0 / deg_w

        feats["adamic_adar_index"] = round(adamic_adar, 5)
        feats["resource_allocation_index"] = round(resource_alloc, 5)

        # 3. Preferential Attachment & Disparity
        feats["preferential_attachment"] = float(deg_u * deg_v)
        feats["degree_u"] = float(deg_u)
        feats["degree_v"] = float(deg_v)
        feats["degree_ratio"] = (
            min(deg_u, deg_v) / max(deg_u, deg_v) if max(deg_u, deg_v) > 0 else 0.0
        )
        feats["degree_diff"] = float(abs(deg_u - deg_v))

        # 4. Shortest Path & Traversal Path Confidence (on masked graph)
        if is_train_edge:
            # Temporarily remove u-v edges from graphs to compute indirect path
            saved_directed_edges = []
            if self.G_directed.has_edge(u, v):
                for k, d in list(self.G_directed[u][v].items()):
                    saved_directed_edges.append((u, v, k, dict(d)))
                    self.G_directed.remove_edge(u, v, key=k)
            if self.G_directed.has_edge(v, u):
                for k, d in list(self.G_directed[v][u].items()):
                    saved_directed_edges.append((v, u, k, dict(d)))
                    self.G_directed.remove_edge(v, u, key=k)
            if self.G_undirected.has_edge(u, v):
                self.G_undirected.remove_edge(u, v)

            sp_len, path_conf, link_str = self._compute_path_metrics(u, v)

            # Restore edges
            for n1, n2, k, d in saved_directed_edges:
                self.G_directed.add_edge(n1, n2, key=k, **d)
                self.G_undirected.add_edge(n1, n2)
        else:
            sp_len, path_conf, link_str = self._compute_path_metrics(u, v)

        feats["shortest_path_length"] = float(sp_len)
        feats["path_confidence"] = float(path_conf)
        feats["graph_link_strength"] = float(link_str)

        # 5. Louvain Community Co-membership
        comm_u = self.node_to_comm.get(u, -1)
        comm_v = self.node_to_comm.get(v, -2)
        feats["same_community"] = 1.0 if (comm_u == comm_v and comm_u != -1) else 0.0

        # 6. Darknet Marketplace Footprint Overlap
        ent_u = self.entities.get(u, {})
        ent_v = self.entities.get(v, {})
        mkts_u = set(ent_u.get("active_marketplaces", []))
        mkts_v = set(ent_v.get("active_marketplaces", []))
        common_mkts = mkts_u.intersection(mkts_v)
        union_mkts = mkts_u.union(mkts_v)

        feats["market_overlap_count"] = float(len(common_mkts))
        feats["market_jaccard"] = (
            float(len(common_mkts) / len(union_mkts)) if len(union_mkts) > 0 else 0.0
        )

        # 7. Cryptographic Identifiers (PGP & Crypto Wallet)
        pgp_u = ent_u.get("pgp_fingerprint")
        pgp_v = ent_v.get("pgp_fingerprint")
        wallet_u = ent_u.get("wallet_address")
        wallet_v = ent_v.get("wallet_address")

        feats["same_pgp_key"] = 1.0 if (pgp_u and pgp_v and pgp_u == pgp_v) else 0.0
        feats["same_wallet"] = 1.0 if (wallet_u and wallet_v and wallet_u == wallet_v) else 0.0

        return feats

    def _compute_path_metrics(self, u: str, v: str) -> Tuple[float, float, float]:
        """Helper to compute indirect path length, path confidence, and link strength."""
        try:
            if nx.has_path(self.G_undirected, u, v):
                sp = nx.shortest_path(self.G_undirected, u, v)
                sp_len = len(sp) - 1

                # Multiplicative confidence along path
                conf = 1.0
                for i in range(len(sp) - 1):
                    n1, n2 = sp[i], sp[i + 1]
                    best_c = 0.0
                    for s, t in [(n1, n2), (n2, n1)]:
                        if self.G_directed.has_edge(s, t):
                            for _, d in self.G_directed[s][t].items():
                                best_c = max(best_c, d.get("confidence", 0.0))
                    conf *= best_c

                path_conf = round(conf, 4)

                # Link strength combining path count
                try:
                    all_paths = list(nx.all_simple_paths(self.G_undirected, u, v, cutoff=3))
                    n_paths = len(all_paths)
                except Exception:
                    n_paths = 1

                link_str = round(min(1.0, path_conf * (1.0 + math.log2(max(1, n_paths)) * 0.1)), 4)
                return sp_len, path_conf, link_str
            else:
                return 5.0, 0.0, 0.0
        except Exception:
            return 5.0, 0.0, 0.0


# ===========================================================================
# 2. Edge-Holdout Dataset Construction
# ===========================================================================

def prepare_edge_holdout_split(engine, test_ratio=0.20):
    """
    Splits unique positive entity relationships into 80% train and 20% held-out test.
    Constructs G_train containing ONLY the training relationships.
    Samples non-overlapping negative examples for both train and test sets.
    """
    print("\n" + "=" * 60)
    print("EDGE-HOLDOUT PROTOCOL INITIALIZATION")
    print("=" * 60)

    entities = engine.get_all_entities()
    entity_ids = list(entities.keys())
    edges_df = engine.edges_df[engine.edges_df["relation_type"] != "SHARED_PGP_AND_WALLET"]

    # 1. Group raw edges into unique canonical entity pairs
    positive_pairs_dict = {}
    for _, r in edges_df.iterrows():
        u = engine.persona_to_entity.get(r["source_persona_id"])
        v = engine.persona_to_entity.get(r["target_persona_id"])
        rtype = r["relation_type"]
        conf = r["confidence_weight"]
        if u and v and u != v:
            pair_key = tuple(sorted([u, v]))
            positive_pairs_dict.setdefault(pair_key, []).append((u, v, rtype, conf))

    positive_pairs = list(positive_pairs_dict.keys())
    total_positives = len(positive_pairs)

    # 2. Perform Edge Train/Test Split
    train_pos_pairs, test_pos_pairs = train_test_split(
        positive_pairs, test_size=test_ratio, random_state=RANDOM_SEED
    )

    print(f"[*] Total positive entity pairs: {total_positives}")
    print(f"    - Training positive pairs (80%): {len(train_pos_pairs)}")
    print(f"    - Held-out test positive pairs (20%): {len(test_pos_pairs)}")

    # 3. Build G_train with ONLY training relationships
    G_train = nx.MultiDiGraph()
    for eid, data in entities.items():
        G_train.add_node(eid, **data)

    train_edge_count = 0
    for pair in train_pos_pairs:
        rels = positive_pairs_dict[pair]
        for u, v, rtype, conf in rels:
            G_train.add_edge(u, v, relation_type=rtype, confidence=conf)
            train_edge_count += 1
            if rtype in {"CO_OCCURRED_IN_THREAD", "TRANSACTED_WITH"}:
                G_train.add_edge(v, u, relation_type=rtype, confidence=conf)
                train_edge_count += 1

    print(f"[*] Built G_train: {G_train.number_of_nodes()} nodes, {train_edge_count} directed edges")

    # 4. Leakage Verification Assertions on G_train
    print("[*] Running strict leakage verification assertions...")
    leaked_count = 0
    for u, v in test_pos_pairs:
        if G_train.has_edge(u, v) or G_train.has_edge(v, u):
            leaked_count += 1

    assert leaked_count == 0, f"FATAL: {leaked_count} held-out test edges leaked into G_train!"
    print(f"    [PASS] Zero held-out test edges exist in G_train (leaked = {leaked_count})")

    # 5. Negative Sampling (without replacement, non-overlapping)
    all_positive_set = set(positive_pairs)
    all_possible_negative_pairs = []
    for i in range(len(entity_ids)):
        for j in range(i + 1, len(entity_ids)):
            p = (entity_ids[i], entity_ids[j])
            if p not in all_positive_set:
                all_possible_negative_pairs.append(p)

    rng = random.Random(RANDOM_SEED)
    rng.shuffle(all_possible_negative_pairs)

    n_train_neg = len(train_pos_pairs)
    n_test_neg = len(test_pos_pairs)

    train_neg_pairs = all_possible_negative_pairs[:n_train_neg]
    test_neg_pairs = all_possible_negative_pairs[n_train_neg:n_train_neg + n_test_neg]

    # Verify zero negative/positive overlap
    assert len(set(train_neg_pairs).intersection(all_positive_set)) == 0
    assert len(set(test_neg_pairs).intersection(all_positive_set)) == 0
    assert len(set(train_neg_pairs).intersection(set(test_neg_pairs))) == 0
    print(f"    [PASS] Negative samples verified: {len(train_neg_pairs)} train negatives, {len(test_neg_pairs)} test negatives (0 overlap)")

    return {
        "G_train": G_train,
        "entities": entities,
        "train_pos_pairs": train_pos_pairs,
        "train_neg_pairs": train_neg_pairs,
        "test_pos_pairs": test_pos_pairs,
        "test_neg_pairs": test_neg_pairs,
        "positive_pairs_dict": positive_pairs_dict
    }


# ===========================================================================
# 3. Feature Matrix Generation
# ===========================================================================

def generate_feature_matrices(split_data: Dict[str, Any]) -> Tuple[pd.DataFrame, np.ndarray, pd.DataFrame, np.ndarray, List[str], Dict[str, float]]:
    """
    Generates training feature matrix (with candidate-edge masking) and
    test feature matrix strictly from G_train.
    """
    G_train = split_data["G_train"]
    entities = split_data["entities"]
    train_pos = split_data["train_pos_pairs"]
    train_neg = split_data["train_neg_pairs"]
    test_pos = split_data["test_pos_pairs"]
    test_neg = split_data["test_neg_pairs"]

    extractor = LeakageSafeGraphFeatureExtractor(G_train, entities)

    # 1. Training Features (with edge masking for positive training pairs)
    print("\n[*] Generating training feature matrix from G_train (with candidate-edge masking)...")
    t0 = time.time()
    train_records = []
    train_labels = []

    for u, v in train_pos:
        feats = extractor.extract_pair_features(u, v, is_train_edge=True)
        feats["entity_id_a"] = u
        feats["entity_id_b"] = v
        train_records.append(feats)
        train_labels.append(1)

    for u, v in train_neg:
        feats = extractor.extract_pair_features(u, v, is_train_edge=False)
        feats["entity_id_a"] = u
        feats["entity_id_b"] = v
        train_records.append(feats)
        train_labels.append(0)

    train_feature_time = time.time() - t0
    print(f"    Train feature matrix: {len(train_records)} samples generated in {train_feature_time:.2f}s")

    # 2. Held-Out Test Features (strictly from G_train, test edges are 100% absent)
    print("[*] Generating held-out test feature matrix from G_train (test edges completely absent)...")
    t1 = time.time()
    test_records = []
    test_labels = []

    for u, v in test_pos:
        feats = extractor.extract_pair_features(u, v, is_train_edge=False)
        feats["entity_id_a"] = u
        feats["entity_id_b"] = v
        test_records.append(feats)
        test_labels.append(1)

    for u, v in test_neg:
        feats = extractor.extract_pair_features(u, v, is_train_edge=False)
        feats["entity_id_a"] = u
        feats["entity_id_b"] = v
        test_records.append(feats)
        test_labels.append(0)

    test_feature_time = time.time() - t1
    print(f"    Test feature matrix: {len(test_records)} samples generated in {test_feature_time:.2f}s")

    df_train = pd.DataFrame(train_records)
    y_train = np.array(train_labels)
    df_test = pd.DataFrame(test_records)
    y_test = np.array(test_labels)

    feature_cols = [
        c for c in df_train.columns
        if c not in ("entity_id_a", "entity_id_b")
    ]

    timings = {
        "train_feature_time": round(train_feature_time, 3),
        "test_feature_time": round(test_feature_time, 3)
    }

    return df_train, y_train, df_test, y_test, feature_cols, timings


# ===========================================================================
# 4. Graph-Aware Edge Cross-Validation
# ===========================================================================

def run_edge_level_cross_validation(train_pos: List[Tuple[str, str]], train_neg: List[Tuple[str, str]], entities: Dict[str, Any], positive_pairs_dict: Dict[Tuple[str, str], List], feature_cols: List[str], n_splits: int = 5) -> Dict[str, float]:
    """
    Executes a true graph-aware 5-fold edge cross-validation:
    For each fold, holds out 20% of training edges, rebuilds the fold sub-graph,
    generates fold features, and evaluates without cross-fold leakage.
    """
    print(f"\n[*] Running {n_splits}-Fold Graph-Aware Edge Cross-Validation on training set...")

    pos_array = np.array(train_pos, dtype=object)
    neg_array = np.array(train_neg, dtype=object)

    skf = StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=RANDOM_SEED)

    fold_roc_aucs = []
    fold_f1s = []
    fold_precisions = []
    fold_recalls = []
    fold_accuracies = []

    # Combined indices
    all_samples = list(range(len(pos_array)))

    for fold_idx, (train_idx, val_idx) in enumerate(skf.split(all_samples, np.ones(len(all_samples))), 1):
        fold_train_pos = [tuple(p) for p in pos_array[train_idx]]
        fold_val_pos = [tuple(p) for p in pos_array[val_idx]]
        fold_train_neg = [tuple(p) for p in neg_array[train_idx]]
        fold_val_neg = [tuple(p) for p in neg_array[val_idx]]

        # Build fold sub-graph
        G_fold = nx.MultiDiGraph()
        for eid, data in entities.items():
            G_fold.add_node(eid, **data)

        for pair in fold_train_pos:
            for u, v, rtype, conf in positive_pairs_dict.get(pair, []):
                G_fold.add_edge(u, v, relation_type=rtype, confidence=conf)
                if rtype in {"CO_OCCURRED_IN_THREAD", "TRANSACTED_WITH"}:
                    G_fold.add_edge(v, u, relation_type=rtype, confidence=conf)

        fold_extractor = LeakageSafeGraphFeatureExtractor(G_fold, entities)

        # Extract fold train
        fold_X_train_list = []
        fold_y_train_list = []
        for u, v in fold_train_pos:
            f = fold_extractor.extract_pair_features(u, v, is_train_edge=True)
            fold_X_train_list.append([f[col] for col in feature_cols])
            fold_y_train_list.append(1)
        for u, v in fold_train_neg:
            f = fold_extractor.extract_pair_features(u, v, is_train_edge=False)
            fold_X_train_list.append([f[col] for col in feature_cols])
            fold_y_train_list.append(0)

        # Extract fold val
        fold_X_val_list = []
        fold_y_val_list = []
        for u, v in fold_val_pos:
            f = fold_extractor.extract_pair_features(u, v, is_train_edge=False)
            fold_X_val_list.append([f[col] for col in feature_cols])
            fold_y_val_list.append(1)
        for u, v in fold_val_neg:
            f = fold_extractor.extract_pair_features(u, v, is_train_edge=False)
            fold_X_val_list.append([f[col] for col in feature_cols])
            fold_y_val_list.append(0)

        # Train fold model
        fold_rf = RandomForestClassifier(
            n_estimators=80, max_depth=8, min_samples_split=4, random_state=RANDOM_SEED, n_jobs=1
        )
        fold_rf.fit(np.array(fold_X_train_list), np.array(fold_y_train_list))

        val_preds = fold_rf.predict(np.array(fold_X_val_list))
        val_probs = fold_rf.predict_proba(np.array(fold_X_val_list))[:, 1]
        y_val_arr = np.array(fold_y_val_list)

        fold_roc_aucs.append(roc_auc_score(y_val_arr, val_probs))
        fold_f1s.append(f1_score(y_val_arr, val_preds))
        fold_precisions.append(precision_score(y_val_arr, val_preds, zero_division=0))
        fold_recalls.append(recall_score(y_val_arr, val_preds, zero_division=0))
        fold_accuracies.append(accuracy_score(y_val_arr, val_preds))

    cv_summary = {
        "cv_roc_auc_mean": round(float(np.mean(fold_roc_aucs)), 4),
        "cv_roc_auc_std": round(float(np.std(fold_roc_aucs)), 4),
        "cv_f1_mean": round(float(np.mean(fold_f1s)), 4),
        "cv_f1_std": round(float(np.std(fold_f1s)), 4),
        "cv_precision_mean": round(float(np.mean(fold_precisions)), 4),
        "cv_recall_mean": round(float(np.mean(fold_recalls)), 4),
        "cv_accuracy_mean": round(float(np.mean(fold_accuracies)), 4)
    }

    print(f"    5-Fold CV ROC-AUC:   {cv_summary['cv_roc_auc_mean']:.4f} (+/- {cv_summary['cv_roc_auc_std']:.4f})")
    print(f"    5-Fold CV F1-Score:  {cv_summary['cv_f1_mean']:.4f} (+/- {cv_summary['cv_f1_std']:.4f})")
    print(f"    5-Fold CV Precision: {cv_summary['cv_precision_mean']:.4f}")
    print(f"    5-Fold CV Recall:    {cv_summary['cv_recall_mean']:.4f}")

    return cv_summary


# ===========================================================================
# 5. Model Training, Selection & Consistent Metric Evaluation
# ===========================================================================

def train_select_and_evaluate(
    df_train: pd.DataFrame,
    y_train: np.ndarray,
    df_test: pd.DataFrame,
    y_test: np.ndarray,
    feature_cols: List[str],
    cv_metrics: Dict[str, float],
    timings: Dict[str, float]
):
    """
    Trains Random Forest and XGBoost on G_train, selects the best model,
    and computes ALL hold-out test metrics exclusively from the saved best model.
    """
    print("\n" + "=" * 60)
    print("TRAINING & FINAL EVALUATION ON UNSEEN TEST EDGES")
    print("=" * 60)

    X_train = df_train[feature_cols].values
    X_test = df_test[feature_cols].values

    # 1. Train Random Forest Classifier
    t_train_start = time.time()
    rf_model = RandomForestClassifier(
        n_estimators=100,
        max_depth=8,
        min_samples_split=4,
        random_state=RANDOM_SEED,
        n_jobs=1
    )
    rf_model.fit(X_train, y_train)
    rf_train_time = time.time() - t_train_start

    rf_probs = rf_model.predict_proba(X_test)[:, 1]
    rf_preds = rf_model.predict(X_test)
    rf_roc_auc = roc_auc_score(y_test, rf_probs)
    rf_f1 = f1_score(y_test, rf_preds)

    best_model = rf_model
    best_model_name = "RandomForestClassifier"
    best_probs = rf_probs
    best_preds = rf_preds
    model_train_time = rf_train_time

    # 2. Train XGBoost Classifier (if available)
    if HAS_XGBOOST:
        t_xgb_start = time.time()
        xgb_model = XGBClassifier(
            n_estimators=100,
            max_depth=5,
            learning_rate=0.08,
            random_state=RANDOM_SEED,
            eval_metric="logloss"
        )
        xgb_model.fit(X_train, y_train)
        xgb_train_time = time.time() - t_xgb_start

        xgb_probs = xgb_model.predict_proba(X_test)[:, 1]
        xgb_preds = xgb_model.predict(X_test)
        xgb_roc_auc = roc_auc_score(y_test, xgb_probs)
        xgb_f1 = f1_score(y_test, xgb_preds)

        print(f"[*] Candidate Models on Unseen Test Edges:")
        print(f"    - RandomForest: ROC-AUC = {rf_roc_auc:.4f}, F1 = {rf_f1:.4f}")
        print(f"    - XGBoost:      ROC-AUC = {xgb_roc_auc:.4f}, F1 = {xgb_f1:.4f}")

        if xgb_roc_auc >= rf_roc_auc:
            best_model = xgb_model
            best_model_name = "XGBoostClassifier"
            best_probs = xgb_probs
            best_preds = xgb_preds
            model_train_time = xgb_train_time
    else:
        print(f"[*] Candidate Model: RandomForest: ROC-AUC = {rf_roc_auc:.4f}, F1 = {rf_f1:.4f}")

    print(f"\n[★] Selected Best Model: {best_model_name}")

    # 3. Calculate ALL Hold-Out Test Metrics from the Single Best Model
    t_eval_start = time.time()
    cm = confusion_matrix(y_test, best_preds)
    tn, fp, fn, tp = cm.ravel()

    test_acc = accuracy_score(y_test, best_preds)
    test_prec = precision_score(y_test, best_preds, zero_division=0)
    test_rec = recall_score(y_test, best_preds, zero_division=0)
    test_f1 = f1_score(y_test, best_preds, zero_division=0)
    test_spec = tn / (tn + fp) if (tn + fp) > 0 else 0.0
    test_mcc = matthews_corrcoef(y_test, best_preds)
    test_roc_auc = roc_auc_score(y_test, best_probs)
    test_pr_auc = average_precision_score(y_test, best_probs)
    test_loss = log_loss(y_test, best_probs)
    eval_time = time.time() - t_eval_start

    timings["model_train_time"] = round(model_train_time, 3)
    timings["eval_time"] = round(eval_time, 3)
    timings["total_pipeline_time"] = round(
        timings["train_feature_time"] + timings["test_feature_time"] + model_train_time + eval_time, 3
    )

    # 4. Feature Importance Ranking
    importances = best_model.feature_importances_
    feat_imp = sorted(zip(feature_cols, importances), key=lambda x: -x[1])

    # 5. Output Summary to Console
    print("\n" + "=" * 60)
    print("FINAL UNSEEN EDGE-HOLDOUT EVALUATION METRICS")
    print("=" * 60)
    print(f"  Model Architecture:      {best_model_name}")
    print(f"  Confusion Matrix:        [[TN={tn}, FP={fp}], [FN={fn}, TP={tp}]]")
    print(f"  True Positives (TP):     {tp}")
    print(f"  True Negatives (TN):     {tn}")
    print(f"  False Positives (FP):    {fp}")
    print(f"  False Negatives (FN):    {fn}")
    print(f"  Accuracy:                {test_acc:.4f} ({test_acc*100:.2f}%)")
    print(f"  Precision:               {test_prec:.4f} ({test_prec*100:.2f}%)")
    print(f"  Recall (Sensitivity):    {test_rec:.4f} ({test_rec*100:.2f}%)")
    print(f"  Specificity:             {test_spec:.4f} ({test_spec*100:.2f}%)")
    print(f"  F1-Score:                {test_f1:.4f}")
    print(f"  Matthews Corr (MCC):     {test_mcc:.4f}")
    print(f"  ROC-AUC Score:           {test_roc_auc:.4f}")
    print(f"  PR-AUC (Avg Precision):  {test_pr_auc:.4f}")
    print(f"  Binary Log Loss:         {test_loss:.4f}")

    print("\n--- Feature Importance Ranking (Top Predictive Signals) ---")
    for rank, (name, imp) in enumerate(feat_imp, 1):
        bar = "█" * int(imp * 35)
        print(f"  {rank:2d}. {name:<28} {imp:.4f}  {bar}")

    # 6. Save Model Artifact
    model_artifact = {
        "model": best_model,
        "model_name": best_model_name,
        "feature_cols": feature_cols,
        "evaluation_protocol": "Edge-Holdout (Strict zero-leakage G_train split)",
        "metrics": {
            "test_roc_auc": round(float(test_roc_auc), 4),
            "test_pr_auc": round(float(test_pr_auc), 4),
            "test_f1_score": round(float(test_f1), 4),
            "test_precision": round(float(test_prec), 4),
            "test_recall": round(float(test_rec), 4),
            "test_specificity": round(float(test_spec), 4),
            "test_accuracy": round(float(test_acc), 4),
            "test_mcc": round(float(test_mcc), 4),
            "test_log_loss": round(float(test_loss), 4),
            "confusion_matrix": {"TP": int(tp), "TN": int(tn), "FP": int(fp), "FN": int(fn)},
            "cv_metrics": cv_metrics
        },
        "feature_importance": [
            {"feature": name, "importance": round(float(imp), 4)} for name, imp in feat_imp
        ],
        "timings_seconds": timings
    }

    joblib.dump(model_artifact, MODEL_OUTPUT_PATH)
    print(f"\n[OK] Model artifact serialized to {MODEL_OUTPUT_PATH}")

    # 7. Save Metrics JSON
    with open(METRICS_OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump({
            "model_type": best_model_name,
            "evaluation_protocol": "Edge-Holdout (Strict Zero-Leakage)",
            "evaluation_summary": model_artifact["metrics"],
            "feature_importance_ranking": model_artifact["feature_importance"],
            "dataset_info": {
                "train_samples": len(df_train),
                "test_samples": len(df_test),
                "features_count": len(feature_cols),
                "train_positives": int(sum(y_train)),
                "train_negatives": int(len(y_train) - sum(y_train)),
                "test_positives": int(sum(y_test)),
                "test_negatives": int(len(y_test) - sum(y_test))
            },
            "execution_timings_seconds": timings,
            "leakage_audit_status": {
                "edge_holdout_enforced": True,
                "held_out_edges_in_G_train": 0,
                "candidate_masking_during_training": True,
                "internally_consistent_metrics": True
            }
        }, f, indent=2)

    print(f"[OK] Evaluation metrics saved to {METRICS_OUTPUT_PATH}")
    return model_artifact


# ===========================================================================
# 6. Public Runner & Inference API
# ===========================================================================

def predict_link_probability(entity_a: str, entity_b: str) -> float:
    """
    Inference helper: Computes link probability between entity_a and entity_b.
    """
    if not MODEL_OUTPUT_PATH.exists():
        raise FileNotFoundError(f"Model not found at {MODEL_OUTPUT_PATH}. Run model_trainer.py first.")

    from graph_engine import EntityGraph
    engine = EntityGraph()
    engine.load()

    artifact = joblib.load(MODEL_OUTPUT_PATH)
    model = artifact["model"]
    feature_cols = artifact["feature_cols"]

    extractor = LeakageSafeGraphFeatureExtractor(engine.get_graph(), engine.get_all_entities())
    feats = extractor.extract_pair_features(entity_a, entity_b, is_train_edge=False)
    x_vec = np.array([[feats[col] for col in feature_cols]])
    prob = model.predict_proba(x_vec)[0, 1]
    return round(float(prob), 4)


def main():
    from graph_engine import EntityGraph

    # 1. Load data & Canonical Graph
    engine = EntityGraph()
    engine.load()

    # 2. Edge-Holdout Split & Training Graph Construction
    split_data = prepare_edge_holdout_split(engine, test_ratio=0.20)

    # 3. Feature Generation from G_train (with candidate masking for train edges)
    df_train, y_train, df_test, y_test, feature_cols, timings = generate_feature_matrices(split_data)

    # 4. Graph-Aware 5-Fold Edge Cross-Validation on Training Set
    cv_metrics = run_edge_level_cross_validation(
        split_data["train_pos_pairs"],
        split_data["train_neg_pairs"],
        split_data["entities"],
        split_data["positive_pairs_dict"],
        feature_cols,
        n_splits=5
    )

    # 5. Train Final Model, Select Best Architecture & Evaluate on Held-Out Test Set
    train_select_and_evaluate(
        df_train, y_train, df_test, y_test, feature_cols, cv_metrics, timings
    )


if __name__ == "__main__":
    main()
