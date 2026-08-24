# Module 2: Evaluated Link-Prediction Model (SIH26151)

Dark Web Threat Actor De-anonymization — Entity graph that maps personas across marketplaces via shared PGP keys, wallet addresses, and trust/vouch links.

## What This Module Does

1. **Loads** 1,833 anonymized persona records (500 unique handles across 23 marketplaces) from ANON CSV files
2. **Collapses** same-handle personas into ~500 canonical entity nodes (one per real actor)
3. **Builds** a NetworkX MultiDiGraph with cross-entity edges (`VOUCHED_FOR`, `CO_OCCURRED_IN_THREAD`, `TRANSACTED_WITH`)
4. **Traverses** the graph to find indirect connections (2–3 hops) between entities that never directly interacted
5. **Scores** each connection with `path_confidence` (multiplicative decay) and `graph_link_strength` (path count + best confidence)
6. **Trains and evaluates** a production-champion supervised link-prediction model with strict zero-leakage edge holdout

## Quick Start

```bash
pip install -r requirements.txt

# Run the full graph pipeline and train/evaluate the champion model
python main.py --train-ml

# Or train/evaluate the champion model directly
python model_trainer.py

# Run validation checks
python validate.py
```

## Machine Learning Link Prediction Model (`model_trainer.py`)

Module 2 includes a **Production Champion Graph ML Model** evaluated under a strict **Edge-Holdout Evaluation Protocol** (zero graph feature leakage):
- **Algorithm**: Random Forest Classifier (`n_estimators=100`, `max_depth=6`, `min_samples_split=4`, `min_samples_leaf=2`, `max_features='sqrt'`)
- **Features Extracted ($d=14$)**: Masked Shortest Path distance, Adamic-Adar Index, Preferential Attachment, Degree metrics ($d_u, d_v, \text{diff}, \text{ratio}$), Resource Allocation Index, Jaccard Coefficient, Common Neighbors, Marketplace overlap and Jaccard similarity, and Cryptographic Key/Wallet matches.
- **Genuine Unseen Link Prediction Performance (20% Edge Hold-Out, $N=590$ Unseen Test Pairs)**:
  - **ROC-AUC Score**: `0.6510` (5-Fold Graph-Aware CV: `0.6612` $\pm 0.0134$)
  - **Average Precision (PR-AUC)**: `0.6871` (5-Fold Graph-Aware CV: `0.6997` $\pm 0.0196$)
  - **Standard Operating Point ($\tau=0.50$)**:
    - **Recall**: `46.10%` (136 TP, +10.17% gain over baseline)
    - **Precision**: `67.66%`
    - **F1-Score**: `0.5484` (+12.5% relative boost)
    - **Specificity**: `77.97%` | **Accuracy**: `62.03%` | **Log Loss**: `0.6570`
  - **Operational Threat Discovery Point ($\tau=0.40$)**:
    - **Recall**: `66.44%` (196 / 295 TP discovered)
    - **Precision**: `57.14%`
    - **F1-Score**: `0.6144`
- **Output Artifacts**:
  - Model Artifact: `data/link_prediction_model.pkl`
  - Metrics JSON: `data/model_metrics.json`
  - Long-Format Master Results: `data/complete_ml_results.csv`
  - Tabular Summary: `data/final_model_metrics.csv`
  - Feature Importances: `data/feature_importance.csv`
  - Historical Baseline Backup: `data/link_prediction_model_baseline_17feat.pkl` & `data/model_metrics_baseline_17feat.json`

## Output

**`data/entity_graph_output.json`** — contains:
- `pairwise_scores` — scored connections for Fusion module (join key: `persona_id` via `aka_persona_ids`)
- `graph.nodes` — canonical entity nodes with `entity_id`, `aka_persona_ids`, `active_marketplaces`
- `graph.edges` — cross-entity relationships with `relation_type` and `confidence`
- `statistics` — summary counts

## Cross-Module Integration

- **Fusion module** reads `entity_id_a`, `entity_id_b`, `graph_link_strength`, `path_confidence` from `pairwise_scores`
- **Dashboard** reads `graph.nodes` and `graph.edges` for visualization
- **Join key**: `persona_id` — every entity node carries `aka_persona_ids` (list of persona_ids that collapsed into it). This maps back to the same `persona_id`s used by Infra+Timing (Module 1) and Stylometry (Module 3).

## Key Interface

If you're continuing this build, `graph_engine.py` exposes:

```python
from graph_engine import EntityGraph

engine = EntityGraph()
engine.load()
G = engine.get_graph()  # Returns networkx.MultiDiGraph
```

`get_graph()` is the stable interface — continue from here even if internals are incomplete.

## Files

| File | Purpose |
|------|---------|
| `main.py` | Pipeline entry point and model-training CLI |
| `model_trainer.py` | Supervised link-prediction training, evaluation, and inference helper |
| `graph_engine.py` | Graph construction + canonical entity collapse |
| `traversal.py` | Multi-hop path finding + scoring |
| `export.py` | JSON export in locked schema |
| `validate.py` | Validation checklist (spec §5) |
| `generate_anon_dataset.py` | Generates ANON CSVs from raw Gwern archive |
| `data/module2_entity_graph_nodes_ANON.csv` | 1,833 persona records (input) |
| `data/module2_entity_graph_edges_ANON.csv` | 4,156 edges (input) |
| `data/complete_ml_results.csv` | Master results CSV containing all baseline, champion, ablation & validation data |
| `data/entity_graph_output.json` | Module output (generated) |

## Data Note

Handle names in the ANON CSVs are **fabricated** (e.g., `VoidFox414`, `CrimsonByte850`). The underlying structure was calibrated against real dark-web archive data, but identity labels are anonymized. Do not re-map to real vendor names. See `ANTIGRAVITY_BUILD_SPEC.md` §2.
