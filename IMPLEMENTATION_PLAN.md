# Implementation Plan — Entity Graph Module (Full Rebuild)

## Context: What Changed

The previous build (synthetic_dataset.py, graph_engine.py, identity_resolver.py, etc.) used a **fabricated 18-actor JSON dataset** with planted identity reuse patterns. That approach is now **replaced entirely** by:

1. **Real data source**: `real_darknet_listings.csv` — 180,317 real Gwern darknet archive listings, 5,788 sellers, 8 marketplaces
2. **New build spec**: `ANTIGRAVITY_BUILD_SPEC.md` — locked design, canonical collapse, multi-hop traversal
3. **Cross-module contract**: `CROSS_MODULE_DATA_ARCHITECTURE.md` — `persona_id` is the join key across all 4 modules

> [!IMPORTANT]
> **All old pipeline code (graph_engine.py, identity_resolver.py, evaluate.py, etc.) has been replaced.** The new spec uses canonical entity collapse + multi-hop traversal — fundamentally different from the old shared-PGP/wallet resolver.

---

## Architecture & Implementation Overview

### Phase 0 — Data Pipeline (Generate ANON CSVs from raw Gwern archive)

#### `generate_anon_dataset.py`

Reads `real_darknet_listings.csv` (180K rows, 5,788 sellers, 8 marketplaces) and produces two ANON CSV files:

**Step-by-step logic:**
1. **Select ~500 unique handles** — prioritize sellers who appear on **multiple marketplaces** (1,269 multi-market sellers exist in the data). This gives natural cross-marketplace identity linkage. Fill remaining slots from single-market sellers.
2. **Create `persona_id`** — one per (seller, marketplace) pair. Format: `P-{uuid}`. A seller on 3 marketplaces gets 3 persona_ids.
3. **Anonymize handles** — map each real seller name to a fabricated name (`VoidFox414` style) using a deterministic hash+seed. Real names never appear in output. Marketplace names stay real (per spec).
4. **Generate PGP fingerprints** — one 40-char hex fingerprint per seller (shared across all their marketplace personas — this is the identity leak the graph should catch).
5. **Generate wallet addresses** — one BTC-like address per seller (also shared across personas).
6. **Extract first_seen/last_seen dates** — from the listing data if available, else generate realistic ranges (2013–2021).
7. **Build edges:**
   - `SHARED_PGP_AND_WALLET` (confidence=0.98) — between every pair of persona_ids belonging to the same handle
   - `VOUCHED_FOR` (~510 edges, confidence 0.4–0.88) — cross-handle trust links planted among connected sellers
   - `CO_OCCURRED_IN_THREAD` (~495 edges, confidence 0.4–0.88) — sellers who co-appear in the same listing descriptions/markets
   - `TRANSACTED_WITH` (~495 edges, confidence 0.4–0.88) — simulated transaction links
8. **Outputs:**
   - `data/module2_entity_graph_nodes_ANON.csv` — 1,833 rows (persona_id, handle, marketplace, pgp_fingerprint, wallet_address, first_seen_date, last_seen_date)
   - `data/module2_entity_graph_edges_ANON.csv` — 4,156 rows (source_persona_id, target_persona_id, relation_type, confidence_weight)

---

### Phase 1 — Graph Construction

#### `graph_engine.py`

Per spec §4.1:
1. Load `data/module2_entity_graph_nodes_ANON.csv` with pandas
2. Group by `handle` → collapse into **canonical entity nodes**:
   - `entity_id` = `E-{handle}` (e.g. `E-VoidFox414`)
   - Attributes: `aka_persona_ids` (list of all persona_ids for this handle), `active_marketplaces` (list), `first_seen`, `last_seen`
3. Load `data/module2_entity_graph_edges_ANON.csv`
4. **`SHARED_PGP_AND_WALLET` edges** — do NOT add as graph edges. Use as sanity check: confirm every pair maps to the same canonical entity.
5. **Other edges** (`VOUCHED_FOR`, `CO_OCCURRED_IN_THREAD`, `TRANSACTED_WITH`) — remap `source_persona_id`/`target_persona_id` to canonical `entity_id`s, add as edges on a `networkx.MultiDiGraph`
6. **Directionality**: `VOUCHED_FOR` = directional. `CO_OCCURRED_IN_THREAD` and `TRANSACTED_WITH` = symmetric (add both directions)
7. Expose `get_graph()` returning the built graph

---

### Phase 2 — Multi-Hop Traversal

#### `traversal.py`

Per spec §4.2:
1. `find_connections(entity_id, max_hops=3)` — all entities reachable within N hops
2. `find_path(source, target, cutoff=3)` — shortest path + all simple paths
3. `get_connected_component(entity_id)` — everything linked to this actor (on undirected view)
4. `path_confidence(path)` — multiply edge `confidence_weight` along the path
5. `graph_link_strength(source, target)` — combine number of distinct paths + strongest path confidence
6. Louvain community detection (`networkx.algorithms.community.louvain_communities`)

---

### Phase 3 — Export

#### `export.py`

Per spec §4.3 — writes `data/entity_graph_output.json` with two sections:
1. **Pairwise scoring** (for Fusion module): `entity_id_a`, `entity_id_b`, `connected`, `shortest_path`, `path_length`, `path_confidence`, `graph_link_strength`, `evidence_path`
2. **Full graph** (for Dashboard): `nodes` (with `aka_persona_ids`) and `edges` (with `relation_type`, `confidence`)

---

### Phase 4 — Validation

#### `validate.py`

Per spec §5:
- [x] Confirm every `SHARED_PGP_AND_WALLET` pair maps to the same canonical entity
- [x] Pick entities with known `VOUCHED_FOR`/`TRANSACTED_WITH`/`CO_OCCURRED_IN_THREAD` connections → confirm traversal finds them
- [x] Test a 2–3 hop chain between two entities with no direct edge → confirm `all_simple_paths` surfaces the indirect connection
- [x] Confirm isolated entities return `connected: false`
- [x] Verify `aka_persona_ids` completeness

---

### Phase 5 — Entry Point + Handoff

#### `main.py`
Single entry point:
```bash
python main.py                    # Build graph + run validation + export
python main.py --serve            # Also launch dashboard
```

#### `README.md`
Handoff doc for Saraa and team members.

---

### Phase 6 — Dashboard Update
- `dashboard/app.js`, `dashboard/index.html` updated for canonical entities and traversal path search.
