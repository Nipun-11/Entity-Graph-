"""
main.py — Entity Relationship Graph Module (SIH26151, Module 2)
=================================================================
Single entry point for the full pipeline:

  python main.py              # Build graph + validate + export
  python main.py --serve      # Also launch Flask dashboard

Pipeline:
  1. Load ANON CSVs -> canonical entity collapse -> MultiDiGraph
  2. Multi-hop traversal engine
  3. Run validation checklist (spec §5)
  4. Export entity_graph_output.json (pairwise scores + full graph)
  5. (Optional) Serve dashboard at localhost:5000
"""

import argparse
import sys
import os
from pathlib import Path

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

# Ensure we can import from project root
sys.path.insert(0, str(Path(__file__).parent))


def run_pipeline(serve=False, skip_validation=False, max_pairs=500):
    """Run the full Entity Graph pipeline."""

    print("""
============================================================
  SIH26151 - Module 2: Entity Relationship Graph
  Dark Web Threat Actor De-anonymization
============================================================
""")

    # ------------------------------------------------------------------
    # Step 1: Build Graph
    # ------------------------------------------------------------------
    print("[Step 1/4] Building entity graph...")
    from graph_engine import EntityGraph

    engine = EntityGraph()
    engine.load()
    G = engine.get_graph()

    # ------------------------------------------------------------------
    # Step 2: Initialize Traversal
    # ------------------------------------------------------------------
    print("[Step 2/4] Initializing traversal engine...")
    from traversal import GraphTraversal

    trav = GraphTraversal(G)
    stats = trav.get_graph_stats()
    print(f"    Entities: {stats['total_entities']}")
    print(f"    Edges: {stats['total_edges']}")
    print(f"    Components: {stats['connected_components']}")
    print(f"    Isolated: {stats['isolated_entities']}")

    # Community detection
    communities = trav.detect_communities()
    print(f"    Communities (Louvain): {len(communities)}")

    # ------------------------------------------------------------------
    # Step 3: Validation
    # ------------------------------------------------------------------
    if not skip_validation:
        print("\n[Step 3/4] Running validation...")
        from validate import run_validation

        passed, failed, results = run_validation(engine, trav)
        if failed > 0:
            print(f"\n[WARN] {failed} validation check(s) failed!")
            print("       Review the output above before using the export.")
    else:
        print("\n[Step 3/4] Validation skipped (--skip-validation)")

    # ------------------------------------------------------------------
    # Step 4: Export
    # ------------------------------------------------------------------
    print("\n[Step 4/4] Exporting results...")
    from export import export_graph

    output_path = export_graph(engine, trav, max_pairs=max_pairs)

    # ------------------------------------------------------------------
    # Done
    # ------------------------------------------------------------------
    print(f"""
============================================================
  PIPELINE COMPLETE
============================================================

  Output: {output_path}

  What this file contains:
    - pairwise_scores: scored connections for Fusion module
    - graph.nodes: canonical entities with aka_persona_ids
    - graph.edges: cross-entity relationships
    - statistics: summary counts

  Cross-module join key: persona_id (via aka_persona_ids)
  Fusion reads: entity_id_a, entity_id_b, graph_link_strength, path_confidence
============================================================
""")

    # ------------------------------------------------------------------
    # Optional: Serve Dashboard
    # ------------------------------------------------------------------
    if serve:
        _serve_dashboard(engine, trav, output_path)

    return engine, trav


def _serve_dashboard(engine, trav, output_path):
    """Launch Flask server for the dashboard."""
    try:
        from flask import Flask, jsonify, send_from_directory, request
        from flask_cors import CORS
    except ImportError:
        print("\n[!] Flask not installed. Run: pip install flask flask-cors")
        print("    Dashboard will not be served.")
        return

    import json

    dashboard_dir = Path(__file__).parent / "dashboard"
    app = Flask(__name__)
    CORS(app)

    # Load the export data
    with open(output_path, "r", encoding="utf-8") as f:
        export_data = json.load(f)

    @app.route("/")
    def index():
        return send_from_directory(dashboard_dir, "index.html")

    @app.route("/<path:filename>")
    def static_files(filename):
        return send_from_directory(dashboard_dir, filename)

    @app.route("/api/graph")
    def api_graph():
        """Full graph data for visualization."""
        return jsonify(export_data["graph"])

    @app.route("/api/stats")
    def api_stats():
        """Graph statistics."""
        return jsonify(export_data["statistics"])

    @app.route("/api/entity/<entity_id>")
    def api_entity(entity_id):
        """Get entity details."""
        entity = engine.get_entity(entity_id)
        if entity:
            connections = trav.find_connections(entity_id, max_hops=2)
            return jsonify({
                "entity": entity,
                "connections": connections[:20],
            })
        return jsonify({"error": "Entity not found"}), 404

    @app.route("/api/path")
    def api_path():
        """Find path between two entities."""
        source = request.args.get("source")
        target = request.args.get("target")
        if not source or not target:
            return jsonify({"error": "source and target required"}), 400
        result = trav.find_path(source, target, cutoff=3)
        return jsonify(result)

    @app.route("/api/search")
    def api_search():
        """Search entities by handle name."""
        query = request.args.get("q", "").lower()
        if not query:
            return jsonify([])
        matches = []
        for eid, data in engine.get_all_entities().items():
            if query in data["handle"].lower():
                matches.append({
                    "entity_id": eid,
                    "handle": data["handle"],
                    "marketplaces": data["active_marketplaces"],
                })
        return jsonify(matches[:20])

    @app.route("/api/communities")
    @app.route("/api/clusters")
    def api_communities():
        """Get community detection results."""
        communities = trav.detect_communities()
        result = []
        for i, comm in enumerate(communities[:50]):
            members = []
            for eid in sorted(comm):
                entity = engine.get_entity(eid)
                if entity:
                    members.append({
                        "entity_id": eid,
                        "handle": entity["handle"],
                    })
            result.append({
                "community_id": i,
                "size": len(comm),
                "members": members,
            })
        return jsonify(result)

    @app.route("/api/pairwise")
    def api_pairwise():
        """Get pairwise scores."""
        limit = int(request.args.get("limit", 50))
        return jsonify(export_data["pairwise_scores"][:limit])

    port = int(os.environ.get("DASHBOARD_PORT", "5000"))
    print(f"\n[*] Dashboard starting at http://localhost:{port}")
    print("    Press Ctrl+C to stop.\n")
    app.run(host="127.0.0.1", port=port, debug=False)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="SIH26151 Module 2: Entity Relationship Graph"
    )
    parser.add_argument("--serve", action="store_true",
                        help="Launch dashboard at localhost:5000 after pipeline")
    parser.add_argument("--skip-validation", action="store_true",
                        help="Skip validation checks")
    parser.add_argument("--train-ml", action="store_true",
                        help="Train supervised ML link prediction model (RandomForest/XGBoost)")
    parser.add_argument("--max-pairs", type=int, default=500,
                        help="Max pairwise scores to compute (default: 500)")
    args = parser.parse_args()

    engine, trav = run_pipeline(
        serve=args.serve,
        skip_validation=args.skip_validation,
        max_pairs=args.max_pairs,
    )

    if args.train_ml:
        from model_trainer import GraphFeatureExtractor, build_training_dataset, train_and_evaluate
        extractor = GraphFeatureExtractor(engine, trav)
        df, y, feature_cols = build_training_dataset(engine, trav, extractor)
        train_and_evaluate(df, y, feature_cols)


if __name__ == "__main__":
    main()
