"""
identity_resolver.py — Identity Cluster Resolution Engine
============================================================
Detects shared PGP keys / wallets across handles and proposes
SAME_ACTOR_AS edges with confidence scores.

Confidence scoring:
  - Shared PGP key:             0.90
  - Shared wallet:              0.85
  - Both PGP + wallet:          0.97  (noisy-OR)
  - Shared trust-link pattern:  0.30  (weak signal)
  - Combined:  1 - ∏(1 - score_i)    (noisy-OR)
"""

from itertools import combinations
from collections import defaultdict
from graph_engine import EntityGraph


# ---------------------------------------------------------------------------
# Confidence weights
# ---------------------------------------------------------------------------

CONFIDENCE_SHARED_PGP = 0.90
CONFIDENCE_SHARED_WALLET = 0.85
CONFIDENCE_SHARED_TRUST_PATTERN = 0.30


def noisy_or(scores: list) -> float:
    """
    Combine independent confidence scores using noisy-OR:
      P(match) = 1 - ∏(1 - p_i)
    
    This is the standard fusion formula for combining independent
    binary signals with known false-negative rates.
    """
    if not scores:
        return 0.0
    product = 1.0
    for s in scores:
        product *= (1.0 - s)
    return round(1.0 - product, 4)


# ---------------------------------------------------------------------------
# Cluster resolution
# ---------------------------------------------------------------------------

