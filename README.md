# Module 2: Entity Relationship Graph (SIH26151)

Dark Web Threat Actor De-anonymization — Entity graph that maps personas across marketplaces via shared PGP keys, wallet addresses, and trust/vouch links.

## What This Module Does

1. **Loads** 1,833 anonymized persona records (500 unique handles across 23 marketplaces) from ANON CSV files
2. **Collapses** same-handle personas into ~500 canonical entity nodes (one per real actor)
3. **Builds** a NetworkX MultiDiGraph with cross-entity edges (VOUCHED_FOR, CO_OCCURRED_IN_THREAD, TRANSACTED_WITH)
4. **Traverses** the graph to find indirect connections (2-3 hops) between entities that never directly interacted
5. **Scores** each connection with `path_confidence` (multiplicative decay) and `graph_link_strength` (path count + best confidence)
6. **Exports** `entity_graph_output.json` — pairwise scores for Fusion + full graph for Dashboard

## Quick Start

```bash
pip install -r requirements.txt

# Run the full pipeline: build graph → validate → export
python main.py

# Run with dashboard visualization
python main.py --serve
```

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
| `main.py` | Pipeline entry point |
| `graph_engine.py` | Graph construction + canonical entity collapse |
| `traversal.py` | Multi-hop path finding + scoring |
| `export.py` | JSON export in locked schema |
| `validate.py` | Validation checklist (spec §5) |
| `generate_anon_dataset.py` | Generates ANON CSVs from raw Gwern archive |
| `data/module2_entity_graph_nodes_ANON.csv` | 1,833 persona records (input) |
| `data/module2_entity_graph_edges_ANON.csv` | 4,156 edges (input) |
| `data/entity_graph_output.json` | Module output (generated) |

## Data Note

Handle names in the ANON CSVs are **fabricated** (e.g., `VoidFox414`, `CrimsonByte850`). The underlying structure was calibrated against real dark-web archive data, but identity labels are anonymized. Do not re-map to real vendor names. See `ANTIGRAVITY_BUILD_SPEC.md` §2.
