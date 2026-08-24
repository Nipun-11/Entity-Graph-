/**
 * app.js — D3.js Force-Directed Graph Visualization for Canonical Entity Graph
 * ==============================================================================
 * Interactive visualization of 500 canonical threat actor entities, 1,482 cross-market
 * relationships, Louvain community clusters, and multi-hop traversal paths.
 */

// ---------------------------------------------------------------------------
// Configuration & Color Palettes
// ---------------------------------------------------------------------------

const API_BASE = window.location.origin;

// 24 distinct HSL-tailored colors for Louvain communities
const COMMUNITY_COLORS = [
    '#6366f1', '#ec4899', '#14b8a6', '#f59e0b', '#8b5cf6',
    '#06b6d4', '#10b981', '#f97316', '#3b82f6', '#d946ef',
    '#84cc16', '#e11d48', '#22c55e', '#a855f7', '#eab308',
    '#0284c7', '#4ade80', '#fb7185', '#2dd4bf', '#c084fc',
    '#fb923c', '#38bdf8', '#a3e635', '#f43f5e'
];

const EDGE_COLORS = {
    'VOUCHED_FOR': '#6366f1',
    'TRANSACTED_WITH': '#06b6d4',
    'CO_OCCURRED_IN_THREAD': '#f59e0b',
    'PATH_HIGHLIGHT': '#f43f5e'
};

// ---------------------------------------------------------------------------
// Global State
// ---------------------------------------------------------------------------

let fullGraphData = { nodes: [], edges: [] };
let communitiesData = [];
let pairwiseData = [];
let statsData = {};

let simulation = null;
let svg, g, linkGroup, nodeGroup, labelGroup;
let zoom;
let selectedEntityId = null;
let activeCommunityId = null;
let activePathEntities = null;
let showAllLinks = false;

// ---------------------------------------------------------------------------
// Initialization
// ---------------------------------------------------------------------------

document.addEventListener('DOMContentLoaded', async () => {
    initSVG();
    initControls();
    await loadAllData();
    initSearch();
    initExport();
});

function initSVG() {
    svg = d3.select('#graph-svg');
    const container = document.getElementById('graph-container');
    const width = container.clientWidth || 900;
    const height = container.clientHeight || 700;

    svg.attr('viewBox', [0, 0, width, height]);

    zoom = d3.zoom()
        .scaleExtent([0.05, 8])
        .on('zoom', (event) => {
            g.attr('transform', event.transform);
        });

    svg.call(zoom);

    // Main canvas groups
    g = svg.append('g');
    linkGroup = g.append('g').attr('class', 'links');
    nodeGroup = g.append('g').attr('class', 'nodes');
    labelGroup = g.append('g').attr('class', 'labels');

    // Canvas click deselects
    svg.on('click', () => {
        deselectNode();
    });
}

// ---------------------------------------------------------------------------
// Data Loading
// ---------------------------------------------------------------------------

async function loadAllData() {
    try {
        const [graphRes, statsRes, commRes, pairRes] = await Promise.allSettled([
            fetch(`${API_BASE}/api/graph`),
            fetch(`${API_BASE}/api/stats`),
            fetch(`${API_BASE}/api/communities`),
            fetch(`${API_BASE}/api/pairwise?limit=100`)
        ]);

        if (graphRes.status === 'fulfilled' && graphRes.value.ok) {
            fullGraphData = await graphRes.value.json();
        } else {
            throw new Error('Could not fetch /api/graph');
        }

        if (statsRes.status === 'fulfilled' && statsRes.value.ok) {
            statsData = await statsRes.value.json();
            updateStats(statsData);
        }

        if (commRes.status === 'fulfilled' && commRes.value.ok) {
            communitiesData = await commRes.value.json();
        }

        if (pairRes.status === 'fulfilled' && pairRes.value.ok) {
            pairwiseData = await pairRes.value.json();
        }

        // Map community IDs to nodes
        mapCommunitiesToNodes();

        // Render Sidebar & Graph
        renderCommunitiesSidebar(communitiesData);
        renderGraph(fullGraphData);

        // Hide loader overlay
        document.getElementById('graph-overlay').classList.add('hidden');
        showToast('Entity graph loaded successfully', 'success');

    } catch (err) {
        console.error('Failed to load graph data:', err);
        document.getElementById('graph-overlay').innerHTML = `
            <div style="text-align:center; color:#f87171; padding:20px;">
                <h3>Failed to load graph</h3>
                <p style="color:#9ca3af; margin-top:8px;">${err.message}</p>
            </div>
        `;
        showToast('Error loading graph. Check server.', 'error');
    }
}

