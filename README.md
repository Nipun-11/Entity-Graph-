# Module 2: Evaluated Link-Prediction Model (SIH26151)

Dark Web Threat Actor De-anonymization — Entity graph that maps personas across darknet marketplaces via shared PGP keys, cryptocurrency wallets, forum co-occurrences, and trust/vouch links.

---

## What This Module Does

1. **Loads** 1,833 anonymized persona records (500 unique handles across 23 marketplaces) from ANON CSV files.
2. **Collapses** same-handle personas into 500 canonical entity nodes (one per real-world threat actor).
3. **Builds** a NetworkX `MultiDiGraph` with cross-entity edges (`VOUCHED_FOR`, `CO_OCCURRED_IN_THREAD`, `TRANSACTED_WITH`).
4. **Traverses** the graph to discover indirect connections (2–3 hops) between entities that never directly interacted in public.
5. **Extracts** leakage-safe topological and marketplace features with strict candidate-edge masking.
6. **Trains and Evaluates** a locked 14-feature Random Forest link-prediction model with Bayesian Prior Calibration.
7. **Exports** calibrated threat attribution risk scores across all 10,452 candidate entity pairs.

---

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Run the complete graph pipeline and train/evaluate the link-prediction model
python main.py --train-ml

# Or train and evaluate the link-prediction model directly
python model_trainer.py

