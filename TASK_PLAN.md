# Task List — Entity Graph Module Rebuild

## Phase 0: Data Pipeline
- [x] Write `generate_anon_dataset.py`
  - [x] Load `real_darknet_listings.csv` (180K rows)
  - [x] Select ~500 sellers (prioritize multi-marketplace)
  - [x] Anonymize handles (`VoidFox414` style, deterministic)
  - [x] Assign `persona_id` per (seller, marketplace) pair
  - [x] Generate PGP fingerprints + wallet addresses (shared per seller)
  - [x] Build `SHARED_PGP_AND_WALLET` edges (2,656 at 0.98)
  - [x] Build `VOUCHED_FOR` edges (510, 0.4-0.88)
  - [x] Build `CO_OCCURRED_IN_THREAD` edges (495, 0.4-0.88)
  - [x] Build `TRANSACTED_WITH` edges (495, 0.4-0.88)
  - [x] Write `data/module2_entity_graph_nodes_ANON.csv` (1,833 rows)
  - [x] Write `data/module2_entity_graph_edges_ANON.csv` (4,156 rows)

## Phase 1: Graph Construction
- [x] Write `graph_engine.py` (canonical entity collapse + MultiDiGraph)
- [x] Canonical entity collapse + sanity check
- [x] Build MultiDiGraph + expose `get_graph()`

## Phase 2: Multi-Hop Traversal
- [x] Write `traversal.py`
- [x] path_confidence, graph_link_strength
- [x] Louvain community detection

## Phase 3: Export
- [x] Write `export.py` — pairwise + full graph JSON

## Phase 4: Validation
- [x] Write `validate.py` — run spec §5 checklist

## Phase 5: Entry Point + Handoff
- [x] Write `main.py`
- [x] Write `README.md` — handoff doc for Saraa
- [x] Update `requirements.txt`

## Phase 6: Dashboard Update
- [ ] Update dashboard for new entity format

## Completed Actions
- [x] Full code implementation (Phases 0-5)
- [x] Created `README.md`, `.gitignore`, `validate.py`, `traversal.py`, `graph_engine.py`, `export.py`, `main.py`
- [x] Generated `module2_entity_graph_nodes_ANON.csv` and `module2_entity_graph_edges_ANON.csv`
- [x] Pushed to GitHub repository: https://github.com/Nipun-11/Entity-Graph- (branch: `main`)
