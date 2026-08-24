"""
traversal.py — Multi-Hop Graph Traversal Engine
=================================================
Finds connections between canonical entities via multi-hop paths,
computes path_confidence and graph_link_strength scores.

Per ANTIGRAVITY_BUILD_SPEC.md §4.2:
  - Traverses the directed MultiDiGraph: VOUCHED_FOR is directional (A -> B),
    while CO_OCCURRED_IN_THREAD and TRANSACTED_WITH are symmetric (bidirectional).
  - path_confidence: multiply confidence_weight along each edge in a path
  - graph_link_strength: combine path count + strongest path confidence
  - Supports up to N=3 hop traversals (deeper paths get noisy)

Libraries: networkx
"""

import sys
import networkx as nx
from collections import defaultdict
from typing import List, Tuple, Optional, Dict, Any

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")


class GraphTraversal:
    """
    Multi-hop path finding and scoring on the collapsed entity graph.
    """

    def __init__(self, graph: nx.MultiDiGraph):
        """
        Args:
            graph: The MultiDiGraph from EntityGraph.get_graph()
        """
        self.graph = graph
        # Undirected view used strictly for community detection and component reachability checks
        self._undirected = graph.to_undirected()

    # ------------------------------------------------------------------
    # Core Path Finding
    # ------------------------------------------------------------------

    def find_path(
        self,
        source: str,
        target: str,
        cutoff: int = 3,
    ) -> Dict[str, Any]:
        """
        Find the shortest path and all simple paths between two entities.
        Queries the directed MultiDiGraph to enforce VOUCHED_FOR directionality.

        Returns dict with:
          - connected: bool
          - shortest_path: list of entity_ids
          - path_length: int
          - path_confidence: float (product of edge confidences on shortest path)
          - all_paths: list of paths (up to cutoff hops)
          - graph_link_strength: float
          - evidence_path: list of edge details on the shortest path
        """
        if source not in self.graph or target not in self.graph:
            return {
                "entity_id_a": source,
                "entity_id_b": target,
                "connected": False,
                "shortest_path": [],
                "path_length": -1,
                "path_confidence": 0.0,
                "graph_link_strength": 0.0,
                "all_paths_count": 0,
                "evidence_path": [],
            }

        # Check connectivity on directed MultiDiGraph (respecting edge directionality)
        try:
            if not nx.has_path(self.graph, source, target):
                return {
                    "entity_id_a": source,
                    "entity_id_b": target,
                    "connected": False,
                    "shortest_path": [],
                    "path_length": -1,
                    "path_confidence": 0.0,
                    "graph_link_strength": 0.0,
                    "all_paths_count": 0,
                    "evidence_path": [],
                }
        except nx.NetworkXError:
            return {
                "entity_id_a": source,
                "entity_id_b": target,
                "connected": False,
                "shortest_path": [],
                "path_length": -1,
                "path_confidence": 0.0,
                "graph_link_strength": 0.0,
                "all_paths_count": 0,
                "evidence_path": [],
            }

        # Find shortest path on directed MultiDiGraph
        try:
            shortest = nx.shortest_path(self.graph, source, target)
        except nx.NetworkXNoPath:
            return {
                "entity_id_a": source,
                "entity_id_b": target,
                "connected": False,
                "shortest_path": [],
                "path_length": -1,
                "path_confidence": 0.0,
                "graph_link_strength": 0.0,
                "all_paths_count": 0,
                "evidence_path": [],
            }

        # Compute path confidence for shortest path
        sp_confidence = self.path_confidence(shortest)
        evidence = self._build_evidence_path(shortest)

        # Find all simple paths (capped at cutoff, using directed MultiDiGraph)
        try:
            all_paths = list(nx.all_simple_paths(
                self.graph, source, target, cutoff=cutoff
            ))
        except nx.NetworkXError:
            all_paths = [shortest]

        # Compute graph_link_strength
        link_strength = self.graph_link_strength_from_paths(all_paths)

        return {
            "entity_id_a": source,
            "entity_id_b": target,
            "connected": True,
            "shortest_path": shortest,
            "path_length": len(shortest) - 1,
            "path_confidence": sp_confidence,
            "graph_link_strength": link_strength,
            "all_paths_count": len(all_paths),
            "evidence_path": evidence,
        }

    # ------------------------------------------------------------------
    # Confidence Scoring
    # ------------------------------------------------------------------

    def path_confidence(self, path: List[str]) -> float:
        """
        Compute confidence of a path by multiplying edge confidences.

        Confidence naturally decays with hops — explainable, simple.
        For multi-edges between the same pair, use the highest confidence.
        """
        if len(path) < 2:
            return 0.0

        confidence = 1.0
        for i in range(len(path) - 1):
            u, v = path[i], path[i + 1]
            edge_conf = self._best_edge_confidence(u, v)
            confidence *= edge_conf

        return round(confidence, 4)

    def graph_link_strength(self, source: str, target: str, cutoff: int = 3) -> float:
        """
        Compute overall link strength between two entities.

        Combines:
          - Number of distinct paths (more paths = stronger evidence)
          - Strongest single path's confidence

        Formula: strength = best_path_conf * (1 + log2(num_paths) * 0.1)
                 capped at 1.0
        """
        try:
            all_paths = list(nx.all_simple_paths(
                self.graph, source, target, cutoff=cutoff
            ))
        except (nx.NetworkXError, nx.NodeNotFound):
            return 0.0

        if not all_paths:
            return 0.0

        return self.graph_link_strength_from_paths(all_paths)

    def graph_link_strength_from_paths(self, paths: List[List[str]]) -> float:
        """Compute link strength from a pre-computed list of paths."""
        if not paths:
            return 0.0

        # Compute confidence for each path
        confidences = [self.path_confidence(p) for p in paths]
        best_conf = max(confidences)
        num_paths = len(paths)

        # More independent paths = stronger evidence
        import math
        strength = best_conf * (1.0 + math.log2(max(num_paths, 1)) * 0.1)
        return round(min(strength, 1.0), 4)

    # ------------------------------------------------------------------
    # Neighborhood / Component Discovery
    # ------------------------------------------------------------------

    def find_connections(
        self,
        entity_id: str,
        max_hops: int = 3,
    ) -> List[Dict[str, Any]]:
        """
        Find all entities reachable from entity_id within max_hops.
        Traverses directed successors in self.graph to respect VOUCHED_FOR directionality.

        Returns list of dicts with entity_id, distance, path_confidence.
        """
        if entity_id not in self.graph:
            return []

        connections = []
        visited = {entity_id}

        # BFS up to max_hops using directed graph successors
        current_layer = {entity_id}
        for hop in range(1, max_hops + 1):
            next_layer = set()
            for node in current_layer:
                for neighbor in self.graph.successors(node):
                    if neighbor not in visited:
                        visited.add(neighbor)
                        next_layer.add(neighbor)

                        # Get path confidence along directed path
                        try:
                            path = nx.shortest_path(
                                self.graph, entity_id, neighbor
                            )
                            conf = self.path_confidence(path)
                        except nx.NetworkXNoPath:
                            conf = 0.0

                        connections.append({
                            "entity_id": neighbor,
                            "distance": hop,
                            "path_confidence": conf,
                        })
            current_layer = next_layer

        # Sort by confidence descending
        connections.sort(key=lambda x: -x["path_confidence"])
        return connections

    def get_connected_component(self, entity_id: str) -> set:
        """
        Get all entities in the same connected component as entity_id.
        Uses undirected view for component membership.
        """
        if entity_id not in self._undirected:
            return set()
        return nx.node_connected_component(self._undirected, entity_id)

    # ------------------------------------------------------------------
    # Community Detection (Optional Stretch)
    # ------------------------------------------------------------------

    def detect_communities(self) -> List[set]:
        """
        Run Louvain community detection on the entity graph.
        Uses undirected view for community partitioning.

        Returns list of sets, each set = community of entity_ids.
        """
        try:
            communities = nx.community.louvain_communities(
                self._undirected,
                seed=42,
            )
            return [set(c) for c in communities]
        except Exception as e:
            print(f"    [WARN] Community detection failed: {e}")
            return []

    # ------------------------------------------------------------------
    # Internal Helpers
    # ------------------------------------------------------------------

    def _best_edge_confidence(self, u: str, v: str) -> float:
        """
        Get the highest confidence across all parallel edges from u to v.
        """
        best = 0.0

        if self.graph.has_edge(u, v):
            for key, data in self.graph[u][v].items():
                conf = data.get("confidence", 0.0)
                if conf > best:
                    best = conf

        return best

    def _build_evidence_path(self, path: List[str]) -> List[dict]:
        """Build a detailed evidence trail for a path."""
        evidence = []
        for i in range(len(path) - 1):
            u, v = path[i], path[i + 1]
            edge_data = self._get_best_edge_data(u, v)
            evidence.append({
                "from": u,
                "to": v,
                "relation_type": edge_data.get("relation_type", "unknown"),
                "confidence": edge_data.get("confidence", 0.0),
            })
        return evidence

    def _get_best_edge_data(self, u: str, v: str) -> dict:
        """Get the edge data for the highest-confidence edge from u to v."""
        best = {"confidence": 0.0}

        if self.graph.has_edge(u, v):
            for key, data in self.graph[u][v].items():
                if data.get("confidence", 0.0) > best["confidence"]:
                    best = dict(data)

        return best

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------

    def get_graph_stats(self) -> dict:
        """Return summary statistics about the graph."""
        components = list(nx.connected_components(self._undirected))
        return {
            "total_entities": self.graph.number_of_nodes(),
            "total_edges": self.graph.number_of_edges(),
            "connected_components": len(components),
            "largest_component": max(len(c) for c in components) if components else 0,
            "isolated_entities": sum(1 for c in components if len(c) == 1),
        }


# ---------------------------------------------------------------------------
# Standalone test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    from graph_engine import EntityGraph

    # Build graph
    engine = EntityGraph()
    engine.load()
    G = engine.get_graph()

    # Create traversal engine
    traversal = GraphTraversal(G)

    # Show stats
    stats = traversal.get_graph_stats()
    print(f"Graph stats: {stats}")

    # Find a pair of connected entities and test traversal
    entities = engine.get_entity_ids()
    tested = 0
    for eid in entities[:20]:
        connections = traversal.find_connections(eid, max_hops=2)
        if connections:
            target = connections[0]["entity_id"]
            result = traversal.find_path(eid, target)
            if result["connected"]:
                print(f"\nPath: {eid} -> {target}")
                print(f"  Length: {result['path_length']}")
                print(f"  Confidence: {result['path_confidence']}")
                print(f"  Link strength: {result['graph_link_strength']}")
                print(f"  Evidence: {result['evidence_path']}")
                tested += 1
                if tested >= 3:
                    break

    # Test community detection
    communities = traversal.detect_communities()
    print(f"\nCommunities detected: {len(communities)}")
    for i, c in enumerate(communities[:5]):
        print(f"  Community {i}: {len(c)} entities")