function mapCommunitiesToNodes() {
    const nodeCommMap = new Map();
    communitiesData.forEach((comm, idx) => {
        if (comm.members) {
            comm.members.forEach(m => {
                nodeCommMap.set(m.entity_id, idx);
            });
        }
    });

    fullGraphData.nodes.forEach(n => {
        n.id = n.entity_id; // Normalize id
        n.community = nodeCommMap.get(n.entity_id) ?? 0;
        n.color = COMMUNITY_COLORS[n.community % COMMUNITY_COLORS.length];
        n.degree = 0;
    });

    // Compute degrees for sizing
    const nodeMap = new Map(fullGraphData.nodes.map(n => [n.id, n]));
    fullGraphData.edges.forEach(e => {
        const u = nodeMap.get(typeof e.source === 'object' ? e.source.id : e.source);
        const v = nodeMap.get(typeof e.target === 'object' ? e.target.id : e.target);
        if (u) u.degree = (u.degree || 0) + 1;
        if (v) v.degree = (v.degree || 0) + 1;
    });
}

function updateStats(stats) {
    if (!stats) return;
    if (document.getElementById('stat-nodes')) document.getElementById('stat-nodes').textContent = stats.total_entities ?? '500';
    if (document.getElementById('stat-edges')) document.getElementById('stat-edges').textContent = stats.total_graph_edges ?? '1,482';
    if (document.getElementById('stat-handles')) document.getElementById('stat-handles').textContent = stats.total_personas ?? '1,833';
    if (document.getElementById('stat-clusters')) document.getElementById('stat-clusters').textContent = stats.connected_components ?? '23';
}

// ---------------------------------------------------------------------------
// Graph Rendering
// ---------------------------------------------------------------------------

function renderGraph(data) {
    const container = document.getElementById('graph-container');
    const width = container.clientWidth || 900;
    const height = container.clientHeight || 700;

    const nodeMap = new Map(data.nodes.map(d => [d.id, d]));

    // Filter valid edges
    const validEdges = data.edges.filter(e => {
        const s = typeof e.source === 'object' ? e.source.id : e.source;
        const t = typeof e.target === 'object' ? e.target.id : e.target;
        return nodeMap.has(s) && nodeMap.has(t);
    }).map(e => ({
        ...e,
        source: typeof e.source === 'object' ? e.source.id : e.source,
        target: typeof e.target === 'object' ? e.target.id : e.target
    }));

    // Links
    const links = linkGroup.selectAll('.link-line')
        .data(validEdges, d => `${d.source}-${d.target}-${d.relation_type}`)
        .join('line')
        .attr('class', 'link-line')
        .attr('stroke', d => EDGE_COLORS[d.relation_type] || '#4a5080')
        .attr('stroke-width', d => Math.max(1, (d.confidence || 0.5) * 2.2))
        .attr('opacity', 0);

    // Nodes
    const nodes = nodeGroup.selectAll('.node-circle')
        .data(data.nodes, d => d.id)
        .join('circle')
        .attr('class', 'node-circle')
        .attr('r', d => {
            const baseSize = 6;
            const marketBonus = (d.active_marketplaces ? d.active_marketplaces.length : 1) * 1.5;
            const degreeBonus = Math.min(6, (d.degree || 1) * 0.4);
            return baseSize + marketBonus + degreeBonus;
        })
        .attr('fill', d => d.color)
        .attr('stroke', d => d3.color(d.color).brighter(0.6))
        .attr('stroke-width', 1.5)
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

    // A graph with 500 labels is unreadable. Keep only the most connected
    // actors labeled; the rest remain searchable and reveal their details on click.
    const prominentNodeIds = new Set(
        [...data.nodes]
            .sort((a, b) => (b.degree || 0) - (a.degree || 0))
            .slice(0, 30)
            .map(node => node.id)
    );
    const labels = labelGroup.selectAll('.node-label')
        .data(data.nodes.filter(n => prominentNodeIds.has(n.id)), d => d.id)
        .join('text')
        .attr('class', 'node-label')
        .text(d => d.handle || d.id)
        .attr('dy', 16)
        .attr('fill', '#e2e8f0')
        .attr('font-size', '10px')
        .attr('text-anchor', 'middle')
        .attr('pointer-events', 'none');

    // Physics Simulation
    simulation = d3.forceSimulation(data.nodes)
        .force('link', d3.forceLink(validEdges).id(d => d.id).distance(82).strength(0.22))
        .force('charge', d3.forceManyBody().strength(-260).distanceMax(520))
        .force('center', d3.forceCenter(width / 2, height / 2))
        .force('x', d3.forceX(width / 2).strength(0.055))
        .force('y', d3.forceY(height / 2).strength(0.055))
        .force('collision', d3.forceCollide().radius(d => 17 + (d.active_marketplaces ? d.active_marketplaces.length : 1) * 2))
        .alphaDecay(0.018)
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

    // Let the layout settle briefly, then show its complete extent in the viewport.
    window.setTimeout(() => fitGraphToViewport(450), 1600);
}

