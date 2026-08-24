"""
query_interface.py — Query Interface + Flask REST API
=======================================================
Provides both a Python function interface (for the fusion layer)
and an optional Flask REST API (for the dashboard).

Endpoints:
  GET /api/query?handle=<username>     — Query by handle
  GET /api/query/pgp?fingerprint=<fp>  — Query by PGP key
  GET /api/query/wallet?address=<addr> — Query by wallet
  GET /api/clusters                    — All candidate clusters
  GET /api/graph                       — Full graph export
  GET /api/export                      — Fusion-layer JSON
"""

import json
from typing import Optional
from graph_engine import EntityGraph
from identity_resolver import IdentityResolver


class QueryInterface:
    """
    Callable query interface for the entity relationship graph.
    
    This is what Member 4's fusion layer calls directly:
        qi = QueryInterface(graph, resolver)
        result = qi.query_handle("darkvendor42")
    """

    def __init__(self, graph: EntityGraph, resolver: IdentityResolver):
        self.graph = graph
        self.resolver = resolver

    def query_handle(self, username: str) -> dict:
        """
        Given a handle, return all linked entities and the graph-derived
        confidence that they belong to the same actor.
        
        Returns:
            {
                "query": username,
                "found": bool,
                "handle_info": { ... },
                "linked_pgp_keys": [ ... ],
                "linked_wallets": [ ... ],
                "marketplaces": [ ... ],
                "trust_links": [ ... ],
                "identity_cluster": { ... } or null,
                "same_actor_candidates": [ ... ],
            }
        """
        node_id = self.graph.get_handle_node_id(username)

        if not node_id:
            return {
                "query": username,
                "found": False,
                "error": f"Handle '{username}' not found in graph",
            }

        # Get node info
        node_data = self.graph.get_node_info(node_id)

        # Find linked PGP keys
        linked_pgp = []
        linked_wallets = []
        marketplaces = []

        for succ in self.graph.graph.successors(node_id):
            succ_data = self.graph.graph.nodes[succ]
            edge_data = self.graph.graph.get_edge_data(node_id, succ)

            for key, edata in edge_data.items():
                if edata.get("edge_type") == EntityGraph.EDGE_USES:
                    if succ_data.get("node_type") == EntityGraph.NODE_PGP:
                        linked_pgp.append({
                            "fingerprint": succ_data.get("fingerprint"),
                            "key_type": succ_data.get("key_type"),
                            "created_date": succ_data.get("created_date"),
                        })
                    elif succ_data.get("node_type") == EntityGraph.NODE_WALLET:
                        linked_wallets.append({
                            "address": succ_data.get("address"),
                            "currency": succ_data.get("currency"),
                            "first_seen": succ_data.get("first_seen"),
                        })
                elif edata.get("edge_type") == EntityGraph.EDGE_POSTS_ON:
                    marketplaces.append({
                        "name": succ_data.get("name", succ_data.get("label")),
                        "type": succ_data.get("marketplace_type"),
                    })

        # Get trust links
        trust_links = self.graph.get_trust_neighbors(username)

        # Find identity cluster
        cluster = self.resolver.get_cluster_for_handle(username)

        # Find same-actor candidates
        same_actor = []
        for pair in self.resolver.get_candidate_pairs():
            if pair["handle_a"] == username or pair["handle_b"] == username:
                other = pair["handle_b"] if pair["handle_a"] == username else pair["handle_a"]
                same_actor.append({
                    "handle": other,
                    "confidence": pair["confidence"],
                    "evidence": pair["evidence"],
                    "signal_count": pair["signal_count"],
                })

        return {
            "query": username,
            "found": True,
            "handle_info": {
                "username": node_data.get("username"),
                "marketplace": node_data.get("marketplace"),
                "marketplace_type": node_data.get("marketplace_type"),
                "registered_date": node_data.get("registered_date"),
                "reputation_score": node_data.get("reputation_score"),
                "total_listings": node_data.get("total_listings"),
            },
            "linked_pgp_keys": linked_pgp,
            "linked_wallets": linked_wallets,
            "marketplaces": marketplaces,
            "trust_links": trust_links,
            "identity_cluster": cluster,
            "same_actor_candidates": same_actor,
        }

    def query_pgp(self, fingerprint: str) -> dict:
        """Query by PGP fingerprint — returns all handles using this key."""
        pgp_shares = self.graph.get_handles_sharing_pgp()
        all_pgp = {}
        for fp, node_id in self.graph._pgp_index.items():
            pgp_data = self.graph.get_node_info(node_id)
            handles_using = []
            for pred in self.graph.graph.predecessors(node_id):
                pred_data = self.graph.graph.nodes[pred]
                if pred_data.get("node_type") == EntityGraph.NODE_HANDLE:
                    handles_using.append(pred_data.get("username"))
            all_pgp[fp] = handles_using

        if fingerprint in all_pgp:
            return {
                "query": fingerprint,
                "found": True,
                "handles": all_pgp[fingerprint],
                "shared": len(all_pgp[fingerprint]) > 1,
            }

        # Try partial match
        matches = {fp: h for fp, h in all_pgp.items()
                   if fingerprint.upper() in fp.upper()}
        if matches:
            return {
                "query": fingerprint,
                "found": True,
                "partial_match": True,
                "results": [{"fingerprint": fp, "handles": h}
                           for fp, h in matches.items()],
            }

        return {"query": fingerprint, "found": False}

    def query_wallet(self, address: str) -> dict:
        """Query by wallet address — returns all handles using this wallet."""
        all_wallets = {}
        for addr, node_id in self.graph._wallet_index.items():
            handles_using = []
            for pred in self.graph.graph.predecessors(node_id):
                pred_data = self.graph.graph.nodes[pred]
                if pred_data.get("node_type") == EntityGraph.NODE_HANDLE:
                    handles_using.append(pred_data.get("username"))
            all_wallets[addr] = handles_using

        if address in all_wallets:
            return {
                "query": address,
                "found": True,
                "handles": all_wallets[address],
                "shared": len(all_wallets[address]) > 1,
            }

        # Try partial match
        matches = {a: h for a, h in all_wallets.items()
                   if address.lower() in a.lower()}
        if matches:
            return {
                "query": address,
                "found": True,
                "partial_match": True,
                "results": [{"address": a, "handles": h}
                           for a, h in matches.items()],
            }

        return {"query": address, "found": False}

    def get_all_clusters(self) -> list:
        """Return all identity clusters with confidence scores."""
        return self.resolver.get_clusters()

    def get_graph_data(self) -> dict:
        """Return the full graph as a serializable dict."""
        return self.graph.to_dict()


