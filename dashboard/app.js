/**
 * app.js — D3.js Force-Directed Graph Visualization
 * ====================================================
 * Interactive entity relationship graph with:
 *   - Force-directed layout
 *   - Node color coding by type
 *   - Animated SAME_ACTOR_AS edges
 *   - Click-to-inspect detail panel
 *   - Search functionality
 *   - Cluster highlighting
 *   - Export actions
 */

// ---------------------------------------------------------------------------
// Configuration
// ---------------------------------------------------------------------------

const API_BASE = window.location.origin;

const NODE_COLORS = {
    Handle: '#6c8cff',
    PGPKey: '#34d399',
    Wallet: '#fb923c',
    Marketplace: '#c084fc',
    Actor: '#f472b6',
};

const NODE_SIZES = {
    Handle: 10,
    PGPKey: 8,
    Wallet: 8,
    Marketplace: 12,
    Actor: 6,
};

const EDGE_CLASSES = {
    SAME_ACTOR_AS: 'same-actor',
    USES: 'uses',
    VOUCHED_BY: 'trust',
    TRANSACTED_WITH: 'trust',
    POSTS_ON: 'posts-on',
};

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------

let graphData = null;
let clusterData = null;
let simulation = null;
let svg, g, linkGroup, nodeGroup, labelGroup;
let zoom;
let selectedNode = null;
let highlightedCluster = null;

// ---------------------------------------------------------------------------
// Initialization
// ---------------------------------------------------------------------------

document.addEventListener('DOMContentLoaded', async () => {
    initSVG();
    await loadData();
    initSearch();
    initControls();
    initExport();
});

function initSVG() {
    svg = d3.select('#graph-svg');
    const container = document.getElementById('graph-container');
    const width = container.clientWidth;
    const height = container.clientHeight;

    svg.attr('viewBox', [0, 0, width, height]);

    // Zoom behavior
    zoom = d3.zoom()
        .scaleExtent([0.1, 5])
        .on('zoom', (event) => {
            g.attr('transform', event.transform);
        });

    svg.call(zoom);

    // Main group for graph elements
    g = svg.append('g');
    linkGroup = g.append('g').attr('class', 'links');
    nodeGroup = g.append('g').attr('class', 'nodes');
    labelGroup = g.append('g').attr('class', 'labels');

    // Arrowhead marker for directed edges
    svg.append('defs').append('marker')
        .attr('id', 'arrowhead')
        .attr('viewBox', '0 -5 10 10')
        .attr('refX', 20)
        .attr('refY', 0)
        .attr('markerWidth', 6)
        .attr('markerHeight', 6)
        .attr('orient', 'auto')
        .append('path')
        .attr('d', 'M0,-5L10,0L0,5')
        .attr('fill', '#4a5080');
}

async function loadData() {
    try {
        // Fetch graph and cluster data
        const [graphRes, clusterRes] = await Promise.all([
            fetch(`${API_BASE}/api/graph`),
            fetch(`${API_BASE}/api/clusters`),
        ]);

        graphData = await graphRes.json();
        clusterData = await clusterRes.json();

        // Update stats
        updateStats(graphData.stats);

        // Render clusters sidebar
        renderClusters(clusterData.clusters);

        // Render graph
        renderGraph(graphData);

        // Hide loading overlay
        document.getElementById('graph-overlay').classList.add('hidden');

        showToast('Graph loaded successfully', 'success');
    } catch (err) {
        console.error('Failed to load data:', err);
        showToast('Failed to load graph data. Make sure the server is running.', 'error');
    }
}

// ---------------------------------------------------------------------------
// Graph Rendering
// ---------------------------------------------------------------------------