function fitGraphToViewport(duration = 450) {
    if (!simulation || !fullGraphData.nodes.length) return;

    const container = document.getElementById('graph-container');
    const width = container.clientWidth || 900;
    const height = container.clientHeight || 700;
    const positioned = fullGraphData.nodes.filter(n => Number.isFinite(n.x) && Number.isFinite(n.y));
    if (!positioned.length) return;

    const minX = d3.min(positioned, n => n.x);
    const maxX = d3.max(positioned, n => n.x);
    const minY = d3.min(positioned, n => n.y);
    const maxY = d3.max(positioned, n => n.y);
    const graphWidth = Math.max(maxX - minX, 1);
    const graphHeight = Math.max(maxY - minY, 1);
    const scale = Math.max(0.12, Math.min(1.25, 0.86 / Math.max(graphWidth / width, graphHeight / height)));
    const translateX = width / 2 - scale * (minX + maxX) / 2;
    const translateY = height / 2 - scale * (minY + maxY) / 2;

    svg.transition().duration(duration).call(
        zoom.transform,
        d3.zoomIdentity.translate(translateX, translateY).scale(scale)
    );
}

// ---------------------------------------------------------------------------
// Simulation Drag handlers
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

// ---------------------------------------------------------------------------
// Interaction & Highlighting
// ---------------------------------------------------------------------------

function highlightConnected(node) {
    if (activeCommunityId !== null || activePathEntities !== null) return;

    const neighborIds = new Set([node.id]);

    fullGraphData.edges.forEach(e => {
        const s = typeof e.source === 'object' ? e.source.id : e.source;
        const t = typeof e.target === 'object' ? e.target.id : e.target;
        if (s === node.id) neighborIds.add(t);
        if (t === node.id) neighborIds.add(s);
    });

    nodeGroup.selectAll('.node-circle')
        .attr('opacity', d => neighborIds.has(d.id) ? 1 : 0.12);

    linkGroup.selectAll('.link-line')
        .attr('opacity', d => {
            const s = typeof d.source === 'object' ? d.source.id : d.source;
            const t = typeof d.target === 'object' ? d.target.id : d.target;
            return (s === node.id || t === node.id) ? 1 : 0.04;
        });

    labelGroup.selectAll('.node-label')
        .attr('opacity', d => neighborIds.has(d.id) ? 1 : 0.08);
}

function resetHighlight() {
    if (activeCommunityId !== null || activePathEntities !== null) return;

    nodeGroup.selectAll('.node-circle').attr('opacity', 1);
    linkGroup.selectAll('.link-line').attr('opacity', showAllLinks ? 0.32 : 0);
    labelGroup.selectAll('.node-label').attr('opacity', 1);
}

