"""
evaluate.py — Accuracy Evaluation Against Ground Truth
========================================================
Compares inferred SAME_ACTOR_AS clusters against the planted
ground truth in the synthetic dataset.

Metrics:
  - Precision: Of the pairs we flagged, how many were correct?
  - Recall: Of the true pairs, how many did we find?
  - F1: Harmonic mean
  - Per-cluster breakdown
"""

import json
from itertools import combinations
from identity_resolver import IdentityResolver


def evaluate(resolver: IdentityResolver, ground_truth: dict) -> dict:
    """
    Evaluate identity resolution accuracy against ground truth.
    
    Args:
        resolver: The IdentityResolver after running .resolve()
        ground_truth: Dict mapping actor_id → [list of true handles]
                      (from dataset["ground_truth_clusters"])
    
    Returns:
        Dict with precision, recall, F1, confusion matrix, and per-cluster breakdown.
    """
    print("\n" + "=" * 60)
    print("  EVALUATION: Identity Resolution Accuracy")
    print("=" * 60)

    # ------------------------------------------------------------------
    # Build ground-truth pair set
    # ------------------------------------------------------------------
    true_pairs = set()
    true_clusters = {}  # handle → actor_id

    for actor_id, handles in ground_truth.items():
        if len(handles) >= 2:
            for a, b in combinations(sorted(handles), 2):
                true_pairs.add((a, b))
        for h in handles:
            true_clusters[h] = actor_id

    # ------------------------------------------------------------------
    # Build predicted pair set
    # ------------------------------------------------------------------
    predicted_pairs = set()
    for pair in resolver.get_candidate_pairs():
        p = tuple(sorted([pair["handle_a"], pair["handle_b"]]))
        predicted_pairs.add(p)

    # ------------------------------------------------------------------
    # Compute metrics
    # ------------------------------------------------------------------
    true_positives = predicted_pairs & true_pairs
    false_positives = predicted_pairs - true_pairs
    false_negatives = true_pairs - predicted_pairs

    tp = len(true_positives)
    fp = len(false_positives)
    fn = len(false_negatives)

    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = (2 * precision * recall / (precision + recall)
          if (precision + recall) > 0 else 0.0)

    # ------------------------------------------------------------------
    # Per-cluster breakdown
    # ------------------------------------------------------------------
    cluster_results = []
    for cluster in resolver.get_clusters():
        cluster_handles = set(cluster["handles"])
        
        # Find which true actor(s) this cluster maps to
        mapped_actors = set()
        for h in cluster_handles:
            if h in true_clusters:
                mapped_actors.add(true_clusters[h])

        # Check if all handles in this cluster belong to the same true actor
        is_pure = len(mapped_actors) <= 1
        
        # Find true handles for the mapped actor
        true_handles_for_actor = set()
        if mapped_actors:
            actor_id = list(mapped_actors)[0]
            true_handles_for_actor = set(ground_truth.get(actor_id, []))

        # Cluster-level metrics
        correctly_grouped = cluster_handles & true_handles_for_actor
        incorrectly_grouped = cluster_handles - true_handles_for_actor
        missed = true_handles_for_actor - cluster_handles

        cluster_results.append({
            "cluster_id": cluster["cluster_id"],
            "predicted_handles": sorted(cluster_handles),
            "confidence": cluster["confidence"],
            "mapped_actor": list(mapped_actors)[0] if mapped_actors else "UNKNOWN",
            "is_pure": is_pure,
            "correctly_grouped": sorted(correctly_grouped),
            "incorrectly_grouped": sorted(incorrectly_grouped),
            "missed_handles": sorted(missed),
        })

    # ------------------------------------------------------------------
    # Print results
    # ------------------------------------------------------------------
    print(f"\n  Ground truth pairs:  {len(true_pairs)}")
    print(f"  Predicted pairs:     {len(predicted_pairs)}")
    print(f"\n  True Positives:  {tp}")
    print(f"  False Positives: {fp}")
    print(f"  False Negatives: {fn}")
    print(f"\n  Precision: {precision:.4f}")
    print(f"  Recall:    {recall:.4f}")
    print(f"  F1 Score:  {f1:.4f}")

    print(f"\n  Per-Cluster Breakdown:")
    print(f"  {'-' * 56}")
    for cr in cluster_results:
        status = "[OK] PURE" if cr["is_pure"] else "[!!] MIXED"
        print(f"  {cr['cluster_id']} | {status} | "
              f"conf={cr['confidence']:.2f} | "
              f"actor={cr['mapped_actor']} | "
              f"handles={cr['predicted_handles']}")
        if cr["incorrectly_grouped"]:
            print(f"         [!] Wrong: {cr['incorrectly_grouped']}")
        if cr["missed_handles"]:
            print(f"         [!] Missed: {cr['missed_handles']}")

    # ------------------------------------------------------------------
    # Check specific planted rebrands
    # ------------------------------------------------------------------
    print(f"\n  Planted Rebrand Detection:")
    print(f"  {'─' * 56}")
    rebrand_actors = [aid for aid in ground_truth
                      if aid.startswith("ACTOR_R")]
    for actor_id in sorted(rebrand_actors):
        true_handles = ground_truth[actor_id]
        detected = False
        det_confidence = 0.0

        for pair in resolver.get_candidate_pairs():
            p = tuple(sorted([pair["handle_a"], pair["handle_b"]]))
            true_p = tuple(sorted(true_handles))
            if len(true_handles) == 2 and p == true_p:
                detected = True
                det_confidence = pair["confidence"]
                break

        status = f"[OK] DETECTED (conf={det_confidence:.2f})" if detected else "[!!] MISSED"
        print(f"  {actor_id}: {true_handles} -> {status}")

    print(f"\n{'=' * 60}\n")

    # ------------------------------------------------------------------
    # Return structured results
    # ------------------------------------------------------------------
    return {
        "metrics": {
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1_score": round(f1, 4),
            "true_positives": tp,
            "false_positives": fp,
            "false_negatives": fn,
        },
        "confusion": {
            "true_positive_pairs": [list(p) for p in sorted(true_positives)],
            "false_positive_pairs": [list(p) for p in sorted(false_positives)],
            "false_negative_pairs": [list(p) for p in sorted(false_negatives)],
        },
        "cluster_results": cluster_results,
        "ground_truth_pairs": len(true_pairs),
        "predicted_pairs": len(predicted_pairs),
    }


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import os
    from synthetic_dataset import generate_dataset
    from graph_engine import EntityGraph
    from identity_resolver import IdentityResolver

    # Generate dataset
    dataset = generate_dataset()

    # Build graph
    graph = EntityGraph()
    graph.ingest_dataset(dataset)

    # Resolve identities
    resolver = IdentityResolver(graph)
    resolver.resolve()

    # Evaluate
    results = evaluate(resolver, dataset["ground_truth_clusters"])

    # Save results
    os.makedirs("data", exist_ok=True)
    with open("data/evaluation_results.json", "w") as f:
        json.dump(results, f, indent=2)
    print("[OK] Evaluation results saved to data/evaluation_results.json")