function renderGraph(data) {
    const container = document.getElementById('graph-container');
    const width = container.clientWidth;
    const height = container.clientHeight;

    // Deduplicate edges (keep one per source-target-type)
    const edgeMap = new Map();
    data.edges.forEach(e => {
        const key = `${e.source}-${e.target}-${e.edge_type}`;
        if (!edgeMap.has(key)) {
            edgeMap.set(key, e);
        }
    });
    const edges = Array.from(edgeMap.values());

    // Create node map
    const nodeMap = new Map();
    data.nodes.forEach(n => nodeMap.set(n.id, n));

    // Filter edges to only include those with valid source/target
    const validEdges = edges.filter(e =>
        nodeMap.has(e.source) && nodeMap.has(e.target)
    );

    // Create links
    const links = linkGroup.selectAll('.link-line')
        .data(validEdges, d => `${d.source}-${d.target}-${d.edge_type}`)
        .join('line')
        .attr('class', d => `link-line ${EDGE_CLASSES[d.edge_type] || 'uses'}`)
        .attr('stroke-width', d => d.edge_type === 'SAME_ACTOR_AS' ? 2.5 : 1.2);

    // Create nodes
    const nodes = nodeGroup.selectAll('.node-circle')
        .data(data.nodes, d => d.id)
        .join('circle')
        .attr('class', 'node-circle')
        .attr('r', d => NODE_SIZES[d.node_type] || 8)
        .attr('fill', d => NODE_COLORS[d.node_type] || '#6b7280')
        .attr('stroke', d => d3.color(NODE_COLORS[d.node_type] || '#6b7280').darker(0.5))
        .on('click', (event, d) => {
            event.stopPropagation();
            selectNode(d);
        })
        .on('mouseenter', (event, d) => {
            highlightConnected(d);
        })
        .on('mouseleave', () => {
            resetHighlight();
        })
        .call(d3.drag()
            .on('start', dragStarted)
            .on('drag', dragged)
            .on('end', dragEnded)
        );

    // Create labels (only for handles and marketplaces)
    const labels = labelGroup.selectAll('.node-label')
        .data(data.nodes.filter(n =>
            n.node_type === 'Handle' || n.node_type === 'Marketplace'
        ), d => d.id)
        .join('text')
        .attr('class', 'node-label')
        .text(d => d.label || d.username || d.name || '')
        .attr('dy', d => (NODE_SIZES[d.node_type] || 8) + 12);

    // Force simulation
    simulation = d3.forceSimulation(data.nodes)
        .force('link', d3.forceLink(validEdges)
            .id(d => d.id)
            .distance(d => {
                if (d.edge_type === 'SAME_ACTOR_AS') return 60;
                if (d.edge_type === 'POSTS_ON') return 100;
                return 80;
            })
            .strength(d => {
                if (d.edge_type === 'SAME_ACTOR_AS') return 0.8;
                return 0.3;
            })
        )
        .force('charge', d3.forceManyBody()
            .strength(d => {
                if (d.node_type === 'Marketplace') return -200;
                if (d.node_type === 'Handle') return -100;
                return -50;
            })
        )
        .force('center', d3.forceCenter(width / 2, height / 2))
        .force('collision', d3.forceCollide()
            .radius(d => (NODE_SIZES[d.node_type] || 8) + 5)
        )
        .on('tick', () => {
            links
                .attr('x1', d => d.source.x)
                .attr('y1', d => d.source.y)
                .attr('x2', d => d.target.x)
                .attr('y2', d => d.target.y);

            nodes
                .attr('cx', d => d.x)
                .attr('cy', d => d.y);

            labels
                .attr('x', d => d.x)
                .attr('y', d => d.y);
        });

    // Click on background to deselect
    svg.on('click', () => {
        deselectNode();
    });
}

// ---------------------------------------------------------------------------
// Interaction
// ---------------------------------------------------------------------------

function dragStarted(event, d) {
    if (!event.active) simulation.alphaTarget(0.3).restart();
    d.fx = d.x;
    d.fy = d.y;
}

function dragged(event, d) {
    d.fx = event.x;
    d.fy = event.y;
}

function dragEnded(event, d) {
    if (!event.active) simulation.alphaTarget(0);
    d.fx = null;
    d.fy = null;
}

