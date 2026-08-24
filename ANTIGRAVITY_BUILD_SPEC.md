# SIH26151 — Entity Relationship Graph Module — Full Build Spec
**For: AI coding agent (Antigravity) — build this end-to-end**
**Project: Dark Web Threat Actor De-anonymization (NTRO, SIH26151)**
**Owners: Nipun (build), Saraa (design/handoff continuation) — this doc is the single source of truth for both**

---

## 0. Context (read first)

This is Module 2 of a 4-module system. Three signal modules — Infra+Timing, **Entity Graph (this one)**, and Stylometry — each score whether two "personas" (a handle-on-a-marketplace instance) belong to the same real-world actor. All three feed a Fusion module which combines the scores into one confidence rating, surfaced on a dashboard.

Everything in this project runs on **synthetic data** — no live dark-web scraping. Real dark-web datasets (Gwern archive, etc.) were used only to calibrate realistic naming/structure patterns; **actual handle names in the working dataset are fabricated (anonymized)**, not real vendor identities — this is intentional and must not be reverted. See §2.

---

## 1. What This Module Does

Build a network graph where:
- **Nodes** = personas/handles/identifiers
- **Edges** = evidence that two personas are connected (shared wallet, shared PGP key, co-occurrence in a post/listing, explicit trust/vouch link)

Core value: **multi-hop traversal** — reveal that actor A connects to actor C through a shared wallet with B, even when A and C never directly interacted. A human analyst scanning raw data would likely miss this.

**Output feeds:**
- Fusion module: `graph_link_strength` and `path_confidence` per persona pair
- Dashboard: full node/edge graph for actor profile view / visualization

---

## 2. Data Files (use these exact files — do not regenerate, do not use non-ANON versions)

```
data/module2_entity_graph_nodes_ANON.csv
data/module2_entity_graph_edges_ANON.csv
```

**Nodes CSV columns:** `persona_id, handle, marketplace, pgp_fingerprint, wallet_address, first_seen_date, last_seen_date`
- 1,833 rows, 500 unique `handle` values, 23 marketplaces.
- **`handle` values are fabricated (anonymized) placeholder names** — e.g. `VoidFox414`, `CrimsonByte850` — styled to look like realistic dark-web handles but not tied to any real vendor identity. This is deliberate: the underlying dataset structure (marketplace names, PGP/wallet format, edge patterns, confidence distributions) was calibrated against real dark-web archive data, but identity labels were swapped to fabricated ones before this became a graph/dataset with claimed "same actor" linkages — so no fabricated identity-linkage claim is attached to a real person's handle.
- **Do not** re-map `handle` back to any real name, and do not source additional handles from real vendor data going forward. If more synthetic personas are ever needed, generate fabricated handles (same style as existing ones), never reuse real dark-web usernames as node labels.

**Edges CSV columns:** `source_persona_id, target_persona_id, relation_type, confidence_weight`
- 4,216 edges, 4 relation types:
  - `SHARED_PGP_AND_WALLET` — 2,716 edges, fixed 0.98 confidence. Connects the same handle's multiple market-records to each other.
  - `VOUCHED_FOR` — 510 edges, confidence 0.4–0.88
  - `CO_OCCURRED_IN_THREAD` — 495 edges, confidence 0.4–0.88
  - `TRANSACTED_WITH` — 495 edges, confidence 0.4–0.88

---

## 3. Locked Design Decision — Canonical Node Collapse

**Problem:** `SHARED_PGP_AND_WALLET` edges form near-complete cliques per handle (e.g. one handle has 10 `persona_id`s, one per marketplace, all pairwise-connected at 0.98). Without collapsing these into a single canonical node before cross-persona traversal, any path between two different handles will find trivial "shortest paths" bouncing through duplicate market-records of the same handle — inflating path counts and making `path_confidence` meaningless.

**Decision (locked, do not revisit): collapse same-handle persona_ids into one canonical entity node.** Matches what a real analyst wants: "this ONE actor connects to that ONE actor." Avoids double-counting. Stronger demo story: "resolved 1,833 raw identity fragments down to 500 canonical entities, then found hidden connections between those."