# ---------------------------------------------------------------------------
# Flask REST API (optional — for dashboard)
# ---------------------------------------------------------------------------

def create_api(query_interface: QueryInterface):
    """
    Create a Flask app with REST endpoints for the dashboard.
    
    Only imported/called when the user wants the web API.
    """
    from flask import Flask, request, jsonify
    from flask_cors import CORS

    app = Flask(__name__)
    CORS(app)

    @app.route("/api/query", methods=["GET"])
    def api_query_handle():
        handle = request.args.get("handle", "")
        if not handle:
            return jsonify({"error": "Missing 'handle' parameter"}), 400
        return jsonify(query_interface.query_handle(handle))

    @app.route("/api/query/pgp", methods=["GET"])
    def api_query_pgp():
        fp = request.args.get("fingerprint", "")
        if not fp:
            return jsonify({"error": "Missing 'fingerprint' parameter"}), 400
        return jsonify(query_interface.query_pgp(fp))

    @app.route("/api/query/wallet", methods=["GET"])
    def api_query_wallet():
        addr = request.args.get("address", "")
        if not addr:
            return jsonify({"error": "Missing 'address' parameter"}), 400
        return jsonify(query_interface.query_wallet(addr))

    @app.route("/api/clusters", methods=["GET"])
    def api_clusters():
        return jsonify({
            "clusters": query_interface.get_all_clusters(),
            "total": len(query_interface.get_all_clusters()),
        })

    @app.route("/api/graph", methods=["GET"])
    def api_graph():
        return jsonify(query_interface.get_graph_data())

    @app.route("/api/export", methods=["GET"])
    def api_export():
        """Full fusion-layer export."""
        from export import build_fusion_export
        export_data = build_fusion_export(
            query_interface.graph,
            query_interface.resolver
        )
        return jsonify(export_data)

    @app.route("/api/handles", methods=["GET"])
    def api_handles():
        """List all handles."""
        return jsonify({
            "handles": query_interface.graph.get_all_handles(),
            "total": len(query_interface.graph.get_all_handles()),
        })

    @app.route("/", methods=["GET"])
    def serve_dashboard():
        """Serve the dashboard HTML."""
        import os
        dashboard_path = os.path.join(
            os.path.dirname(__file__), "dashboard", "index.html"
        )
        if os.path.exists(dashboard_path):
            with open(dashboard_path, "r", encoding="utf-8") as f:
                return f.read()
        return "<h1>Dashboard not found</h1>", 404

    @app.route("/dashboard/<path:filename>", methods=["GET"])
    def serve_static(filename):
        """Serve dashboard static files."""
        from flask import send_from_directory
        import os
        dashboard_dir = os.path.join(os.path.dirname(__file__), "dashboard")
        return send_from_directory(dashboard_dir, filename)

    return app
