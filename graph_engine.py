"""
graph_engine.py — Entity Relationship Graph Engine
====================================================
Loads the ANON node/edge CSVs, collapses same-handle persona_ids into
canonical entity nodes, and builds a NetworkX MultiDiGraph.

Design decisions (locked per ANTIGRAVITY_BUILD_SPEC.md §3-4.1):
  - Canonical collapse by `handle` — one entity node per unique handle
  - SHARED_PGP_AND_WALLET edges are sanity-check only (not added as graph edges)
  - VOUCHED_FOR is directional; CO_OCCURRED_IN_THREAD and TRANSACTED_WITH
    are symmetric (edges added in both directions)
  - Parallel edges allowed (MultiDiGraph) — multiple independent edges
    between the same pair is itself a strength signal

Libraries: networkx, pandas
"""

import os
import sys
import pandas as pd
import networkx as nx
from pathlib import Path
from collections import defaultdict

# Force UTF-8 on Windows
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------
DATA_DIR = Path(__file__).parent / "data"
NODES_CSV = DATA_DIR / "module2_entity_graph_nodes_ANON.csv"
EDGES_CSV = DATA_DIR / "module2_entity_graph_edges_ANON.csv"

# Symmetric edge types: add in both directions on the DiGraph
SYMMETRIC_TYPES = {"CO_OCCURRED_IN_THREAD", "TRANSACTED_WITH"}