async function selectNode(node) {
    selectedEntityId = node.id;

    // Highlight circle
    nodeGroup.selectAll('.node-circle')
        .classed('highlighted', d => d.id === node.id)
        .attr('stroke', d => d.id === node.id ? '#ffffff' : d3.color(d.color).brighter(0.6))
        .attr('stroke-width', d => d.id === node.id ? 3.5 : 1.5);

    // Fetch live node details and 2-hop connections from API
    try {
        const res = await fetch(`${API_BASE}/api/entity/${encodeURIComponent(node.id)}`);
        if (res.ok) {
            const data = await res.json();
            // Preserve community/color metadata attached to the clicked node.
            renderEntityDetail({ ...node, ...data.entity }, data.connections);
        } else {
            renderEntityDetail(node, []);
        }
    } catch (err) {
        renderEntityDetail(node, []);
    }
}

function deselectNode() {
    selectedEntityId = null;
    nodeGroup.selectAll('.node-circle')
        .classed('highlighted', false)
        .attr('stroke', d => d3.color(d.color).brighter(0.6))
        .attr('stroke-width', 1.5);

    document.getElementById('detail-content').style.display = 'none';
    document.getElementById('detail-empty').style.display = 'flex';
    resetHighlight();
}

// ---------------------------------------------------------------------------
// Detail Panel Rendering
// ---------------------------------------------------------------------------

function renderEntityDetail(entity, connections = []) {
    document.getElementById('detail-empty').style.display = 'none';
    const detailContent = document.getElementById('detail-content');
    detailContent.style.display = 'block';

    document.getElementById('detail-title').textContent = entity.handle || entity.entity_id;
    document.getElementById('detail-subtitle').textContent = entity.entity_id;
    document.getElementById('detail-type-badge').textContent = entity.community == null
        ? 'Community unavailable'
        : `Community #${entity.community + 1}`;
    document.getElementById('detail-type-badge').style.background = entity.color || '#6366f1';

    const markets = entity.active_marketplaces || [];
    const personas = entity.aka_persona_ids || [];

    const sections = document.getElementById('detail-sections');
    sections.innerHTML = `
        <div class="detail-section">
            <h4>Active Darknet Markets (${markets.length})</h4>
            <div style="display:flex; flex-wrap:wrap; gap:6px; margin-top:8px;">
                ${markets.map(m => `<span style="background:#1e293b; color:#38bdf8; padding:3px 8px; border-radius:4px; font-size:11px; font-weight:500;">${m}</span>`).join('')}
            </div>
        </div>

        <div class="detail-section">
            <h4>Cryptographic Identifiers</h4>
            <div style="margin-top:8px; font-family:'JetBrains Mono', monospace; font-size:11px;">
                <div style="color:#94a3b8; margin-bottom:4px;">PGP SHA-1 Fingerprint:</div>
                <div style="background:#0f172a; padding:6px 8px; border-radius:4px; color:#34d399; word-break:break-all;">
                    ${entity.pgp_fingerprint || '—'}
                </div>
                <div style="color:#94a3b8; margin-top:8px; margin-bottom:4px;">Crypto Wallet Address:</div>
                <div style="background:#0f172a; padding:6px 8px; border-radius:4px; color:#fb923c; word-break:break-all;">
                    ${entity.wallet_address || '—'}
                </div>
            </div>
        </div>

        <div class="detail-section">
            <h4>Cross-Module Join Keys (${personas.length} Personas)</h4>
            <p style="font-size:11px; color:#94a3b8; margin-bottom:6px;">Join keys passed to Infra & Stylometry fusion layers:</p>
            <div style="max-height:80px; overflow-y:auto; font-family:'JetBrains Mono', monospace; font-size:11px; color:#a5b4fc; background:#0f172a; padding:6px 8px; border-radius:4px;">
                ${personas.map(p => `<div>${p}</div>`).join('')}
            </div>
        </div>

        <div class="detail-section">
            <h4>Multi-Hop Connected Entities (${connections.length})</h4>
            <div style="max-height:140px; overflow-y:auto; margin-top:8px; display:flex; flex-direction:column; gap:6px;">
                ${connections.map(c => `
                    <div class="cluster-card" style="padding:6px 10px; cursor:pointer;" onclick="focusPath('${entity.entity_id}', '${c.entity_id}')">
                        <div style="display:flex; justify-content:space-between; align-items:center;">
                            <strong style="font-size:12px; color:#f1f5f9;">${c.entity_id}</strong>
                            <span style="font-size:11px; color:#a855f7;">${c.distance} hop${c.distance > 1 ? 's' : ''}</span>
                        </div>
                        <div style="display:flex; justify-content:space-between; font-size:11px; color:#94a3b8; margin-top:2px;">
                            <span>Confidence:</span>
                            <span style="color:#34d399; font-weight:600;">${(c.path_confidence * 100).toFixed(1)}%</span>
                        </div>
                    </div>
                `).join('')}
            </div>
        </div>

        <div class="detail-section" style="margin-top:12px;">
            <h4>Path Finder to Another Entity</h4>
            <div style="display:flex; gap:6px; margin-top:6px;">
                <input type="text" id="target-entity-input" placeholder="e.g. E-AzureHawk831" style="flex:1; background:#0f172a; border:1px solid #334155; color:#f8fafc; padding:6px 8px; border-radius:4px; font-size:12px;">
                <button class="control-btn" style="padding:6px 12px; font-size:11px; width:auto;" onclick="executePathQuery('${entity.entity_id}')">Find</button>
            </div>
            <div id="path-result" style="margin-top:8px; font-size:11px;"></div>
        </div>
    `;
}