function highlightConnected(node) {
    const connectedIds = new Set([node.id]);

    graphData.edges.forEach(e => {
        const src = typeof e.source === 'object' ? e.source.id : e.source;
        const tgt = typeof e.target === 'object' ? e.target.id : e.target;
        if (src === node.id) connectedIds.add(tgt);
        if (tgt === node.id) connectedIds.add(src);
    });

    nodeGroup.selectAll('.node-circle')
        .attr('opacity', d => connectedIds.has(d.id) ? 1 : 0.15);

    linkGroup.selectAll('.link-line')
        .attr('opacity', d => {
            const src = typeof d.source === 'object' ? d.source.id : d.source;
            const tgt = typeof d.target === 'object' ? d.target.id : d.target;
            return (src === node.id || tgt === node.id) ? 1 : 0.05;
        });

    labelGroup.selectAll('.node-label')
        .attr('opacity', d => connectedIds.has(d.id) ? 1 : 0.1);
}

function resetHighlight() {
    if (highlightedCluster) return; // Don't reset if a cluster is active

    nodeGroup.selectAll('.node-circle').attr('opacity', 1);
    linkGroup.selectAll('.link-line').attr('opacity', null);
    labelGroup.selectAll('.node-label').attr('opacity', 1);
}

async function selectNode(node) {
    selectedNode = node;

    // Highlight the selected node
    nodeGroup.selectAll('.node-circle')
        .classed('highlighted', d => d.id === node.id);

    // If it's a handle, query the API
    if (node.node_type === 'Handle' && node.username) {
        try {
            const res = await fetch(`${API_BASE}/api/query?handle=${encodeURIComponent(node.username)}`);
            const data = await res.json();
            showDetail(data);
        } catch (err) {
            console.error('Query failed:', err);
        }
    } else {
        showNodeDetail(node);
    }
}

function deselectNode() {
    selectedNode = null;
    nodeGroup.selectAll('.node-circle').classed('highlighted', false);
    document.getElementById('detail-content').style.display = 'none';
    document.getElementById('detail-empty').style.display = 'flex';
}

// ---------------------------------------------------------------------------
// Cluster Highlighting
// ---------------------------------------------------------------------------

function highlightCluster(cluster) {
    highlightedCluster = cluster;

    // Find all node IDs that correspond to cluster handles
    const clusterHandleIds = new Set();
    const clusterRelatedIds = new Set();

    graphData.nodes.forEach(n => {
        if (n.node_type === 'Handle' && cluster.handles.includes(n.username)) {
            clusterHandleIds.add(n.id);
            clusterRelatedIds.add(n.id);
        }
    });

    // Also highlight connected PGP/wallet nodes
    graphData.edges.forEach(e => {
        const src = typeof e.source === 'object' ? e.source.id : e.source;
        const tgt = typeof e.target === 'object' ? e.target.id : e.target;
        if (clusterHandleIds.has(src)) clusterRelatedIds.add(tgt);
        if (clusterHandleIds.has(tgt)) clusterRelatedIds.add(src);
    });

    nodeGroup.selectAll('.node-circle')
        .attr('opacity', d => clusterRelatedIds.has(d.id) ? 1 : 0.1)
        .classed('node-cluster-member', d => clusterHandleIds.has(d.id));

    linkGroup.selectAll('.link-line')
        .attr('opacity', d => {
            const src = typeof d.source === 'object' ? d.source.id : d.source;
            const tgt = typeof d.target === 'object' ? d.target.id : d.target;
            return (clusterRelatedIds.has(src) && clusterRelatedIds.has(tgt)) ? 1 : 0.03;
        });

    labelGroup.selectAll('.node-label')
        .attr('opacity', d => clusterRelatedIds.has(d.id) ? 1 : 0.05);

    // Update cluster card active state
    document.querySelectorAll('.cluster-card').forEach(card => {
        card.classList.toggle('active', card.dataset.clusterId === cluster.cluster_id);
    });
}