class EntityGraph:
    """
    Core graph engine for the Entity Relationship Graph module.

    Loads ANON CSVs, collapses personas into canonical entity nodes,
    and exposes a NetworkX MultiDiGraph for traversal.
    """

    def __init__(self, nodes_csv=None, edges_csv=None):
        self.nodes_csv = Path(nodes_csv) if nodes_csv else NODES_CSV
        self.edges_csv = Path(edges_csv) if edges_csv else EDGES_CSV

        # Raw data
        self.nodes_df = None
        self.edges_df = None

        # Canonical entity data
        self.entities = {}       # entity_id -> {aka_persona_ids, active_marketplaces, ...}
        self.persona_to_entity = {}  # persona_id -> entity_id
        self.handle_to_entity = {}   # handle -> entity_id

        # The graph
        self.graph = None  # nx.MultiDiGraph

        # Stats
        self.collapse_violations = 0

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------

    def load(self):
        """Load CSVs and build the full graph. Main entry point."""
        self._load_csvs()
        self._collapse_to_entities()
        self._sanity_check_shared_edges()
        self._build_graph()
        self._print_summary()
        return self

    def _load_csvs(self):
        """Load the two ANON CSV files."""
        print(f"[*] Loading {self.nodes_csv.name}...")
        self.nodes_df = pd.read_csv(self.nodes_csv)
        print(f"    {len(self.nodes_df)} persona records, "
              f"{self.nodes_df['handle'].nunique()} unique handles, "
              f"{self.nodes_df['marketplace'].nunique()} marketplaces")

        print(f"[*] Loading {self.edges_csv.name}...")
        self.edges_df = pd.read_csv(self.edges_csv)
        print(f"    {len(self.edges_df)} edges")

    # ------------------------------------------------------------------
    # Canonical Collapse
    # ------------------------------------------------------------------

    def _collapse_to_entities(self):
        """
        Group persona records by handle and collapse into canonical entities.

        Each entity gets:
          - entity_id: E-{handle}
          - aka_persona_ids: list of all persona_ids for this handle
          - active_marketplaces: list of marketplaces this handle appears on
          - pgp_fingerprint: the shared PGP key
          - wallet_address: the shared wallet
          - first_seen: earliest first_seen_date across personas
          - last_seen: latest last_seen_date across personas
        """
        print("\n[*] Collapsing personas into canonical entities...")

        grouped = self.nodes_df.groupby("handle")

        for handle, group in grouped:
            entity_id = f"E-{handle}"

            persona_ids = group["persona_id"].tolist()
            marketplaces = sorted(group["marketplace"].unique().tolist())
            first_seen = group["first_seen_date"].min()
            last_seen = group["last_seen_date"].max()

            # PGP and wallet should be identical within a handle group
            pgp_keys = group["pgp_fingerprint"].unique()
            wallets = group["wallet_address"].unique()

            if len(pgp_keys) > 1:
                print(f"    [WARN] Handle {handle} has {len(pgp_keys)} different PGP keys!")
            if len(wallets) > 1:
                print(f"    [WARN] Handle {handle} has {len(wallets)} different wallets!")

            self.entities[entity_id] = {
                "entity_id": entity_id,
                "handle": handle,
                "aka_persona_ids": persona_ids,
                "active_marketplaces": marketplaces,
                "pgp_fingerprint": pgp_keys[0],
                "wallet_address": wallets[0],
                "first_seen": first_seen,
                "last_seen": last_seen,
            }

            self.handle_to_entity[handle] = entity_id
            for pid in persona_ids:
                self.persona_to_entity[pid] = entity_id

        print(f"    Collapsed {len(self.nodes_df)} personas -> "
              f"{len(self.entities)} canonical entities")

    # ------------------------------------------------------------------
    # Sanity Check
    # ------------------------------------------------------------------

    def _sanity_check_shared_edges(self):
        """
        Verify every SHARED_PGP_AND_WALLET edge maps to the same canonical
        entity. If any doesn't, the collapse logic has a bug.
        """
        print("\n[*] Sanity check: SHARED_PGP_AND_WALLET edges...")
        shared_edges = self.edges_df[
            self.edges_df["relation_type"] == "SHARED_PGP_AND_WALLET"
        ]

        violations = 0
        for _, row in shared_edges.iterrows():
            src = row["source_persona_id"]
            tgt = row["target_persona_id"]
            ent_src = self.persona_to_entity.get(src)
            ent_tgt = self.persona_to_entity.get(tgt)

            if ent_src is None or ent_tgt is None:
                print(f"    [ERROR] Unknown persona_id in SHARED edge: {src} or {tgt}")
                violations += 1
            elif ent_src != ent_tgt:
                print(f"    [ERROR] SHARED edge spans entities: "
                      f"{ent_src} != {ent_tgt} (personas {src}, {tgt})")
                violations += 1

        self.collapse_violations = violations
        if violations == 0:
            print(f"    [OK] All {len(shared_edges)} SHARED_PGP_AND_WALLET edges "
                  f"map to same entity. Collapse is correct.")
        else:
            print(f"    [!!] {violations} violations found! Collapse logic has a bug.")

    # ------------------------------------------------------------------
    # Graph Construction
    # ------------------------------------------------------------------

    def _build_graph(self):
        """
        Build the NetworkX MultiDiGraph from canonical entities and
        non-SHARED edges.
        """
        print("\n[*] Building NetworkX MultiDiGraph...")

        G = nx.MultiDiGraph()

        # Add entity nodes
        for eid, data in self.entities.items():
            G.add_node(eid, **{
                "handle": data["handle"],
                "aka_persona_ids": data["aka_persona_ids"],
                "active_marketplaces": data["active_marketplaces"],
                "pgp_fingerprint": data["pgp_fingerprint"],
                "wallet_address": data["wallet_address"],
                "first_seen": data["first_seen"],
                "last_seen": data["last_seen"],
                "node_type": "entity",
            })

        # Add non-SHARED edges, remapped to entity_ids
        cross_edges = self.edges_df[
            self.edges_df["relation_type"] != "SHARED_PGP_AND_WALLET"
        ]

        added = 0
        skipped_self = 0
        for _, row in cross_edges.iterrows():
            src_pid = row["source_persona_id"]
            tgt_pid = row["target_persona_id"]
            rtype = row["relation_type"]
            conf = row["confidence_weight"]

            src_eid = self.persona_to_entity.get(src_pid)
            tgt_eid = self.persona_to_entity.get(tgt_pid)

            if src_eid is None or tgt_eid is None:
                continue

            # Skip self-loops (both personas belong to same entity)
            if src_eid == tgt_eid:
                skipped_self += 1
                continue

            # Add the edge
            G.add_edge(src_eid, tgt_eid,
                       relation_type=rtype,
                       confidence=conf,
                       source_persona_id=src_pid,
                       target_persona_id=tgt_pid)
            added += 1

            # For symmetric types, add reverse edge too
            if rtype in SYMMETRIC_TYPES:
                G.add_edge(tgt_eid, src_eid,
                           relation_type=rtype,
                           confidence=conf,
                           source_persona_id=tgt_pid,
                           target_persona_id=src_pid)
                added += 1

        self.graph = G

        print(f"    Entity nodes:    {G.number_of_nodes()}")
        print(f"    Cross edges:     {added} (including symmetric duplicates)")
        print(f"    Skipped self:    {skipped_self}")

    # ------------------------------------------------------------------
    # Public Interface
    # ------------------------------------------------------------------

    def get_graph(self) -> nx.MultiDiGraph:
        """
        Return the built graph. This is the stable interface other
        modules depend on.
        """
        if self.graph is None:
            self.load()
        return self.graph

    def get_entity(self, entity_id: str) -> dict:
        """Get entity data by entity_id."""
        return self.entities.get(entity_id)

    def get_entity_by_handle(self, handle: str) -> dict:
        """Get entity data by handle name."""
        eid = self.handle_to_entity.get(handle)
        if eid:
            return self.entities.get(eid)
        return None

    def get_entity_by_persona(self, persona_id: str) -> dict:
        """Get entity data by persona_id."""
        eid = self.persona_to_entity.get(persona_id)
        if eid:
            return self.entities.get(eid)
        return None

    def get_all_entities(self) -> dict:
        """Return all entities."""
        return self.entities

    def get_entity_ids(self) -> list:
        """Return all entity_ids."""
        return list(self.entities.keys())

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------

    def _print_summary(self):
        """Print build summary."""
        G = self.graph
        edge_types = defaultdict(int)
        for u, v, data in G.edges(data=True):
            edge_types[data.get("relation_type", "unknown")] += 1

        # Count connected vs isolated
        undirected = G.to_undirected()
        components = list(nx.connected_components(undirected))
        isolated = sum(1 for c in components if len(c) == 1)

        print(f"""
{'='*60}
GRAPH ENGINE SUMMARY
{'='*60}

  Canonical entities:    {G.number_of_nodes()}
  Total graph edges:     {G.number_of_edges()}
  Collapse violations:   {self.collapse_violations}

  Edge type breakdown:
    VOUCHED_FOR:             {edge_types.get('VOUCHED_FOR', 0)}
    CO_OCCURRED_IN_THREAD:   {edge_types.get('CO_OCCURRED_IN_THREAD', 0)}
    TRANSACTED_WITH:         {edge_types.get('TRANSACTED_WITH', 0)}

  Connected components:  {len(components)}
  Isolated entities:     {isolated}
  Largest component:     {max(len(c) for c in components)} entities
{'='*60}
""")


# ---------------------------------------------------------------------------
# Standalone test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    engine = EntityGraph()
    engine.load()
    G = engine.get_graph()

    # Quick spot-check
    sample = list(engine.entities.values())[:3]
    print("Sample entities:")
    for e in sample:
        print(f"  {e['entity_id']}: {len(e['aka_persona_ids'])} personas, "
              f"markets={e['active_marketplaces']}")