// ---------------------------------------------------------------------------
// Path Finder Action
// ---------------------------------------------------------------------------

window.executePathQuery = async function(sourceId) {
    const targetInput = document.getElementById('target-entity-input');
    const targetId = targetInput ? targetInput.value.trim() : '';
    if (!targetId) return;

    const resultBox = document.getElementById('path-result');
    resultBox.innerHTML = '<span style="color:#94a3b8;">Calculating multi-hop path...</span>';

    try {
        const res = await fetch(`${API_BASE}/api/path?source=${encodeURIComponent(sourceId)}&target=${encodeURIComponent(targetId)}`);
        const data = await res.json();

        if (data.connected && data.shortest_path && data.shortest_path.length > 0) {
            resultBox.innerHTML = `
                <div style="background:#0f172a; padding:8px; border-radius:4px; border-left:3px solid #34d399;">
                    <div style="color:#34d399; font-weight:600;">Connected (${data.path_length} hops)</div>
                    <div style="margin:4px 0; color:#e2e8f0; font-family:'JetBrains Mono', monospace; font-size:10px;">
                        ${data.shortest_path.join(' ➔ ')}
                    </div>
                    <div style="display:flex; justify-content:space-between; color:#94a3b8; font-size:10px;">
                        <span>Path Confidence: <strong style="color:#f59e0b;">${(data.path_confidence * 100).toFixed(1)}%</strong></span>
                        <span>Link Strength: <strong style="color:#38bdf8;">${(data.graph_link_strength * 100).toFixed(1)}%</strong></span>
                    </div>
                </div>
            `;
            highlightPath(data.shortest_path);
        } else {
            resultBox.innerHTML = `<span style="color:#f87171;">No connection path found within 3 hops.</span>`;
        }
    } catch (err) {
        resultBox.innerHTML = `<span style="color:#f87171;">Path search error.</span>`;
    }
};

window.focusPath = function(sourceId, targetId) {
    const input = document.getElementById('target-entity-input');
    if (input) {
        input.value = targetId;
        executePathQuery(sourceId);
    }
};

