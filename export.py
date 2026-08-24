"""
export.py — Entity Graph Export Module
========================================
Produces entity_graph_output.json in the locked schema defined in
ANTIGRAVITY_BUILD_SPEC.md §4.3.

Two sections in the output:
  1. Pairwise scoring (for Fusion module — per connected entity pair)
  2. Full graph export (for Dashboard — all nodes and edges)

The `aka_persona_ids` field is preserved on every entity node — this is
the cross-module join key that Fusion uses to map entity_ids back to the
persona_ids used by Infra+Timing and Stylometry modules.
"""

import json
import sys
import time
from pathlib import Path
from typing import List, Dict, Any

import networkx as nx

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

DATA_DIR = Path(__file__).parent / "data"
OUTPUT_PATH = DATA_DIR / "entity_graph_output.json"


def export_graph(engine, traversal, output_path=None, max_pairs=500):
    """
    Export the full entity graph output.

    Args:
        engine: EntityGraph instance (loaded)
        traversal: GraphTraversal instance
        output_path: Path to write output JSON (default: data/entity_graph_output.json)
        max_pairs: Max number of pairwise scores to compute (for performance)

    Returns:
        Path to the written file
    """
    output_path = Path(output_path) if output_path else OUTPUT_PATH

    print("\n[*] Exporting entity graph output...")

    G = engine.get_graph()
    entities = engine.get_all_entities()

    # ------------------------------------------------------------------
    # Section 1: Pairwise scoring (for Fusion module)
    # ------------------------------------------------------------------
    print("    Computing pairwise scores...")
    pairwise_scores = _compute_pairwise_scores(engine, traversal, max_pairs)
    print(f"    {len(pairwise_scores)} pairwise connections scored")

    # ------------------------------------------------------------------
    # Section 2: Full graph export (for Dashboard)
    # ------------------------------------------------------------------
    print("    Building full graph export...")
    nodes_export = _build_nodes_export(entities)
    edges_export = _build_edges_export(G)

    # ------------------------------------------------------------------
    # Assemble output
    # ------------------------------------------------------------------
    output = {
        "metadata": {
            "module": "entity_graph",
            "version": "2.0",
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "description": "Entity Relationship Graph — canonical entity collapse + multi-hop traversal",
        },
        "pairwise_scores": pairwise_scores,
        "graph": {
            "nodes": nodes_export,
            "edges": edges_export,
        },
        "statistics": {
            "total_entities": len(entities),
            "total_personas": sum(
                len(e["aka_persona_ids"]) for e in entities.values()
            ),
            "total_graph_edges": G.number_of_edges(),
            "total_pairwise_connections": len(pairwise_scores),
            "connected_components": traversal.get_graph_stats()["connected_components"],
            "isolated_entities": traversal.get_graph_stats()["isolated_entities"],
        },
    }

    # Write
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, default=str)

    size_mb = output_path.stat().st_size / (1024 * 1024)
    print(f"\n[OK] Export saved to {output_path} ({size_mb:.1f} MB)")
    print(f"     Pairwise scores: {len(pairwise_scores)}")
    print(f"     Nodes: {len(nodes_export)}")
    print(f"     Edges: {len(edges_export)}")

    return output_path


def _compute_pairwise_scores(engine, traversal, max_pairs=500) -> List[Dict]:
    """
    Compute pairwise scores for connected entity pairs.

    Strategy: for each entity, find its connections within 2-3 hops,
    then compute full path details. Capped at max_pairs for performance.
    """
    G = engine.get_graph()
    entities = engine.get_entity_ids()
    scored_pairs = set()
    results = []

    for eid in entities:
        if len(results) >= max_pairs:
            break

        connections = traversal.find_connections(eid, max_hops=3)
        for conn in connections[:10]:  # Top 10 per entity
            target = conn["entity_id"]
            pair_key = tuple(sorted([eid, target]))
            if pair_key in scored_pairs:
                continue
            scored_pairs.add(pair_key)

            result = traversal.find_path(eid, target, cutoff=3)
            if result["connected"]:
                results.append({
                    "entity_id_a": result["entity_id_a"],
                    "entity_id_b": result["entity_id_b"],
                    "connected": True,
                    "shortest_path": result["shortest_path"],
                    "path_length": result["path_length"],
                    "path_confidence": result["path_confidence"],
                    "graph_link_strength": result["graph_link_strength"],
                    "evidence_path": result["evidence_path"],
                })

            if len(results) >= max_pairs:
                break

    # Sort by link strength descending
    results.sort(key=lambda x: -x["graph_link_strength"])
    return results


def _build_nodes_export(entities: Dict) -> List[Dict]:
    """Build the nodes array for the full graph export."""
    nodes = []
    for eid, data in entities.items():
        nodes.append({
            "entity_id": eid,
            "handle": data["handle"],
            "aka_persona_ids": data["aka_persona_ids"],
            "active_marketplaces": data["active_marketplaces"],
            "pgp_fingerprint": data["pgp_fingerprint"],
            "wallet_address": data["wallet_address"],
            "first_seen": data["first_seen"],
            "last_seen": data["last_seen"],
        })
    return nodes


def _build_edges_export(G: nx.MultiDiGraph) -> List[Dict]:
    """
    Build the edges array for the full graph export.
    De-duplicate symmetric edges (keep one per undirected pair per type).
    """
    seen = set()
    edges = []
    for u, v, data in G.edges(data=True):
        rtype = data.get("relation_type", "unknown")
        pair_key = (tuple(sorted([u, v])), rtype)
        if pair_key in seen:
            continue
        seen.add(pair_key)
        edges.append({
            "source": u,
            "target": v,
            "relation_type": rtype,
            "confidence": data.get("confidence", 0.0),
        })
    return edges


# ---------------------------------------------------------------------------
# Standalone entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    from graph_engine import EntityGraph
    from traversal import GraphTraversal

    engine = EntityGraph()
    engine.load()
    G = engine.get_graph()

    trav = GraphTraversal(G)
    export_graph(engine, trav)