# Run validation checks (all 5/5 assertions)
python validate.py
```

---

## Machine Learning Link Prediction Model (`model_trainer.py`)

Module 2 includes a **Production 14-Feature Link-Prediction Model** evaluated under a strict **Edge-Holdout Evaluation Protocol** (zero graph feature leakage):

- **Algorithm**: Random Forest Classifier (`n_estimators=100`, `max_depth=6`, `min_samples_split=4`, `min_samples_leaf=2`, `max_features='sqrt'`)
- **Features Extracted ($d=14$)**: Masked Shortest Path distance, Adamic-Adar Index, Preferential Attachment, Degree metrics ($d_u, d_v, \text{diff}, \text{ratio}$), Resource Allocation Index, Jaccard Coefficient, Common Neighbors, Marketplace overlap and Jaccard similarity, and Cryptographic Key/Wallet matches.
- **Architectural Value**: Eliminates reliance on the coarse `same_community` heuristic (which dominated $43.6\%$ of baseline splits) while matching baseline discrimination with cleaner, more interpretable features.

### Unseen Link Prediction Benchmark ($N=590$ Held-Out Test Pairs)

- **PR-AUC (Average Precision)**: **`0.6922`** (5-Fold Graph-Aware CV: `0.6997` $\pm 0.0196$)
- **ROC-AUC Score**: **`0.6490`** (5-Fold Graph-Aware CV: `0.6612` $\pm 0.0134$)

### Operational Threat Attribution Modes:

| Operating Mode | Threshold ($\tau$) | Precision | Recall | F1-Score | Specificity | MCC | Operational Purpose |
|---|:---:|:---:|:---:|:---:|:---:|:---:|---|
| 🎯 **Headline Pitch Mode (Balanced)** | **`0.55`** | **`60.66%`** | **`62.71%`** | **`0.6167`** | **`59.32%`** | **`0.2205`** | **Primary standard for syndicate link attribution** |
| 🛡️ **High-Precision Court Mode** | **`0.60`** | **`65.18%`** | **`49.49%`** | **`0.5626`** | **`73.56%`** | **`0.2375`** | **Specificity-matched court-defensible attribution** |
| 🔍 **Lead-Generation Screening Mode** | **`0.40`** | **`51.37%`** | **`89.15%`** | **`0.6518`** | **`15.59%`** | **`0.0701`** | **Aggressive wide-net funnel ($263/295$ links caught)** |

### Per-Relation-Type Recall Analysis:
- **`VOUCHED_FOR`** ($N=102$): **`76.47%`** @ $\tau=0.55$ | **`99.02%`** @ $\tau=0.40$
- **`CO_OCCURRED_IN_THREAD`** ($N=100$): **`74.00%`** @ $\tau=0.55$ | **`97.00%`** @ $\tau=0.40$
- **`TRANSACTED_WITH`** ($N=94$): **`35.11%`** @ $\tau=0.55$ | **`70.21%`** @ $\tau=0.40$ *(Sparse bilateral escrow pattern)*

---

## Prediction Output Dataset (`data/entity_link_predictions_calibrated.csv`)

The model evaluated all **10,452 candidate 1-hop and 2-hop entity pairs** across 23 marketplaces:
- **Mean Calibrated Probability**: `0.4552` (45.52%)
- **Threat Attribution Tiers**:
  - 🚨 **`HIGH_ATTRIBUTION` ($P \ge 0.65$)**: 2,028 pairs (19.4%)
  - 🔍 **`INVESTIGATIVE_LEAD` ($0.45 \le P < 0.65$)**: 2,704 pairs (25.9%)
  - ⚪ **`LOW_CONFIDENCE` ($P < 0.45$)**: 5,720 pairs (54.7%)

### Key Columns in Prediction CSVs:
- `Entity_A`, `Entity_B`: Canonical entity identifiers (e.g. `E-BlazeBlade597`)
- `Handle_A`, `Handle_B`: Clean handle names (e.g. `BlazeBlade597`)
- `Raw_ML_Probability`: Raw model tree ensemble output
- `Calibrated_Probability_CandidatePool`: Bayesian-calibrated score for candidate pairs ($\pi = 14.11\%$)
- `Calibrated_Probability_FullUniverse`: Bayesian-calibrated score for full-graph universe ($\pi = 1.18\%$)
- `Threat_Attribution_Risk`: Operational risk tier (`HIGH_ATTRIBUTION`, `INVESTIGATIVE_LEAD`, `LOW_CONFIDENCE`)
- `Structural_Relationship_Type`: `DIRECT_COLLABORATOR`, `MULTI_HOP_DIRECTED`, `STRUCTURAL_PROXIMITY_UNDIRECTED`, `INDIRECT_COMMUNITY_CLUSTER`
- `Directed_Shortest_Path_Hops`, `Undirected_Topological_Hops`: Directional traversal vs. topological network hops
- `Shared_Marketplaces`: Semicolon-separated list of common darknet marketplaces
- `Aka_Personas_A`, `Aka_Personas_B`: Complete semicolon-separated lists of collapsed persona IDs

---

## Master File Directory

| File | Purpose |
|---|---|
| `main.py` | Pipeline orchestrator and CLI entry point |
| `model_trainer.py` | Supervised link prediction training, CV, and inference engine |
| `graph_engine.py` | Graph construction and canonical entity collapsing |
| `traversal.py` | Multi-hop directed traversal and path confidence decay scoring |
| `export.py` | JSON export in locked schema |
| `validate.py` | Automated verification test suite |
| `data/entity_link_predictions_calibrated.csv` | **Master calibrated prediction spreadsheet (10,452 pairs)** |
| `data/entity_link_predictions_output.csv` | **Synchronized production output CSV** |
| `data/final_pitch_model_test_metrics.json` | **Frozen pitch benchmark metrics JSON** |
| `data/complete_ml_results.csv` | Master results CSV containing all 12 experimental categories |
| `data/entity_graph_output.json` | Full module JSON output for Fusion and Dashboard modules |
| `data/link_prediction_model.pkl` | Serialized 14-feature production champion model |
| `data/link_prediction_model_baseline_17feat.pkl` | Frozen 17-feature reference baseline backup |

---

## Data Note

Handle names in the ANON CSVs are **fabricated** (e.g., `VoidFox414`, `CrimsonByte850`). The underlying network structure was calibrated against real dark-web archive data, but identity labels are anonymized. Do not re-map to real vendor names. See `ANTIGRAVITY_BUILD_SPEC.md` §2.