function highlightPath(pathArray) {
    if (!pathArray || pathArray.length === 0) return;
    activePathEntities = new Set(pathArray);

    const pathEdges = new Set();
    for (let i = 0; i < pathArray.length - 1; i++) {
        pathEdges.add(`${pathArray[i]}-${pathArray[i+1]}`);
        pathEdges.add(`${pathArray[i+1]}-${pathArray[i]}`);
    }

    nodeGroup.selectAll('.node-circle')
        .attr('opacity', d => activePathEntities.has(d.id) ? 1 : 0.1)
        .attr('stroke-width', d => activePathEntities.has(d.id) ? 3 : 1.5);

    linkGroup.selectAll('.link-line')
        .attr('opacity', d => {
            const s = typeof d.source === 'object' ? d.source.id : d.source;
            const t = typeof d.target === 'object' ? d.target.id : d.target;
            return (pathEdges.has(`${s}-${t}`) || pathEdges.has(`${t}-${s}`)) ? 1 : 0.03;
        })
        .attr('stroke', d => {
            const s = typeof d.source === 'object' ? d.source.id : d.source;
            const t = typeof d.target === 'object' ? d.target.id : d.target;
            return (pathEdges.has(`${s}-${t}`) || pathEdges.has(`${t}-${s}`)) ? '#f43f5e' : (EDGE_COLORS[d.relation_type] || '#4a5080');
        });
}

// ---------------------------------------------------------------------------
// Sidebar: Louvain Communities List
// ---------------------------------------------------------------------------

function renderCommunitiesSidebar(communities) {
    const list = document.getElementById('cluster-list');
    if (!list) return;

    document.getElementById('cluster-count').textContent = communities.length;
    list.innerHTML = '';

    communities.forEach((comm, idx) => {
        const color = COMMUNITY_COLORS[idx % COMMUNITY_COLORS.length];
        const card = document.createElement('div');
        card.className = 'cluster-card';
        card.dataset.communityId = idx;

        const members = comm.members || [];
        const sampleHandles = members.slice(0, 3).map(m => m.handle || m.entity_id).join(', ');

        card.innerHTML = `
            <div class="cluster-header">
                <span class="cluster-id" style="color:${color}; font-weight:700;">Community #${idx + 1}</span>
                <span class="cluster-badge" style="background:${color}22; color:${color}; font-weight:600;">${comm.size} entities</span>
            </div>
            <div class="cluster-handles" style="font-size:11px; color:#94a3b8; margin-top:4px;">
                ${sampleHandles}${comm.size > 3 ? '…' : ''}
            </div>
        `;

        card.addEventListener('click', () => {
            toggleCommunityFilter(idx, comm);
        });

        list.appendChild(card);
    });
}

function toggleCommunityFilter(commId, commObj) {
    if (activeCommunityId === commId) {
        // Deselect community
        activeCommunityId = null;
        document.querySelectorAll('.cluster-card').forEach(c => c.classList.remove('active'));
        resetHighlight();
        return;
    }

    activeCommunityId = commId;
    activePathEntities = null;

    document.querySelectorAll('.cluster-card').forEach(c => {
        c.classList.toggle('active', parseInt(c.dataset.communityId) === commId);
    });

    const memberSet = new Set((commObj.members || []).map(m => m.entity_id));

    nodeGroup.selectAll('.node-circle')
        .attr('opacity', d => memberSet.has(d.id) ? 1 : 0.08)
        .attr('stroke', d => memberSet.has(d.id) ? '#ffffff' : d3.color(d.color).brighter(0.6));

    linkGroup.selectAll('.link-line')
        .attr('opacity', d => {
            const s = typeof d.source === 'object' ? d.source.id : d.source;
            const t = typeof d.target === 'object' ? d.target.id : d.target;
            return (memberSet.has(s) && memberSet.has(t)) ? 0.9 : 0.02;
        });

    labelGroup.selectAll('.node-label')
        .attr('opacity', d => memberSet.has(d.id) ? 1 : 0.05);
}

// ---------------------------------------------------------------------------
// Search Functionality
// ---------------------------------------------------------------------------