---

## 4. Build Tasks

### 4.1 Graph Construction / Loader (`graph_engine.py`)

1. Load `module2_entity_graph_nodes_ANON.csv`.
2. Group records by `handle` (`pandas.groupby('handle')` handles this cleanly). Ideally cross-check `pgp_fingerprint`/`wallet_address` match within the group in case two different handles ever accidentally share a wallet — that itself is a meaningful signal, not noise, so flag it rather than silently merging.
3. For each handle group, create one **canonical entity node**:
   - `entity_id` — stable ID, e.g. hash of the handle or the first `persona_id` in the group, prefixed `E-` (e.g. `E-VoidFox414`)
   - Attributes: `aka_persona_ids` (list), `active_marketplaces` (list), `first_seen`, `last_seen`
4. Load `module2_entity_graph_edges_ANON.csv`.
   - `SHARED_PGP_AND_WALLET` edges are now redundant (already captured by the collapse) — **do not add as graph edges**. Instead use them as a sanity check: confirm every `SHARED_PGP_AND_WALLET` pair maps to the same canonical entity. If any doesn't, the collapse logic has a bug — fix before proceeding.
   - For `VOUCHED_FOR`, `CO_OCCURRED_IN_THREAD`, `TRANSACTED_WITH` edges: remap `source_persona_id`/`target_persona_id` to their canonical `entity_id`s, then add as graph edges with `relation_type` and `confidence_weight` as attributes.
   - If two canonical entities end up connected by more than one edge (e.g. both vouched AND transacted), keep both as **parallel edges** — use `networkx.MultiDiGraph`, don't collapse them. Multiple independent edges is itself a strength signal for scoring later.
5. Directionality: `VOUCHED_FOR` is naturally directional (A vouches for B ≠ B vouches for A). `CO_OCCURRED_IN_THREAD` and `TRANSACTED_WITH` are naturally symmetric — add them as edges in both directions on the `MultiDiGraph`.
6. Expose `get_graph()` returning the built graph — this is the interface the traversal code imports.

**Libraries:** `networkx`, `pandas`.

### 4.2 Multi-Hop Traversal (`traversal.py`)

1. Given a canonical `entity_id`, find all other entities reachable within N hops (start with N=2–3; deeper paths get noisy and harder to explain in a live demo).
2. Use NetworkX's built-in path-finding:
   - `nx.shortest_path(graph, source, target)` for a specific pair
   - `nx.all_simple_paths(graph, source, target, cutoff=3)` to enumerate multiple possible paths between two entities
   - `nx.node_connected_component(graph, entity_id)` (on `.to_undirected()` view if using a DiGraph) for "show me everything linked to this actor" — building block for the dashboard's actor profile view
3. **`path_confidence`**: multiply the `confidence_weight` of each edge along a path (confidence naturally decays with hops — explainable, simple, no need for anything fancier for a PoC).
4. **`graph_link_strength`**: combine the number of distinct paths connecting two entities with the strongest single path's confidence — more independent paths = stronger evidence of a real connection.
5. **Optional stretch** (only if ahead of schedule): Louvain community detection (`networkx.algorithms.community.louvain_communities`) on the collapsed entity graph — with 500 entities and ~1,500 non-redundant edges this should run fast and gives a strong visual for the demo.

**Libraries:** `networkx` (traversal + optional community detection built in).

### 4.3 Output Format (`export.py`)

Per-pair scoring output:
```json
{
  "entity_id_a": "E-VoidFox414",
  "entity_id_b": "E-SomeOtherEntity",
  "connected": true,
  "shortest_path": ["E-VoidFox414", "E-Intermediate", "E-SomeOtherEntity"],
  "path_length": 2,
  "path_confidence": 0.63,
  "graph_link_strength": 0.71,
  "evidence_path": [
    {"from": "E-VoidFox414", "to": "E-Intermediate", "relation_type": "TRANSACTED_WITH", "confidence": 0.9},
    {"from": "E-Intermediate", "to": "E-SomeOtherEntity", "relation_type": "VOUCHED_FOR", "confidence": 0.7}
  ]
}
```