class IdentityResolver:
    """
    Analyzes the entity graph to find candidate identity clusters.
    
    Walks the graph looking for handles that share hard identifiers
    (PGP keys, wallets) and proposes SAME_ACTOR_AS edges with
    confidence scores. Never auto-merges — always outputs a score.
    """

    def __init__(self, graph: EntityGraph):
        self.graph = graph
        self.candidate_pairs = []     # list of (handle_a, handle_b, confidence, evidence)
        self.clusters = []            # list of resolved clusters

    def resolve(self) -> list:
        """
        Run the full identity resolution pipeline.
        
        Returns:
            List of cluster dicts, each containing:
              - cluster_id
              - handles
              - confidence
              - evidence
              - shared_identifiers
        """
        print("[*] Running identity resolution…")
        self.candidate_pairs = []
        self.clusters = []

        # Step 1: Find PGP-key sharing
        pgp_shares = self._detect_shared_pgp()

        # Step 2: Find wallet sharing
        wallet_shares = self._detect_shared_wallets()

        # Step 3: Find trust-link pattern overlap
        trust_shares = self._detect_trust_patterns()

        # Step 4: Merge all signals into candidate pairs
        self._merge_signals(pgp_shares, wallet_shares, trust_shares)

        # Step 5: Build clusters from pairwise matches
        self._build_clusters()

        # Step 6: Add SAME_ACTOR_AS edges to the graph
        self._inject_edges()

        print(f"[OK] Identity resolution complete:")
        print(f"    - {len(self.candidate_pairs)} candidate pairs found")
        print(f"    - {len(self.clusters)} identity clusters formed")

        return self.clusters

    # ------------------------------------------------------------------
    # Signal detectors
    # ------------------------------------------------------------------

    def _detect_shared_pgp(self) -> dict:
        """
        Detect handles sharing PGP keys.
        Returns: { (handle_a, handle_b): { fingerprint, confidence } }
        """
        shared = {}
        pgp_overlaps = self.graph.get_handles_sharing_pgp()

        for fingerprint, handles in pgp_overlaps.items():
            for a, b in combinations(sorted(handles), 2):
                pair = (a, b)
                shared[pair] = {
                    "type": "shared_pgp",
                    "fingerprint": fingerprint,
                    "confidence": CONFIDENCE_SHARED_PGP,
                }

        if shared:
            print(f"    [PGP] Found {len(shared)} handle pairs sharing PGP keys")
        return shared

    def _detect_shared_wallets(self) -> dict:
        """
        Detect handles sharing wallet addresses.
        Returns: { (handle_a, handle_b): { address, confidence } }
        """
        shared = {}
        wallet_overlaps = self.graph.get_handles_sharing_wallet()

        for address, handles in wallet_overlaps.items():
            for a, b in combinations(sorted(handles), 2):
                pair = (a, b)
                shared[pair] = {
                    "type": "shared_wallet",
                    "address": address,
                    "confidence": CONFIDENCE_SHARED_WALLET,
                }

        if shared:
            print(f"    [WAL] Found {len(shared)} handle pairs sharing wallets")
        return shared

    def _detect_trust_patterns(self) -> dict:
        """
        Detect handles with suspicious trust-link overlap.
        
        Two handles are flagged if they share a significant number
        of common trust neighbors (Jaccard similarity > threshold).
        
        Returns: { (handle_a, handle_b): { jaccard, confidence } }
        """
        shared = {}
        all_handles = self.graph.get_all_handles()

        # Build neighbor sets for each handle
        neighbor_sets = {}
        for handle in all_handles:
            neighbors = self.graph.get_trust_neighbors(handle)
            neighbor_set = set(n["handle"] for n in neighbors)
            if neighbor_set:
                neighbor_sets[handle] = neighbor_set

        # Compare pairs (only handles with trust neighbors)
        handles_with_trust = list(neighbor_sets.keys())
        for a, b in combinations(handles_with_trust, 2):
            set_a = neighbor_sets[a]
            set_b = neighbor_sets[b]

            # Jaccard similarity
            intersection = set_a & set_b
            union = set_a | set_b

            if not union:
                continue

            jaccard = len(intersection) / len(union)

            # Only flag if Jaccard > 0.4 (meaningful overlap)
            if jaccard > 0.4 and len(intersection) >= 2:
                pair = tuple(sorted([a, b]))
                shared[pair] = {
                    "type": "shared_trust_pattern",
                    "jaccard_similarity": round(jaccard, 4),
                    "common_neighbors": list(intersection),
                    "confidence": CONFIDENCE_SHARED_TRUST_PATTERN,
                }

        if shared:
            print(f"    [TRS] Found {len(shared)} handle pairs with overlapping trust patterns")
        return shared

    # ------------------------------------------------------------------
    # Signal fusion
    # ------------------------------------------------------------------

    def _merge_signals(self, pgp_shares: dict, wallet_shares: dict,
                       trust_shares: dict):
        """
        Merge all detected signals into candidate pairs with combined
        confidence scores using noisy-OR.
        """
        all_pairs = set()
        all_pairs.update(pgp_shares.keys())
        all_pairs.update(wallet_shares.keys())
        all_pairs.update(trust_shares.keys())

        for pair in all_pairs:
            scores = []
            evidence = []

            if pair in pgp_shares:
                scores.append(pgp_shares[pair]["confidence"])
                evidence.append({
                    "signal": "shared_pgp_key",
                    "detail": pgp_shares[pair].get("fingerprint", ""),
                    "raw_confidence": pgp_shares[pair]["confidence"],
                })

            if pair in wallet_shares:
                scores.append(wallet_shares[pair]["confidence"])
                evidence.append({
                    "signal": "shared_wallet",
                    "detail": wallet_shares[pair].get("address", ""),
                    "raw_confidence": wallet_shares[pair]["confidence"],
                })

            if pair in trust_shares:
                scores.append(trust_shares[pair]["confidence"])
                evidence.append({
                    "signal": "shared_trust_pattern",
                    "detail": f"Jaccard={trust_shares[pair].get('jaccard_similarity', 0)}",
                    "common_neighbors": trust_shares[pair].get("common_neighbors", []),
                    "raw_confidence": trust_shares[pair]["confidence"],
                })

            combined = noisy_or(scores)

            self.candidate_pairs.append({
                "handle_a": pair[0],
                "handle_b": pair[1],
                "confidence": combined,
                "evidence": evidence,
                "signal_count": len(scores),
            })

        # Sort by confidence descending
        self.candidate_pairs.sort(key=lambda x: x["confidence"], reverse=True)

    # ------------------------------------------------------------------
    # Cluster building
    # ------------------------------------------------------------------

    def _build_clusters(self):
        """
        Build identity clusters from pairwise candidate matches
        using Union-Find (disjoint set).
        """
        parent = {}

        def find(x):
            if x not in parent:
                parent[x] = x
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        def union(x, y):
            px, py = find(x), find(y)
            if px != py:
                parent[px] = py

        # Union all candidate pairs
        for pair in self.candidate_pairs:
            union(pair["handle_a"], pair["handle_b"])

        # Group handles by cluster root
        cluster_map = defaultdict(set)
        for pair in self.candidate_pairs:
            root = find(pair["handle_a"])
            cluster_map[root].add(pair["handle_a"])
            cluster_map[root].add(pair["handle_b"])

        # Build cluster records
        for i, (root, members) in enumerate(cluster_map.items()):
            members_sorted = sorted(members)

            # Collect all evidence and shared identifiers for this cluster
            cluster_evidence = []
            shared_pgp = set()
            shared_wallets = set()
            pair_confidences = []

            for pair in self.candidate_pairs:
                if pair["handle_a"] in members and pair["handle_b"] in members:
                    cluster_evidence.extend(pair["evidence"])
                    pair_confidences.append(pair["confidence"])
                    for ev in pair["evidence"]:
                        if ev["signal"] == "shared_pgp_key":
                            shared_pgp.add(ev["detail"])
                        elif ev["signal"] == "shared_wallet":
                            shared_wallets.add(ev["detail"])

            # Cluster confidence = max pairwise confidence
            cluster_confidence = max(pair_confidences) if pair_confidences else 0.0

            self.clusters.append({
                "cluster_id": f"C{i+1:03d}",
                "handles": members_sorted,
                "confidence": cluster_confidence,
                "shared_identifiers": {
                    "pgp_keys": list(shared_pgp),
                    "wallets": list(shared_wallets),
                },
                "evidence": cluster_evidence,
                "handle_count": len(members_sorted),
            })

        self.clusters.sort(key=lambda c: c["confidence"], reverse=True)

    # ------------------------------------------------------------------
    # Edge injection
    # ------------------------------------------------------------------

    def _inject_edges(self):
        """Add SAME_ACTOR_AS edges to the graph for all candidate pairs."""
        for pair in self.candidate_pairs:
            self.graph.add_same_actor_edge(
                handle_a=pair["handle_a"],
                handle_b=pair["handle_b"],
                confidence=pair["confidence"],
                evidence=pair["evidence"],
            )

    # ------------------------------------------------------------------
    # Accessors
    # ------------------------------------------------------------------

    def get_clusters(self) -> list:
        """Return all resolved identity clusters."""
        return self.clusters

    def get_candidate_pairs(self) -> list:
        """Return all candidate handle pairs with confidence scores."""
        return self.candidate_pairs

    def get_cluster_for_handle(self, username: str) -> dict:
        """Find the cluster containing a given handle, if any."""
        for cluster in self.clusters:
            if username in cluster["handles"]:
                return cluster
        return None