function clearClusterHighlight() {
    highlightedCluster = null;

    nodeGroup.selectAll('.node-circle')
        .attr('opacity', 1)
        .classed('node-cluster-member', false);

    linkGroup.selectAll('.link-line')
        .attr('opacity', null);

    labelGroup.selectAll('.node-label')
        .attr('opacity', 1);

    document.querySelectorAll('.cluster-card').forEach(card => {
        card.classList.remove('active');
    });
}

// ---------------------------------------------------------------------------
// Sidebar: Cluster List
// ---------------------------------------------------------------------------

function renderClusters(clusters) {
    const list = document.getElementById('cluster-list');
    document.getElementById('cluster-count').textContent = clusters.length;
    list.innerHTML = '';

    clusters.forEach(cluster => {
        const card = document.createElement('div');
        card.className = 'cluster-card';
        card.dataset.clusterId = cluster.cluster_id;

        const confClass = cluster.confidence >= 0.85 ? 'high' :
                          cluster.confidence >= 0.5 ? 'medium' : 'low';

        // Build evidence tags
        const evidenceSet = new Set();
        (cluster.evidence || []).forEach(e => {
            if (e.signal === 'shared_pgp_key') evidenceSet.add('pgp');
            else if (e.signal === 'shared_wallet') evidenceSet.add('wallet');
            else if (e.signal === 'shared_trust_pattern') evidenceSet.add('trust');
        });

        const evidenceTags = Array.from(evidenceSet).map(type =>
            `<span class="evidence-tag ${type}">${type.toUpperCase()}</span>`
        ).join('');

        card.innerHTML = `
            <div class="cluster-card-header">
                <span class="cluster-id">${cluster.cluster_id}</span>
                <span class="confidence-badge confidence-${confClass}">
                    ${(cluster.confidence * 100).toFixed(0)}%
                </span>
            </div>
            <div class="cluster-handles">
                ${cluster.handles.map(h => `
                    <div class="cluster-handle">
                        <span class="dot"></span>
                        <span class="handle-name">${h}</span>
                    </div>
                `).join('')}
            </div>
            <div class="cluster-evidence">${evidenceTags}</div>
        `;

        card.addEventListener('click', () => {
            if (highlightedCluster && highlightedCluster.cluster_id === cluster.cluster_id) {
                clearClusterHighlight();
            } else {
                highlightCluster(cluster);
            }
        });

        list.appendChild(card);
    });
}

// ---------------------------------------------------------------------------
// Detail Panel
// ---------------------------------------------------------------------------

