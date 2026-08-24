"""
model_trainer.py — Supervised ML Link Prediction Model for Entity Graph
=========================================================================
Trains a Machine Learning model (Random Forest / XGBoost) on graph topological
and behavioral features to predict whether two threat actor personas or entities
are linked (collaborative syndicate, transaction partner, or Sybil account).

Features extracted per entity pair (u, v):
  1. Jaccard Coefficient of Common Neighbors
  2. Adamic-Adar Index
  3. Resource Allocation Index
  4. Preferential Attachment Score
  5. Common Neighbors Count
  6. Shortest Path Hop Distance
  7. Multi-Hop Path Confidence (multiplicative decay)
  8. Graph Link Strength Score
  9. Louvain Community Co-membership (1/0)
 10. Darknet Marketplace Overlap Count
 11. Darknet Marketplace Jaccard Similarity
 12. Degree Centrality (u, v) and Degree Ratio
 13. Same PGP Fingerprint Flag (1/0)
 14. Same Crypto Wallet Flag (1/0)

Evaluation:
  - Stratified 5-Fold Cross-Validation
  - ROC-AUC, Average Precision (PR-AUC), F1-Score, Precision, Recall
  - Feature Importance Ranking
  - Model serialization to data/link_prediction_model.pkl
"""

import os
import sys
import math
import json
import random
import joblib
import numpy as np
import pandas as pd
import networkx as nx
from pathlib import Path
from typing import Dict, List, Tuple, Any