Full graph export (for Dashboard visualization):
```json
{
  "nodes": [
    {"entity_id": "E-VoidFox414", "aka_persona_ids": ["P-...", "P-..."], "active_marketplaces": ["...", "..."], "first_seen": "2014-01-15", "last_seen": "2021-11-30"}
  ],
  "edges": [
    {"source": "E-VoidFox414", "target": "E-SomeOtherEntity", "relation_type": "TRANSACTED_WITH", "confidence": 0.9}
  ]
}
```

Save both as `entity_graph_output.json`. Fusion consumes the pairwise scores. Dashboard consumes the full node/edge list.

**Important — `persona_id` is the cross-module join key** (per the project's unified canonical schema): `aka_persona_ids` on each entity node is how Fusion maps this module's `entity_id`s back to the same `persona_id`s used by the Infra+Timing and Stylometry modules. Do not drop or rename `aka_persona_ids` — it's the only bridge between this module's collapsed view and the other modules' persona-level view.

---

## 5. Validation Checklist (run before handoff)

- [ ] Confirm every `SHARED_PGP_AND_WALLET` pair from the raw edges CSV maps to the same canonical entity — if any don't, fix the collapse logic.
- [ ] Pick a few entities with real `VOUCHED_FOR`/`TRANSACTED_WITH`/`CO_OCCURRED_IN_THREAD` connections in the raw data and confirm traversal correctly finds them.
- [ ] Deliberately test a 2–3 hop chain between two entities with no direct edge — confirm `all_simple_paths` surfaces the indirect connection with a sensible `path_confidence`.
- [ ] Spot-check that entities with no connections at all correctly return `connected: false`.

---

## 6. Tools/Libraries

- `networkx` — graph construction (`MultiDiGraph`), traversal, optional community detection
- `pandas` — CSV loading, grouping by handle
- `pyvis` — optional, for interactive graph visualization embeddable in the dashboard
- Plain JSON for output — no database dependency needed for the hackathon timeline

---

## 7. Handoff Notes (for whoever continues this — Saraa)

- Data files, canonical-collapse decision, and output JSON schema above are **locked** — don't redesign, extend from here.
- If build stops partway: whatever of `graph_engine.py` / `traversal.py` / `export.py` exists should still expose `get_graph()` as the stable interface — continue from that function even if internals are incomplete.
- Send `entity_graph_output.json` to whoever owns Fusion once ready — confirm `entity_id` ↔ `persona_id` mapping (via `aka_persona_ids`) is clear, since Fusion needs to map this module's entities back to the persona_ids used by Infra+Timing and Stylometry.
- Send the full node/edge export to the Dashboard owner for graph visualization.

---

## 8. What to Say in the Pitch (for this module — use this exact framing, not a "real-world actors" claim)

> "We built a synthetic entity graph modeled on real dark-web marketplace structure and naming conventions — 500 personas across 23 real historical marketplace names, with planted identity-linkage evidence (shared PGP keys, wallets, vouch/transaction/co-occurrence links) so we can measure real precision against known ground truth. We then used graph traversal — not a Graph Neural Network — to find indirect connections between entities, like a vouch-chain or shared transaction two hops away. For a hackathon PoC, explicit traversal over a well-structured graph gives the same investigative value a GNN would, while staying fast to build and fully explainable to an analyst reviewing the evidence."

**Do not** say the system "resolved real-world actors" or that PGP/wallet links are "evidence" of real identity — the linkage is planted synthetic ground truth used to validate the traversal/scoring logic, not a claim about real people. This distinction matters if a judge asks how the linkages were verified.

---

## 9. Non-Negotiables (do not change without team discussion)

1. Use only the `_ANON` data files for anything that goes into the GitHub repo, demo, or pitch deck.
2. `persona_id` (not `handle`) is the field other modules join on — preserve it through the collapse as `aka_persona_ids`.
3. Never reintroduce real dark-web vendor handles as node labels, even for "more realistic" demo data.
4. Canonical collapse is by shared `handle` (already anonymized/unique per real actor in this dataset) — don't redesign the collapse key.
