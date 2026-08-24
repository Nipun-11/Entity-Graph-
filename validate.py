"""
validate.py — Validation Checklist Runner
============================================
Runs the validation checks from ANTIGRAVITY_BUILD_SPEC.md §5:

  1. Confirm every SHARED_PGP_AND_WALLET pair maps to the same entity
  2. Spot-check known connections (VOUCHED_FOR/TRANSACTED_WITH/CO_OCCURRED)
  3. Test a 2-3 hop indirect path with sensible path_confidence
  4. Confirm isolated entities return connected: false
  5. Verify aka_persona_ids completeness
"""

import sys
import pandas as pd
import networkx as nx
from pathlib import Path

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

DATA_DIR = Path(__file__).parent / "data"


def run_validation(engine, traversal):
    """
    Run all validation checks. Returns (passed, failed, results_list).
    """
    print(f"\n{'='*60}")
    print("VALIDATION CHECKLIST")
    print(f"{'='*60}\n")

    passed = 0
    failed = 0
    results = []

    # ------------------------------------------------------------------
    # Check 1: SHARED_PGP_AND_WALLET collapse sanity
    # ------------------------------------------------------------------
    print("[Check 1] SHARED_PGP_AND_WALLET collapse sanity...")
    violations = engine.collapse_violations
    if violations == 0:
        print(f"    [PASS] 0 violations — all shared edges map to same entity")
        passed += 1
        results.append(("SHARED_PGP_AND_WALLET collapse", "PASS", "0 violations"))
    else:
        print(f"    [FAIL] {violations} violations found")
        failed += 1
        results.append(("SHARED_PGP_AND_WALLET collapse", "FAIL", f"{violations} violations"))

    # ------------------------------------------------------------------
    # Check 2: Spot-check known connections
    # ------------------------------------------------------------------
    print("\n[Check 2] Spot-check known cross-entity connections...")
    G = engine.get_graph()
    edges_df = engine.edges_df

    # Get 5 VOUCHED_FOR edges that connect different entities
    cross_edges = edges_df[edges_df["relation_type"] != "SHARED_PGP_AND_WALLET"]
    sample_edges = cross_edges.head(10)

    checks_ok = 0
    checks_total = 0
    for _, row in sample_edges.iterrows():
        src_eid = engine.persona_to_entity.get(row["source_persona_id"])
        tgt_eid = engine.persona_to_entity.get(row["target_persona_id"])
        if src_eid and tgt_eid and src_eid != tgt_eid:
            checks_total += 1
            result = traversal.find_path(src_eid, tgt_eid)
            if result["connected"]:
                checks_ok += 1
            else:
                print(f"    [WARN] Known edge {src_eid} -> {tgt_eid} "
                      f"({row['relation_type']}) not found in traversal")

    if checks_total > 0 and checks_ok == checks_total:
        print(f"    [PASS] {checks_ok}/{checks_total} known connections found via traversal")
        passed += 1
        results.append(("Known connection spot-check", "PASS",
                        f"{checks_ok}/{checks_total} found"))
    elif checks_total == 0:
        print(f"    [SKIP] No cross-entity edges found to test")
        results.append(("Known connection spot-check", "SKIP", "No edges to test"))
    else:
        print(f"    [FAIL] Only {checks_ok}/{checks_total} known connections found")
        failed += 1
        results.append(("Known connection spot-check", "FAIL",
                        f"{checks_ok}/{checks_total} found"))

    # ------------------------------------------------------------------
    # Check 3: 2-3 hop indirect path test
    # ------------------------------------------------------------------
    print("\n[Check 3] Multi-hop indirect path test...")
    found_indirect = False

    entities = engine.get_entity_ids()
    for eid in entities[:50]:
        connections = traversal.find_connections(eid, max_hops=3)
        for conn in connections:
            if conn["distance"] >= 2:
                result = traversal.find_path(eid, conn["entity_id"], cutoff=3)
                if result["connected"] and result["path_length"] >= 2:
                    print(f"    Found {result['path_length']}-hop path: "
                          f"{' -> '.join(result['shortest_path'])}")
                    print(f"    path_confidence: {result['path_confidence']}")
                    print(f"    graph_link_strength: {result['graph_link_strength']}")

                    # Verify confidence decays (should be < 1.0 for multi-hop)
                    if result["path_confidence"] < 1.0:
                        print(f"    Confidence decays correctly with hops")
                        found_indirect = True
                        break
        if found_indirect:
            break

    if found_indirect:
        print(f"    [PASS] Multi-hop path found with decaying confidence")
        passed += 1
        results.append(("Multi-hop indirect path", "PASS",
                        "Confidence decays correctly"))
    else:
        print(f"    [FAIL] No multi-hop indirect paths found")
        failed += 1
        results.append(("Multi-hop indirect path", "FAIL", "No paths found"))

    # ------------------------------------------------------------------
    # Check 4: Isolated entity returns connected: false
    # ------------------------------------------------------------------
    print("\n[Check 4] Isolated entity test...")
    undirected = G.to_undirected()
    components = list(nx.connected_components(undirected))
    isolated = [list(c)[0] for c in components if len(c) == 1]

    if isolated:
        iso_eid = isolated[0]
        # Pick a non-isolated entity
        non_iso = [list(c)[0] for c in components if len(c) > 1]
        if non_iso:
            target = non_iso[0]
            result = traversal.find_path(iso_eid, target)
            if not result["connected"]:
                print(f"    [PASS] Isolated entity {iso_eid} correctly returns "
                      f"connected=false")
                passed += 1
                results.append(("Isolated entity test", "PASS",
                                f"{iso_eid} -> connected=false"))
            else:
                print(f"    [FAIL] Isolated entity {iso_eid} incorrectly "
                      f"returns connected=true")
                failed += 1
                results.append(("Isolated entity test", "FAIL",
                                f"{iso_eid} returned connected=true"))
        else:
            print(f"    [SKIP] No non-isolated entities to test against")
            results.append(("Isolated entity test", "SKIP", "No test pair"))
    else:
        print(f"    [INFO] No isolated entities in graph — all connected")
        print(f"    [PASS] (no isolated entities to incorrectly connect)")
        passed += 1
        results.append(("Isolated entity test", "PASS",
                        "No isolated entities exist"))

    # ------------------------------------------------------------------
    # Check 5: aka_persona_ids completeness
    # ------------------------------------------------------------------
    print("\n[Check 5] aka_persona_ids completeness...")
    nodes_df = engine.nodes_df
    all_persona_ids = set(nodes_df["persona_id"].unique())

    mapped_pids = set()
    for entity_data in engine.entities.values():
        mapped_pids.update(entity_data["aka_persona_ids"])

    missing = all_persona_ids - mapped_pids
    extra = mapped_pids - all_persona_ids

    if not missing and not extra:
        print(f"    [PASS] All {len(all_persona_ids)} persona_ids mapped to entities")
        passed += 1
        results.append(("aka_persona_ids completeness", "PASS",
                        f"{len(all_persona_ids)} persona_ids complete"))
    else:
        if missing:
            print(f"    [FAIL] {len(missing)} persona_ids not mapped to any entity")
        if extra:
            print(f"    [FAIL] {len(extra)} persona_ids in entities but not in nodes CSV")
        failed += 1
        results.append(("aka_persona_ids completeness", "FAIL",
                        f"missing={len(missing)}, extra={len(extra)}"))

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------
    print(f"\n{'='*60}")
    print(f"VALIDATION RESULTS: {passed} passed, {failed} failed")
    print(f"{'='*60}")
    for name, status, detail in results:
        marker = "[PASS]" if status == "PASS" else "[FAIL]" if status == "FAIL" else "[SKIP]"
        print(f"  {marker} {name}: {detail}")
    print()

    return passed, failed, results


# ---------------------------------------------------------------------------
# Standalone
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    from graph_engine import EntityGraph
    from traversal import GraphTraversal

    engine = EntityGraph()
    engine.load()
    G = engine.get_graph()

    trav = GraphTraversal(G)
    passed, failed, _ = run_validation(engine, trav)

    exit(0 if failed == 0 else 1)