function showDetail(data) {
    if (!data.found) return;

    const detailContent = document.getElementById('detail-content');
    const detailEmpty = document.getElementById('detail-empty');

    detailEmpty.style.display = 'none';
    detailContent.style.display = 'block';

    // Header
    document.getElementById('detail-type-badge').textContent = 'Handle';
    document.getElementById('detail-type-badge').style.background = 'rgba(108, 140, 255, 0.12)';
    document.getElementById('detail-type-badge').style.color = '#6c8cff';
    document.getElementById('detail-title').textContent = data.handle_info.username;
    document.getElementById('detail-subtitle').textContent =
        `${data.handle_info.marketplace} • ${data.handle_info.marketplace_type}`;

    // Build sections
    const sections = document.getElementById('detail-sections');
    sections.innerHTML = '';

    // Basic Info
    sections.innerHTML += `
        <div class="detail-section">
            <div class="detail-section-title">Handle Info</div>
            <div class="detail-row">
                <span class="detail-row-label">Marketplace</span>
                <span class="detail-row-value">${data.handle_info.marketplace || '—'}</span>
            </div>
            <div class="detail-row">
                <span class="detail-row-label">Reputation</span>
                <span class="detail-row-value">${data.handle_info.reputation_score || '—'}</span>
            </div>
            <div class="detail-row">
                <span class="detail-row-label">Listings</span>
                <span class="detail-row-value">${data.handle_info.total_listings || '—'}</span>
            </div>
            <div class="detail-row">
                <span class="detail-row-label">Registered</span>
                <span class="detail-row-value">${formatDate(data.handle_info.registered_date)}</span>
            </div>
        </div>
    `;

    // PGP Keys
    if (data.linked_pgp_keys && data.linked_pgp_keys.length > 0) {
        sections.innerHTML += `
            <div class="detail-section">
                <div class="detail-section-title">PGP Keys (${data.linked_pgp_keys.length})</div>
                ${data.linked_pgp_keys.map(p => `
                    <div class="detail-list-item">
                        <span class="item-icon" style="background: ${NODE_COLORS.PGPKey}"></span>
                        <span class="item-text">${p.fingerprint.substring(0, 20)}…</span>
                        <span class="item-meta">${p.key_type || ''}</span>
                    </div>
                `).join('')}
            </div>
        `;
    }

    // Wallets
    if (data.linked_wallets && data.linked_wallets.length > 0) {
        sections.innerHTML += `
            <div class="detail-section">
                <div class="detail-section-title">Wallets (${data.linked_wallets.length})</div>
                ${data.linked_wallets.map(w => `
                    <div class="detail-list-item">
                        <span class="item-icon" style="background: ${NODE_COLORS.Wallet}"></span>
                        <span class="item-text">${w.address.substring(0, 20)}…</span>
                        <span class="item-meta">${w.currency}</span>
                    </div>
                `).join('')}
            </div>
        `;
    }

    // Same-Actor Candidates
    if (data.same_actor_candidates && data.same_actor_candidates.length > 0) {
        const candidatesHTML = data.same_actor_candidates.map(sa => {
            const confClass = sa.confidence >= 0.85 ? 'high' :
                              sa.confidence >= 0.5 ? 'medium' : 'low';
            const pct = (sa.confidence * 100).toFixed(0);
            return `
                <div class="detail-list-item" onclick="searchAndSelect('${sa.handle}')">
                    <span class="item-icon" style="background: var(--color-edge-same-actor)"></span>
                    <span class="item-text">${sa.handle}</span>
                    <span class="confidence-badge confidence-${confClass}">${pct}%</span>
                </div>
                <div class="confidence-bar-container">
                    <div class="confidence-bar">
                        <div class="confidence-bar-fill ${confClass}" style="width: ${pct}%"></div>
                    </div>
                </div>
            `;
        }).join('');

        sections.innerHTML += `
            <div class="detail-section">
                <div class="detail-section-title">⚡ Same-Actor Candidates</div>
                ${candidatesHTML}
            </div>
        `;
    }

    // Identity Cluster
    if (data.identity_cluster) {
        const c = data.identity_cluster;
        sections.innerHTML += `
            <div class="detail-section">
                <div class="detail-section-title">Identity Cluster: ${c.cluster_id}</div>
                <div class="detail-row">
                    <span class="detail-row-label">Confidence</span>
                    <span class="detail-row-value">${(c.confidence * 100).toFixed(0)}%</span>
                </div>
                <div class="detail-row">
                    <span class="detail-row-label">Members</span>
                    <span class="detail-row-value">${c.handle_count}</span>
                </div>
                ${c.shared_identifiers.pgp_keys.length > 0 ? `
                    <div class="detail-row">
                        <span class="detail-row-label">Shared PGP</span>
                        <span class="detail-row-value">${c.shared_identifiers.pgp_keys.length}</span>
                    </div>
                ` : ''}
                ${c.shared_identifiers.wallets.length > 0 ? `
                    <div class="detail-row">
                        <span class="detail-row-label">Shared Wallets</span>
                        <span class="detail-row-value">${c.shared_identifiers.wallets.length}</span>
                    </div>
                ` : ''}
            </div>
        `;
    }

    // Trust Links
    if (data.trust_links && data.trust_links.length > 0) {
        sections.innerHTML += `
            <div class="detail-section">
                <div class="detail-section-title">Trust Links (${data.trust_links.length})</div>
                ${data.trust_links.slice(0, 10).map(t => `
                    <div class="detail-list-item" onclick="searchAndSelect('${t.handle}')">
                        <span class="item-icon" style="background: var(--color-edge-trust)"></span>
                        <span class="item-text">${t.handle}</span>
                        <span class="item-meta">${t.link_type} ${t.direction === 'incoming' ? '←' : '→'}</span>
                    </div>
                `).join('')}
            </div>
        `;
    }
}