function initSearch() {
    const input = document.getElementById('search-input');
    if (!input) return;

    input.addEventListener('input', (e) => {
        const query = e.target.value.trim().toLowerCase();
        if (!query) {
            resetHighlight();
            return;
        }

        activeCommunityId = null;
        activePathEntities = null;

        const matchIds = new Set();
        fullGraphData.nodes.forEach(n => {
            const handleMatch = n.handle && n.handle.toLowerCase().includes(query);
            const idMatch = n.id && n.id.toLowerCase().includes(query);
            const pgpMatch = n.pgp_fingerprint && n.pgp_fingerprint.toLowerCase().includes(query);
            const walletMatch = n.wallet_address && n.wallet_address.toLowerCase().includes(query);
            const marketMatch = n.active_marketplaces && n.active_marketplaces.some(m => m.toLowerCase().includes(query));

            if (handleMatch || idMatch || pgpMatch || walletMatch || marketMatch) {
                matchIds.add(n.id);
            }
        });

        nodeGroup.selectAll('.node-circle')
            .attr('opacity', d => matchIds.has(d.id) ? 1 : 0.08)
            .attr('stroke-width', d => matchIds.has(d.id) ? 3 : 1.5);

        linkGroup.selectAll('.link-line')
            .attr('opacity', d => {
                const s = typeof d.source === 'object' ? d.source.id : d.source;
                const t = typeof d.target === 'object' ? d.target.id : d.target;
                return (matchIds.has(s) || matchIds.has(t)) ? 0.8 : 0.02;
            });

        labelGroup.selectAll('.node-label')
            .attr('opacity', d => matchIds.has(d.id) ? 1 : 0.05);
    });

    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') {
            input.value = '';
            resetHighlight();
            deselectNode();
        }
    });
}

// ---------------------------------------------------------------------------
// Controls & Export
// ---------------------------------------------------------------------------

function initControls() {
    const linksButton = document.getElementById('btn-toggle-links');
    linksButton?.addEventListener('click', () => {
        showAllLinks = !showAllLinks;
        linksButton.textContent = `Links: ${showAllLinks ? 'On' : 'Off'}`;
        if (activeCommunityId === null && activePathEntities === null && selectedEntityId === null) {
            resetHighlight();
        }
    });

    document.getElementById('btn-zoom-in')?.addEventListener('click', () => {
        svg.transition().duration(300).call(zoom.scaleBy, 1.3);
    });

    document.getElementById('btn-zoom-out')?.addEventListener('click', () => {
        svg.transition().duration(300).call(zoom.scaleBy, 0.75);
    });

    document.getElementById('btn-fit')?.addEventListener('click', () => {
        fitGraphToViewport();
    });

    document.getElementById('btn-reset-view')?.addEventListener('click', () => {
        activeCommunityId = null;
        activePathEntities = null;
        document.querySelectorAll('.cluster-card').forEach(c => c.classList.remove('active'));
        resetHighlight();
        deselectNode();
        fitGraphToViewport();
        showToast('Graph view reset', 'info');
    });
}

function initExport() {
    document.getElementById('btn-export-json')?.addEventListener('click', () => {
        window.open(`${API_BASE}/api/graph`, '_blank');
    });

    document.getElementById('btn-export-csv')?.addEventListener('click', () => {
        const rows = [
            ['entity_id', 'handle', 'active_marketplaces', 'pgp_fingerprint', 'wallet_address', 'community_id']
        ];
        fullGraphData.nodes.forEach(n => {
            rows.push([
                n.id,
                n.handle || '',
                (n.active_marketplaces || []).join('; '),
                n.pgp_fingerprint || '',
                n.wallet_address || '',
                n.community ?? 0
            ]);
        });
        const csvContent = 'data:text/csv;charset=utf-8,' + rows.map(e => e.map(i => `"${i}"`).join(',')).join('\n');
        const encodedUri = encodeURI(csvContent);
        const link = document.createElement('a');
        link.setAttribute('href', encodedUri);
        link.setAttribute('download', 'entity_graph_nodes.csv');
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        showToast('CSV exported', 'success');
    });
}

function showToast(message, type = 'info') {
    const container = document.getElementById('toast-container');
    if (!container) return;

    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.textContent = message;
    container.appendChild(toast);

    setTimeout(() => {
        toast.remove();
    }, 3500);
}