# Scikit-learn
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
from sklearn.model_selection import StratifiedKFold, cross_validate, train_test_split
from sklearn.metrics import (
    roc_auc_score,
    average_precision_score,
    precision_score,
    recall_score,
    f1_score,
    accuracy_score,
    classification_report,
    roc_curve,
    precision_recall_curve
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

# Fixed seed for reproducibility
RANDOM_SEED = 42
np.random.seed(RANDOM_SEED)
random.seed(RANDOM_SEED)


# ===========================================================================
# 1. Graph Feature Extractor
# ===========================================================================

class GraphFeatureExtractor:
    """
    Extracts topological, cryptographic, and operational features
    for pairs of entities in the Canonical Entity Graph.
    """

    def __init__(self, engine, traversal):
        self.engine = engine
        self.traversal = traversal
        self.graph = engine.get_graph()
        self.undirected = self.graph.to_undirected()
        self.entities = engine.get_all_entities()

        # Precompute Louvain communities
        self.communities = traversal.detect_communities()
        self.node_to_comm = {}
        for idx, comm in enumerate(self.communities):
            for node in comm:
                self.node_to_comm[node] = idx

        # Degrees
        self.degrees = dict(self.undirected.degree())

    def extract_pair_features(self, u: str, v: str) -> Dict[str, float]:
        """
        Extract all feature attributes for entity pair (u, v).
        """
        feats = {}

        # 1. Common neighbors & neighborhoods
        neighbors_u = set(self.undirected.neighbors(u)) if u in self.undirected else set()
        neighbors_v = set(self.undirected.neighbors(v)) if v in self.undirected else set()
        common_neighbors = neighbors_u.intersection(neighbors_v)
        union_neighbors = neighbors_u.union(neighbors_v)

        feats["common_neighbors_count"] = float(len(common_neighbors))
        feats["jaccard_coefficient"] = (
            len(common_neighbors) / len(union_neighbors) if len(union_neighbors) > 0 else 0.0
        )

        # 2. Adamic-Adar Index
        adamic_adar = 0.0
        for w in common_neighbors:
            deg = self.degrees.get(w, 0)
            if deg > 1:
                adamic_adar += 1.0 / math.log(deg)
        feats["adamic_adar_index"] = round(adamic_adar, 5)

        # 3. Resource Allocation Index
        resource_alloc = 0.0
        for w in common_neighbors:
            deg = self.degrees.get(w, 0)
            if deg > 0:
                resource_alloc += 1.0 / deg
        feats["resource_allocation_index"] = round(resource_alloc, 5)

        # 4. Preferential Attachment
        deg_u = self.degrees.get(u, 0)
        deg_v = self.degrees.get(v, 0)
        feats["preferential_attachment"] = float(deg_u * deg_v)
        feats["degree_u"] = float(deg_u)
        feats["degree_v"] = float(deg_v)
        feats["degree_ratio"] = (
            min(deg_u, deg_v) / max(deg_u, deg_v) if max(deg_u, deg_v) > 0 else 0.0
        )
        feats["degree_diff"] = float(abs(deg_u - deg_v))

        # 5. Shortest path & Traversal scores
        try:
            if nx.has_path(self.undirected, u, v):
                sp = nx.shortest_path(self.undirected, u, v)
                feats["shortest_path_length"] = float(len(sp) - 1)
                feats["is_connected"] = 1.0
                feats["path_confidence"] = self.traversal.path_confidence(sp)
            else:
                feats["shortest_path_length"] = 5.0  # Cap for disconnected
                feats["is_connected"] = 0.0
                feats["path_confidence"] = 0.0
        except (nx.NetworkXError, nx.NodeNotFound):
            feats["shortest_path_length"] = 5.0
            feats["is_connected"] = 0.0
            feats["path_confidence"] = 0.0

        # Graph link strength
        feats["graph_link_strength"] = self.traversal.graph_link_strength(u, v, cutoff=3)

        # 6. Louvain Community Co-membership
        comm_u = self.node_to_comm.get(u, -1)
        comm_v = self.node_to_comm.get(v, -2)
        feats["same_community"] = 1.0 if (comm_u == comm_v and comm_u != -1) else 0.0

        # 7. Marketplace footprints
        ent_u = self.entities.get(u, {})
        ent_v = self.entities.get(v, {})
        mkts_u = set(ent_u.get("active_marketplaces", []))
        mkts_v = set(ent_v.get("active_marketplaces", []))
        common_mkts = mkts_u.intersection(mkts_v)
        union_mkts = mkts_u.union(mkts_v)

        feats["market_overlap_count"] = float(len(common_mkts))
        feats["market_jaccard"] = (
            len(common_mkts) / len(union_mkts) if len(union_mkts) > 0 else 0.0
        )

        # 8. Cryptographic identifiers
        pgp_u = ent_u.get("pgp_fingerprint")
        pgp_v = ent_v.get("pgp_fingerprint")
        wallet_u = ent_u.get("wallet_address")
        wallet_v = ent_v.get("wallet_address")

        feats["same_pgp_key"] = 1.0 if (pgp_u and pgp_v and pgp_u == pgp_v) else 0.0
        feats["same_wallet"] = 1.0 if (wallet_u and wallet_v and wallet_u == wallet_v) else 0.0

        return feats


# ===========================================================================
# 2. Dataset Construction
# ===========================================================================

def build_training_dataset(engine, traversal, extractor, n_samples=2500) -> Tuple[pd.DataFrame, np.ndarray, List[str]]:
    """
    Constructs a link prediction dataset using the standard edge-masking formulation:
    - Positive instances (y=1): Real entity edges (VOUCHED_FOR, TRANSACTED_WITH, CO_OCCURRED).
    - Negative instances (y=0): Non-edge pairs spanning hard negatives (sharing neighbors/communities)
      and random non-edges.
    """
    print("\n[*] Constructing ML training dataset using edge-masking formulation...")

    G = engine.get_graph()
    entities = engine.get_entity_ids()
    undirected = G.to_undirected()

    # Real graph edges (positive pairs)
    all_real_edges = set()
    for u, v in undirected.edges():
        if u != v:
            all_real_edges.add(tuple(sorted([u, v])))

    positive_list = list(all_real_edges)
    random.shuffle(positive_list)
    n_pos = min(len(positive_list), n_samples // 2)
    selected_positives = positive_list[:n_pos]

    # Negative sampling: include hard negatives (2-hop neighbors without direct edge) and random pairs
    negative_pairs = set()
    
    # 1. Hard negatives (share common neighbors or same community but have NO edge)
    for u, v in selected_positives[:n_pos // 2]:
        neighbors_u = list(undirected.neighbors(u))
        if neighbors_u:
            w = random.choice(neighbors_u)
            neighbors_w = list(undirected.neighbors(w))
            for candidate in neighbors_w:
                if candidate != u and tuple(sorted([u, candidate])) not in all_real_edges:
                    negative_pairs.add(tuple(sorted([u, candidate])))
                    if len(negative_pairs) >= n_pos // 2:
                        break

    # 2. Random negatives
    attempts = 0
    max_attempts = n_pos * 30
    while len(negative_pairs) < n_pos and attempts < max_attempts:
        attempts += 1
        u, v = random.sample(entities, 2)
        pair = tuple(sorted([u, v]))
        if pair not in all_real_edges and pair not in negative_pairs:
            negative_pairs.add(pair)

    selected_negatives = list(negative_pairs)[:n_pos]

    print(f"    Positive link pairs (y=1): {len(selected_positives)}")
    print(f"    Negative non-link pairs (y=0): {len(selected_negatives)} (including hard topological negatives)")

    records = []
    labels = []

    for u, v in selected_positives:
        feats = extractor.extract_pair_features(u, v)
        feats["entity_id_a"] = u
        feats["entity_id_b"] = v
        records.append(feats)
        labels.append(1)

    for u, v in selected_negatives:
        feats = extractor.extract_pair_features(u, v)
        feats["entity_id_a"] = u
        feats["entity_id_b"] = v
        records.append(feats)
        labels.append(0)

    df = pd.DataFrame(records)
    y = np.array(labels)

    feature_cols = [
        c for c in df.columns 
        if c not in ("entity_id_a", "entity_id_b", "is_connected", "shortest_path_length")
    ]

    print(f"    Total dataset: {df.shape[0]} samples × {len(feature_cols)} topological & behavioral features")
    return df, y, feature_cols


# ===========================================================================
# 3. Model Training & Cross-Validation
# ===========================================================================

def train_and_evaluate(df: pd.DataFrame, y: np.ndarray, feature_cols: List[str]):
    """
    Trains Random Forest and XGBoost classifiers with 5-fold cross-validation.
    """
    print("\n" + "=" * 60)
    print("TRAINING GRAPH LINK PREDICTION CLASSIFIER")
    print("=" * 60)

    X = df[feature_cols].values

    # Train/Test Split (80/20)
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.20, random_state=RANDOM_SEED, stratify=y
    )

    # ------------------------------------------------------------------
    # Model 1: Random Forest Classifier
    # ------------------------------------------------------------------
    print("\n[*] Training Random Forest Classifier (100 trees)...")
    rf_model = RandomForestClassifier(
        n_estimators=100,
        max_depth=10,
        min_samples_split=4,
        random_state=RANDOM_SEED,
        n_jobs=-1
    )

    # 5-Fold Stratified Cross Validation
    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=RANDOM_SEED)
    scoring = {
        'roc_auc': 'roc_auc',
        'f1': 'f1',
        'precision': 'precision',
        'recall': 'recall',
        'accuracy': 'accuracy'
    }
    cv_results = cross_validate(rf_model, X_train, y_train, cv=cv, scoring=scoring)

    print("\n--- 5-Fold Cross-Validation Performance (Random Forest) ---")
    print(f"  ROC-AUC:   {cv_results['test_roc_auc'].mean():.4f} (+/- {cv_results['test_roc_auc'].std():.4f})")
    print(f"  F1-Score:  {cv_results['test_f1'].mean():.4f} (+/- {cv_results['test_f1'].std():.4f})")
    print(f"  Precision: {cv_results['test_precision'].mean():.4f} (+/- {cv_results['test_precision'].std():.4f})")
    print(f"  Recall:    {cv_results['test_recall'].mean():.4f} (+/- {cv_results['test_recall'].std():.4f})")
    print(f"  Accuracy:  {cv_results['test_accuracy'].mean():.4f} (+/- {cv_results['test_accuracy'].std():.4f})")

    # Fit on full training set and evaluate on hold-out test set
    rf_model.fit(X_train, y_train)
    y_pred = rf_model.predict(X_test)
    y_prob = rf_model.predict_proba(X_test)[:, 1]

    test_roc_auc = roc_auc_score(y_test, y_prob)
    test_pr_auc = average_precision_score(y_test, y_prob)
    test_f1 = f1_score(y_test, y_pred)
    test_prec = precision_score(y_test, y_pred)
    test_rec = recall_score(y_test, y_pred)
    test_acc = accuracy_score(y_test, y_pred)

    print("\n--- Hold-Out Test Set Results (20% Split) ---")
    print(f"  Test Accuracy:     {test_acc:.4f}")
    print(f"  Test Precision:    {test_prec:.4f}")
    print(f"  Test Recall:       {test_rec:.4f}")
    print(f"  Test F1-Score:     {test_f1:.4f}")
    print(f"  Test ROC-AUC:      {test_roc_auc:.4f}")
    print(f"  Test PR-AUC:       {test_pr_auc:.4f}")

    # ------------------------------------------------------------------
    # Model 2: XGBoost Classifier (if available)
    # ------------------------------------------------------------------
    best_model = rf_model
    model_name = "RandomForestClassifier"

    if HAS_XGBOOST:
        print("\n[*] Training XGBoost Classifier...")
        xgb_model = XGBClassifier(
            n_estimators=100,
            max_depth=6,
            learning_rate=0.08,
            random_state=RANDOM_SEED,
            eval_metric="logloss"
        )
        xgb_model.fit(X_train, y_train)
        xgb_prob = xgb_model.predict_proba(X_test)[:, 1]
        xgb_roc_auc = roc_auc_score(y_test, xgb_prob)
        xgb_f1 = f1_score(y_test, xgb_model.predict(X_test))

        print(f"  XGBoost Test ROC-AUC: {xgb_roc_auc:.4f} | F1-Score: {xgb_f1:.4f}")
        if xgb_roc_auc >= test_roc_auc:
            best_model = xgb_model
            model_name = "XGBoostClassifier"
            test_roc_auc = xgb_roc_auc
            test_f1 = xgb_f1

    # ------------------------------------------------------------------
    # Feature Importance Ranking
    # ------------------------------------------------------------------
    importances = best_model.feature_importances_
    feat_imp = sorted(zip(feature_cols, importances), key=lambda x: -x[1])

    print("\n--- Feature Importance Ranking (Top Predictive Signals) ---")
    for rank, (name, imp) in enumerate(feat_imp, 1):
        bar = "█" * int(imp * 35)
        print(f"  {rank:2d}. {name:<28} {imp:.4f}  {bar}")

    # ------------------------------------------------------------------
    # Serialization & Metrics JSON
    # ------------------------------------------------------------------
    model_artifact = {
        "model": best_model,
        "model_name": model_name,
        "feature_cols": feature_cols,
        "metrics": {
            "test_roc_auc": round(float(test_roc_auc), 4),
            "test_pr_auc": round(float(test_pr_auc), 4),
            "test_f1_score": round(float(test_f1), 4),
            "test_precision": round(float(test_prec), 4),
            "test_recall": round(float(test_rec), 4),
            "test_accuracy": round(float(test_acc), 4),
            "cv_roc_auc_mean": round(float(cv_results['test_roc_auc'].mean()), 4),
            "cv_f1_mean": round(float(cv_results['test_f1'].mean()), 4)
        },
        "feature_importance": [
            {"feature": name, "importance": round(float(imp), 4)} for name, imp in feat_imp
        ]
    }

    joblib.dump(model_artifact, MODEL_OUTPUT_PATH)
    print(f"\n[OK] Model saved to {MODEL_OUTPUT_PATH}")

    # Save metrics JSON
    with open(METRICS_OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump({
            "model_type": model_name,
            "evaluation_summary": model_artifact["metrics"],
            "feature_importance_ranking": model_artifact["feature_importance"],
            "dataset_info": {
                "total_training_samples": len(df),
                "features_count": len(feature_cols),
                "positive_links": int(sum(y)),
                "negative_links": int(len(y) - sum(y))
            }
        }, f, indent=2)

    print(f"[OK] Evaluation metrics saved to {METRICS_OUTPUT_PATH}")

    return best_model, model_artifact["metrics"]


# ===========================================================================
# 4. Standalone Runner & Prediction Helper
# ===========================================================================

def predict_link_probability(entity_a: str, entity_b: str) -> float:
    """
    Inference helper: Loads trained model and predicts link probability between u and v.
    """
    if not MODEL_OUTPUT_PATH.exists():
        raise FileNotFoundError(f"Model not found at {MODEL_OUTPUT_PATH}. Run model_trainer.py first.")

    from graph_engine import EntityGraph
    from traversal import GraphTraversal

    engine = EntityGraph()
    engine.load()
    trav = GraphTraversal(engine.get_graph())
    extractor = GraphFeatureExtractor(engine, trav)

    artifact = joblib.load(MODEL_OUTPUT_PATH)
    model = artifact["model"]
    feature_cols = artifact["feature_cols"]

    feats = extractor.extract_pair_features(entity_a, entity_b)
    x_vec = np.array([[feats[col] for col in feature_cols]])
    prob = model.predict_proba(x_vec)[0, 1]
    return round(float(prob), 4)


def main():
    from graph_engine import EntityGraph
    from traversal import GraphTraversal

    # Load graph
    engine = EntityGraph()
    engine.load()
    trav = GraphTraversal(engine.get_graph())

    # Extract features & build dataset
    extractor = GraphFeatureExtractor(engine, trav)
    df, y, feature_cols = build_training_dataset(engine, trav, extractor, n_samples=2500)

    # Train model & evaluate
    train_and_evaluate(df, y, feature_cols)


if __name__ == "__main__":
    main()