function showNodeDetail(node) {
    const detailContent = document.getElementById('detail-content');
    const detailEmpty = document.getElementById('detail-empty');

    detailEmpty.style.display = 'none';
    detailContent.style.display = 'block';

    const badge = document.getElementById('detail-type-badge');
    badge.textContent = node.node_type;
    badge.style.background = `${NODE_COLORS[node.node_type]}20`;
    badge.style.color = NODE_COLORS[node.node_type];

    document.getElementById('detail-title').textContent = node.label || node.id;
    document.getElementById('detail-subtitle').textContent = node.node_type;

    const sections = document.getElementById('detail-sections');
    sections.innerHTML = `
        <div class="detail-section">
            <div class="detail-section-title">Node Properties</div>
            ${Object.entries(node)
                .filter(([k]) => !['id', 'x', 'y', 'vx', 'vy', 'fx', 'fy', 'index', 'label'].includes(k))
                .map(([k, v]) => `
                    <div class="detail-row">
                        <span class="detail-row-label">${k}</span>
                        <span class="detail-row-value">${truncate(String(v), 24)}</span>
                    </div>
                `).join('')}
        </div>
    `;
}

// ---------------------------------------------------------------------------
// Stats
// ---------------------------------------------------------------------------

function updateStats(stats) {
    document.getElementById('stat-nodes').textContent = stats.total_nodes || 0;
    document.getElementById('stat-edges').textContent = stats.total_edges || 0;
    document.getElementById('stat-handles').textContent = stats.handles || 0;
    document.getElementById('stat-clusters').textContent = clusterData?.total || 0;
}

// ---------------------------------------------------------------------------
// Search
// ---------------------------------------------------------------------------

function initSearch() {
    const input = document.getElementById('search-input');

    input.addEventListener('input', debounce((e) => {
        const query = e.target.value.trim().toLowerCase();
        if (!query) {
            resetHighlight();
            return;
        }

        // Find matching nodes
        const matches = graphData.nodes.filter(n => {
            const label = (n.label || '').toLowerCase();
            const username = (n.username || '').toLowerCase();
            const fingerprint = (n.fingerprint || '').toLowerCase();
            const address = (n.address || '').toLowerCase();
            const name = (n.name || '').toLowerCase();
            return label.includes(query) || username.includes(query) ||
                   fingerprint.includes(query) || address.includes(query) ||
                   name.includes(query);
        });

        if (matches.length > 0) {
            const matchIds = new Set(matches.map(m => m.id));

            nodeGroup.selectAll('.node-circle')
                .attr('opacity', d => matchIds.has(d.id) ? 1 : 0.1);
            labelGroup.selectAll('.node-label')
                .attr('opacity', d => matchIds.has(d.id) ? 1 : 0.05);

            // Auto-select first match
            if (matches.length === 1) {
                selectNode(matches[0]);
            }
        }
    }, 200));

    // Keyboard shortcut: Cmd/Ctrl + K to focus search
    document.addEventListener('keydown', (e) => {
        if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
            e.preventDefault();
            input.focus();
        }
        if (e.key === 'Escape') {
            input.blur();
            input.value = '';
            resetHighlight();
            deselectNode();
        }
    });
}

function searchAndSelect(handleName) {
    const node = graphData.nodes.find(n => n.username === handleName);
    if (node) {
        selectNode(node);

        // Center on the node
        const container = document.getElementById('graph-container');
        const width = container.clientWidth;
        const height = container.clientHeight;

        svg.transition().duration(500)
            .call(zoom.transform,
                d3.zoomIdentity
                    .translate(width / 2, height / 2)
                    .scale(1.5)
                    .translate(-node.x, -node.y)
            );
    }
}

// ---------------------------------------------------------------------------
// Controls
// ---------------------------------------------------------------------------

function initControls() {
    document.getElementById('btn-zoom-in').addEventListener('click', () => {
        svg.transition().duration(300).call(zoom.scaleBy, 1.4);
    });

    document.getElementById('btn-zoom-out').addEventListener('click', () => {
        svg.transition().duration(300).call(zoom.scaleBy, 0.7);
    });

    document.getElementById('btn-fit').addEventListener('click', () => {
        const container = document.getElementById('graph-container');
        const width = container.clientWidth;
        const height = container.clientHeight;
        svg.transition().duration(500)
            .call(zoom.transform, d3.zoomIdentity
                .translate(width / 2, height / 2)
                .scale(0.8)
                .translate(-width / 2, -height / 2)
            );
    });

    document.getElementById('btn-reset-view').addEventListener('click', () => {
        clearClusterHighlight();
        deselectNode();
        const container = document.getElementById('graph-container');
        const width = container.clientWidth;
        const height = container.clientHeight;
        svg.transition().duration(500)
            .call(zoom.transform, d3.zoomIdentity);
    });
}

// ---------------------------------------------------------------------------
// Export
// ---------------------------------------------------------------------------

function initExport() {
    document.getElementById('btn-export-json').addEventListener('click', async () => {
        try {
            const res = await fetch(`${API_BASE}/api/export`);
            const data = await res.json();
            downloadJSON(data, 'graph_signal_export.json');
            showToast('JSON export downloaded', 'success');
        } catch (err) {
            showToast('Export failed', 'error');
        }
    });

    document.getElementById('btn-export-csv').addEventListener('click', async () => {
        try {
            const clusters = clusterData.clusters;
            let csv = 'Cluster ID,Handle A,Handle B,Confidence,Evidence\n';
            clusters.forEach(c => {
                for (let i = 0; i < c.handles.length; i++) {
                    for (let j = i + 1; j < c.handles.length; j++) {
                        const evidence = (c.evidence || []).map(e => e.signal).join('; ');
                        csv += `${c.cluster_id},${c.handles[i]},${c.handles[j]},${c.confidence},"${evidence}"\n`;
                    }
                }
            });
            downloadCSV(csv, 'identity_clusters.csv');
            showToast('CSV export downloaded', 'success');
        } catch (err) {
            showToast('Export failed', 'error');
        }
    });
}

function downloadJSON(data, filename) {
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
}

function downloadCSV(csv, filename) {
    const blob = new Blob([csv], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
}

// ---------------------------------------------------------------------------
// Toast Notifications
// ---------------------------------------------------------------------------

function showToast(message, type = 'success') {
    const container = document.getElementById('toast-container');
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.textContent = message;
    container.appendChild(toast);

    setTimeout(() => {
        toast.style.animation = 'toast-out 0.3s ease-in forwards';
        setTimeout(() => toast.remove(), 300);
    }, 3000);
}

// ---------------------------------------------------------------------------
// Utilities
// ---------------------------------------------------------------------------

function formatDate(dateStr) {
    if (!dateStr) return '—';
    try {
        const d = new Date(dateStr);
        return d.toLocaleDateString('en-US', {
            year: 'numeric', month: 'short', day: 'numeric'
        });
    } catch {
        return dateStr;
    }
}

function truncate(str, len) {
    if (!str) return '—';
    return str.length > len ? str.substring(0, len) + '…' : str;
}

function debounce(fn, ms) {
    let timeout;
    return (...args) => {
        clearTimeout(timeout);
        timeout = setTimeout(() => fn(...args), ms);
    };
}
