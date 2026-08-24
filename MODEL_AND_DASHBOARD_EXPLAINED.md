# SIH26151 — Module 2: Entity Relationship Graph & Dashboard Guide
## Comprehensive Technical Documentation, Graph Semantics & Analyst Walkthrough

**Project Title**: De-anonymization of Dark Web Threat Actors  
**Organization**: NTRO (National Technical Research Organisation) | **Category**: Software  
**Module**: Module 2 of 4 (Entity Relationship Graph Engine & Visualization)  
**Authors/Maintainers**: Nipun (Build Lead), Saraa (Design/Handoff)

---

## 📑 Table of Contents
1. [Executive Summary: What This Module Does](#1-executive-summary-what-this-module-does)
2. [Underlying Data & Realistic Modeling](#2-underlying-data--realistic-modeling)
3. [The Core Model Architecture](#3-the-core-model-architecture)
   - [3.1 Canonical Entity Collapse (Intra-Actor Resolution)](#31-canonical-entity-collapse-intra-actor-resolution)
   - [3.2 The Property MultiDiGraph Engine](#32-the-property-multidigraph-engine)
   - [3.3 Multi-Hop Traversal & Evidential Scoring](#33-multi-hop-traversal--evidential-scoring)
   - [3.4 Louvain Community Detection (Syndicate Clustering)](#34-louvain-community-detection-syndicate-clustering)
   - [3.5 Cross-Module Fusion Contract](#35-cross-module-fusion-contract)
4. [The Interactive Dashboard: Complete Visual Semantics](#4-the-interactive-dashboard-complete-visual-semantics)
   - [4.1 What Every Node Represents](#41-what-every-node-represents)
   - [4.2 What Every Connection Line (Edge) Represents](#42-what-every-connection-line-edge-represents)
   - [4.3 UI Component Breakdown](#43-ui-component-breakdown)
5. [Step-by-Step Investigation Walkthrough](#5-step-by-step-investigation-walkthrough)
6. [Mathematical & Algorithmic Specifications](#6-mathematical--algorithmic-specifications)
7. [Official Pitch & Defense Guidelines for Judges](#7-official-pitch--defense-guidelines-for-judges)

---

## 1. Executive Summary: What This Module Does

On the dark web, sophisticated threat actors operate under multiple aliases across dozens of marketplaces (e.g., *Agora, Silk Road 2, Evolution, AlphaBay, Wall Street, Hydra*). They communicate in encrypted forums, exchange cryptocurrency, and vouch for one another to build illicit reputation.

A human investigator looking at raw marketplace listings sees only fragmented records:
* An actor named `VoidFox414` on *Agora*.
* An actor named `VoidFox414` on *Evolution*.
* Another actor named `IronCrypt324` on *Silk Road 2*.

**Module 2 (Entity Relationship Graph)** automatically:
1. **Collapses fragmented identity surfaces** across 23 marketplaces into unified **Canonical Entity Profiles** using shared cryptographic fingerprints and wallet reuse patterns.
2. **Constructs a multi-relational property graph** capturing operational relationships (`VOUCHED_FOR`, `TRANSACTED_WITH`, `CO_OCCURRED_IN_THREAD`).
3. **Executes Multi-Hop Graph Traversal** to uncover hidden indirect links (e.g., *Actor A connects to Actor C through an intermediary transaction with Actor B two hops away*), computing mathematically rigorous confidence decay and link strength scores.
4. **Discovers Threat Syndicates** using Louvain modularity clustering.
5. **Serves an interactive visual dashboard** for cyber-intelligence analysts and feeds structured scoring to the **Module 4 Fusion Engine**.

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                        MODULE 2 — GRAPH DE-ANONYMIZATION PIPELINE                      │
└────────────────────────────────────────────────────────────────────────────────────────┘
                                           │
  [1] 1,833 Raw Scraped Personas Across 23 Historical Darknet Markets
                                           │
                                           ▼
  [2] Canonical Entity Collapse (Group by Handle & Verify PGP/Wallet Clues)
      ──► Yields 500 Unique Canonical Entities (e.g., E-VoidFox414)
                                           │
                                           ▼
  [3] MultiDiGraph Construction (2,490 Directed & Symmetric Cross-Entity Edges)
      ──► VOUCHED_FOR (510) | TRANSACTED_WITH (990) | CO_OCCURRED (990)
                                           │
                                           ▼
  [4] Graph Traversal & Analytics Engine
      ├── Multi-Hop Shortest Path (BFS with Cutoff = 3)
      ├── Path Confidence Decay: P(Path) = ∏ Confidence(edge_i)
      ├── Graph Link Strength: Best_Conf × (1 + 0.1 × log2(N_paths))
      └── Louvain Community Modularity Detection (23 Underground Clusters)
                                           │
                    ┌──────────────────────┴──────────────────────┐
                    ▼                                             ▼
        [5] Fusion JSON Export                       [6] Interactive D3.js
        (entity_graph_output.json)                       Visual Dashboard
        Fed to Module 4 Fusion Engine                 (http://localhost:5000)
```

---

## 2. Underlying Data & Realistic Modeling

The dataset is calibrated against the **Gwern Darknet Market Archive** (180,317 real darknet listings across 5,788 vendors and 8 historical markets).

* **Nodes Dataset (`module2_entity_graph_nodes_ANON.csv`)**:
  - **1,833 persona records**.
  - **500 unique threat actor handles**.
  - **23 marketplaces** (e.g., *Agora, Silk Road 2, Evolution, Nucleus, Abraxas, 1776, Dream Market, AlphaBay, Hansa, Hydra, Wall Street, Torrez*).
  - Handles are anonymized placeholder names (`VoidFox414`, `CrimsonByte850`, `AshenArc682`) so no fabricated identity claims are tied to real persons, while fully preserving real-world graph topologies, migration patterns, and OpSec mistakes.
* **Edges Dataset (`module2_entity_graph_edges_ANON.csv`)**:
  - **4,156 total relation rows**.
  - `SHARED_PGP_AND_WALLET` (2,656 edges, fixed 0.98 confidence) — connects multi-market instances of the same actor.
  - `VOUCHED_FOR` (510 edges, 0.40–0.88 confidence) — reputation vouches.
  - `CO_OCCURRED_IN_THREAD` (495 symmetric edges, 0.40–0.88 confidence) — forum co-presence.
  - `TRANSACTED_WITH` (495 symmetric edges, 0.40–0.88 confidence) — crypto/escrow transactions.

---

## 3. The Core Model Architecture

### 3.1 Canonical Entity Collapse (Intra-Actor Resolution)
In raw scrapes, a single vendor operating on 5 marketplaces generates 5 disconnected records with 10 pairwise `SHARED_PGP_AND_WALLET` edges (a complete clique).
* **The Problem**: Running pathfinding across uncollapsed raw records creates trivial bouncing paths through duplicate accounts of the same vendor, inflating metrics and distorting path confidence.
* **Our Solution (Locked Architecture)**:
  `graph_engine.py` groups records by `handle`, verifies identical PGP fingerprints (`40-hex SHA1`) and Bitcoin addresses (`1...`), and collapses them into **1 single Canonical Entity Node**:
  $$\text{Entity ID} = \text{E-}\{\text{Handle}\} \quad (\text{e.g., } \text{E-VoidFox414})$$
  Every entity preserves:
  - `aka_persona_ids`: Complete array of all underlying raw persona UUIDs.
  - `active_marketplaces`: Complete list of forums/markets where this actor operates.
  - `first_seen` / `last_seen`: Activity timeframe across darknet history.

### 3.2 The Property MultiDiGraph Engine
Built using `networkx.MultiDiGraph`:
- Allows **parallel edges** between entities (e.g., Actor A both *vouched for* and *transacted with* Actor B). Multiple independent relationships strengthen the evidential weight.
- **Directionality**:
  - `VOUCHED_FOR`: Directional edge ($A \rightarrow B$).
  - `TRANSACTED_WITH` & `CO_OCCURRED_IN_THREAD`: Bidirectional symmetric edges ($A \leftrightarrow B$).

### 3.3 Multi-Hop Traversal & Evidential Scoring
Implemented in `traversal.py`. Real-world threat actors frequently avoid direct transactions with one another. Multi-hop traversal uncovers indirect trust chains:

```
[Target Actor A] ──[TRANSACTED_WITH: 0.85]──► [Broker B] ──[VOUCHED_FOR: 0.80]──► [Target Actor C]
```

1. **Shortest & All Simple Paths**: Breadth-First Search (BFS) bounded at cutoff $k=3$ hops (preventing noisy, unexplainable deep traversals).
2. **Path Confidence ($\text{PathConf}$)**: Multiplies edge confidences along the traversal chain. Confidence naturally and explainably decays over intermediate hops:
   $$\text{PathConf}(P) = \prod_{i=1}^{k} \text{confidence}(e_i)$$
   *(Example: $0.85 \times 0.80 = 0.68$ confidence over a 2-hop chain).*
3. **Graph Link Strength ($\text{LinkStrength}$)**: Synthesizes the strongest single path's confidence with the redundancy of alternative independent paths:
   $$\text{LinkStrength}(u, v) = \min\left(1.0, \; \max_{p \in \text{Paths}} \text{PathConf}(p) \times \left(1.0 + 0.1 \times \log_2(|\text{Paths}|)\right)\right)$$

### 3.4 Louvain Community Detection (Syndicate Clustering)
Applies the Louvain modularity optimization algorithm (`networkx.community.louvain_communities`) across the 500 canonical entities:
- Discovers **23 tightly interconnected darknet syndicates / operational rings**.
- Allows cyber investigators to isolate entire collaborative vendor rings at a single click.

### 3.5 Cross-Module Fusion Contract
Outputs `data/entity_graph_output.json`.
- **Join Key**: `persona_id` (via `aka_persona_ids`).
- **Data Delivered to Module 4 (Fusion)**:
  ```json
  {
    "entity_id_a": "E-VoidFox414",
    "entity_id_b": "E-IronCrypt324",
    "connected": true,
    "path_length": 2,
    "path_confidence": 0.7569,
    "graph_link_strength": 0.8326,
    "shortest_path": ["E-VoidFox414", "E-Intermediary", "E-IronCrypt324"],
    "evidence_path": [
      {"from": "E-VoidFox414", "to": "E-Intermediary", "relation_type": "TRANSACTED_WITH", "confidence": 0.87},
      {"from": "E-Intermediary", "to": "E-IronCrypt324", "relation_type": "VOUCHED_FOR", "confidence": 0.87}
    ]
  }
  ```

### 3.6 Supervised Machine Learning Link Prediction Model (`model_trainer.py`)
Module 2 provides a **Supervised Graph Machine Learning Link Prediction Model** trained under a strict **Edge-Holdout Evaluation Protocol** to genuinely predict unseen relationships without graph feature leakage.

#### ⚠️ Audit Note: Legacy Metric Invalidation
* **Previous Row-Split Metric (~0.97 ROC-AUC)**: **INVALID / LEAKED**.
  * *Why*: In the preliminary prototype, features were generated on the full graph prior to row-level splitting, which allowed shortest-path and neighborhood algorithms to observe the direct target edges being predicted.
* **Current Edge-Holdout Metric (Strict Zero-Leakage)**: **VALID & SCIENTIFICALLY SOUND**.
  * *Edge-Holdout Protocol*: The 1,475 ground-truth entity relationships are split 80% ($N=1,180$) into $G_{\text{train}}$ and 20% ($N=295$) held out into $G_{\text{test}}$.
  * *Zero Leakage*: $G_{\text{train}}$ contains 0 held-out test relationships (neither forward nor reverse).
  * *Candidate Edge Masking*: During training feature extraction on $G_{\text{train}}$, candidate edges are dynamically masked to eliminate direct length-1 path shortcuts.
  * *Isolated Community Detection*: Louvain community partitions are generated strictly on $G_{\text{train}}$.

#### Topological & Behavioral Feature Vectors ($d=17$):
1. `same_community` (43.6%) — Louvain syndicate co-membership on $G_{\text{train}}$.
2. `graph_link_strength` (6.3%) — Non-linear multi-path redundancy score.
3. `path_confidence` (6.0%) — Multiplicative confidence along indirect paths.
4. `preferential_attachment` (5.4%) — Scale-free degree interaction: $|\Gamma(u)| \times |\Gamma(v)|$.
5. `shortest_path_length` (5.4%) — Indirect path distance in $G_{\text{train}}$ (excluding target edge).
6. `degree_v`, `degree_u`, `degree_ratio`, `degree_diff` — Centrality and degree disparity measures.
7. `adamic_adar_index` & `resource_allocation_index` — Frequency-weighted resource transfer metrics.
8. `market_jaccard` & `market_overlap_count` — Darknet marketplace footprint overlap.
9. `jaccard_coefficient` & `common_neighbors_count` — Neighborhood overlap metrics.

#### Genuine Unseen Link Prediction Benchmark Results (Hold-Out Test Set):
* **Model Selected**: `RandomForestClassifier` (100 estimators, max depth 8)
* **Confusion Matrix**: $[[\text{TN}=261, \text{FP}=34], [\text{FN}=189, \text{TP}=106]]$
* **Accuracy**: **`62.20%`**
* **Precision**: **`75.71%`** (High precision: 3 out of 4 predicted links are genuine threat actor collaborations)
* **Recall (Sensitivity)**: **`35.93%`**
* **Specificity**: **`88.47%`** (Strong ability to filter out unrelated entity pairs)
* **F1-Score**: **`0.4874`**
* **Matthews Correlation Coefficient (MCC)**: **`0.2869`**
* **ROC-AUC Score**: **`0.6394`** (5-Fold Edge Cross-Validation: **`0.6571`** $\pm 0.0173$)
* **PR-AUC (Average Precision)**: **`0.6719`**
* **Artifacts**: Serialized model in [`data/link_prediction_model.pkl`](file:///c:/Users/savag/Downloads/De-Anonymity/data/link_prediction_model.pkl), metrics in [`data/model_metrics.json`](file:///c:/Users/savag/Downloads/De-Anonymity/data/model_metrics.json).

---

## 4. The Interactive Dashboard: Complete Visual Semantics

The dashboard is served locally at **`http://localhost:5000`** via a lightweight Flask backend and rendered in real-time using **D3.js (v7)** with a physics-driven force layout.

```
┌────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│ TOP NAV: [Brand: De-Anonymity]   [Live Search: Handles, PGP, Wallets, Markets]   [Reset] [Export JSON/CSV] │
├──────────────────────────────┬──────────────────────────────────────────┬──────────────────────────────┤
│ LEFT SIDEBAR                 │ CENTER: INTERACTIVE GRAPH CANVAS         │ RIGHT DETAIL PANEL           │
│                              │                                          │                              │
│ • 23 Louvain Communities     │ • 500 Canonical Entity Circles           │ • Threat Actor Profile Card  │
│   (Click to isolate cluster) │ • 1,482 Color-Coded Relationship Lines   │ • PGP & Bitcoin Identifiers  │
│ • Global Metrics Footer:     │ • Physics simulation (Drag, Zoom, Pan)   │ • Marketplaces Badges        │
│   - 500 Entities             │ • Hover spotlight & Path Trails          │ • Cross-Module Join Keys     │
│   - 1,482 Graph Edges        │                                          │ • 2-Hop Neighbor Ranking     │
│   - 1,833 Raw Personas       │                                          │ • Live Path Search Tool      │
│   - 23 Detected Rings        │                                          │   (Find shortest path)       │
└──────────────────────────────┴──────────────────────────────────────────┴──────────────────────────────┘
```

---

### 4.1 What Every Node Represents

Every circle on the graph is a **Canonical Threat Actor Entity** ($N = 500$).

```
                      ┌────────────────────────────────────────┐
                      │            NODE ANATOMY                │
                      └────────────────────────────────────────┘

                                   ░░░░░░░░░░░░
                                ░░              ░░
                              ░░   E-VoidFox414   ░░  ◄── Label (prominent vendors)
                             ░░   (Handle Name)    ░░
                              ░░                  ░░
                                ░░              ░░
                                   ░░░░░░░░░░░░
                                        │
           ┌────────────────────────────┼────────────────────────────┐
           ▼                            ▼                            ▼
      [NODE COLOR]                 [NODE SIZE]                 [NODE BORDER]
  Community Membership        Marketplace Footprint &       Selection & Highlight
   (24 Curated Colors)          Connectivity Degree           (White Ring on Focus)
```

| Visual Property | What It Tells the Investigator | Underlying Calculation |
|---|---|---|
| **Node Identity** | Unique canonical darknet threat actor. | `entity_id` (e.g. `E-VoidFox414`), representing all marketplace instances of that vendor. |
| **Node Color** | The underground **syndicate/ring** the actor belongs to. | Colored by **Louvain Community ID** (24 curated neon/pastel colors). Actors with the same color frequently trade, vouch, and co-post together. |
| **Node Size (Radius)** | The actor's **operational reach & importance**. | Radius $R = 6 + 1.5 \times |\text{Marketplaces}| + 0.4 \times \text{Degree}$. Larger nodes represent large-scale vendors active across many markets with high connectivity. |
| **Node Border** | Focus state. | White highlight ring ($3.5\text{px}$) when clicked or when part of an active multi-hop search trail. |
| **Node Label** | Vendor name. | Displays handle name for high-degree/multi-market actors. |

---

### 4.2 What Every Connection Line (Edge) Represents

Every line connecting two circles is an **OSINT / Cryptographic / Behavioral Relationship** ($E = 1,482$).

```
[Actor A] ───────────────[ Colored Relationship Line ]───────────────► [Actor B]
```

| Edge Type | Visual Style | Real-World Intelligence Meaning | Confidence Weight |
|---|---|---|---|
| `VOUCHED_FOR` | **Solid Indigo Line** (`#6366f1`) | **Reputation Vouch**: Actor A publicly backed or verified the authenticity of Actor B on an underground forum/escrow thread. | `0.40` to `0.88` |
| `TRANSACTED_WITH` | **Solid Cyan / Teal Line** (`#06b6d4`) | **Crypto / Escrow Interaction**: Actor A and Actor B exchanged Bitcoin or conducted multisig escrow deals. | `0.40` to `0.88` |
| `CO_OCCURRED_IN_THREAD` | **Solid Amber Line** (`#f59e0b`) | **Forum Co-Presence**: Both actors actively participated in the same specialized discussion thread, vendor review, or trade dispute. | `0.40` to `0.88` |
| `MULTI_HOP_TRAIL` | **Crimson Glowing Trail** (`#f43f5e`) | **Discovered Indirect Connection**: The computed shortest path connecting two distant actors through intermediaries. | Product of edge weights along the trail |

* **Line Thickness**: Thicker lines indicate higher evidential confidence ($w \propto \text{confidence}$).
* **Hover Interaction**: Hovering over any node dims all unrelated nodes to $12\%$ opacity, spotlighting immediate first-degree connections and their relationship types.

---

### 4.3 UI Component Breakdown

#### 1. Top Navigation Bar
- **Brand Badge**: `De-Anonymity | MODULE 2 — ENTITY GRAPH`.
- **Omni-Search Bar (`#search-input`)**: Real-time search across all 500 handles, 40-hex PGP fingerprints, Bitcoin addresses, and marketplace names. Pressing `Esc` clears search.
- **Action Buttons**:
  - **Reset View (`⌘`)**: Clears all filters, resets zoom to center, and restores full graph opacity.
  - **Export JSON**: Downloads the complete graph export consumable by Module 4 Fusion.
  - **Export CSV**: Downloads a flat CSV of all 500 entities, their PGP/wallet addresses, and community memberships.

#### 2. Left Sidebar: Entity Communities (`#sidebar`)
- **Community Cards**: Lists all 23 detected Louvain syndicates with their member count and sample vendor names.
- **Filter Action**: Clicking any community card spotlights all members of that syndicate in the graph, dimming the rest of the network.
- **Global Intelligence Footer**: Live counters showing Total Entities (`500`), Graph Edges (`1,482`), Underlying Personas (`1,833`), and Detected Clusters (`23`).

#### 3. Right Detail Panel: Threat Actor Profile (`#detail-panel`)
When an investigator clicks any node, the panel populates:
- **Header**: Vendor handle name, entity ID, and Community badge.
- **Active Darknet Markets**: Pill badges showing all markets where the vendor operated (e.g. `Agora`, `Silk Road 2`, `Evolution`, `AlphaBay`).
- **Cryptographic Identifiers**:
  - `PGP SHA-1 Fingerprint` (in glowing green).
  - `Crypto Wallet Address` (in glowing orange).
- **Cross-Module Join Keys**: Raw `persona_id` array (`P-3ae0dfac...`) passed to Module 1 and Module 3.
- **Multi-Hop Connected Entities**: Top 2-hop neighbors ranked by path confidence percentage.
- **Interactive Path Finder**: Allows the analyst to enter any target Entity ID (e.g., `E-AzureHawk831`) and click **Find** to calculate the live shortest path, hop count, path confidence, and highlight the glowing crimson path on the canvas.

---

## 5. Step-by-Step Investigation Walkthrough

### Scenario: Investigating Multi-Market Vendor `E-AshenArc682`

1. **Step 1 — Search**: The analyst types `AshenArc` in the top search bar.
   - The graph instantly filters, highlighting `E-AshenArc682` and its immediate neighborhood.
2. **Step 2 — Profile Inspection**: The analyst clicks the node `E-AshenArc682`.
   - The Right Panel opens, showing active presence across *Agora, AlphaBay, and Evolution*.
   - Displays its PGP key `A7B89...` and Bitcoin address `14Qk...`.
   - Lists 3 raw `persona_id` keys joined across Infra and Stylometry modules.
3. **Step 3 — Syndicate Isolation**: The analyst clicks the Community badge `Community #1`.
   - The canvas focuses on the 32 entities comprising this specific counterfeit/narcotics ring.
4. **Step 4 — Multi-Hop Path Discovery**: In the Path Finder box, the analyst enters `E-AzureHawk831` and clicks **Find**.
   - The model finds an indirect 2-hop connection:
     $$\text{E-AshenArc682} \xrightarrow{\text{TRANSACTED\_WITH (0.87)}} \text{E-IronCrypt324} \xrightarrow{\text{VOUCHED\_FOR (0.87)}} \text{E-AzureHawk831}$$
   - Displays **Path Confidence: 75.7%**, **Link Strength: 83.3%**.
   - The canvas illuminates the crimson path trail connecting the two actors through the intermediary.
5. **Step 5 — Export**: The analyst clicks **Export JSON** to hand off the evidential path to the Fusion layer (Module 4) for multi-signal attribution.

---

## 6. Mathematical & Algorithmic Specifications

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                              MATHEMATICAL FORMULATIONS                                 │
└────────────────────────────────────────────────────────────────────────────────────────┘

1. CANONICAL COLLAPSE SANITY CHECK:
   ∀ (p_i, p_j) ∈ E_SHARED : Entity(p_i) == Entity(p_j)   (0 Violations Allowed)

2. MULTI-HOP PATH CONFIDENCE DECAY:
   PathConf(p) = ∏_{e ∈ p} weight(e)    where weight(e) ∈ [0.40, 0.88]

3. MULTI-PATH EVIDENTIAL LINK STRENGTH:
   LinkStrength(u, v) = min(1.0,  max_{p} PathConf(p) × (1 + 0.1 × log2(|Paths|)))

4. LOUVAIN MODULARITY OPTIMIZATION:
   Q = 1/(2m) ∑_{ij} [ A_{ij} - (k_i k_j)/(2m) ] δ(c_i, c_j)
```

---

## 7. Official Pitch & Defense Guidelines for Judges

When presenting Module 2 to hackathon judges, **use this exact wording**:

> *"We modeled an entity relationship graph from real dark-web marketplace patterns — 500 canonical threat actors across 23 historical marketplaces, resolving 1,833 fragmented scrapes using cryptographic PGP and crypto wallet reuse.*
>
> *We implemented multi-hop graph traversal and Louvain community detection rather than a black-box Graph Neural Network. For cyber threat intelligence and legal evidence, explicit traversal across a canonical property graph provides full explainability, verifiable confidence decay over intermediate hops, and zero training overhead — enabling an analyst to trace exactly how Actor A links to Actor C through intermediary transactions."*

### Key Clarifications:
- **Do NOT claim**: "We tracked real individuals."
- **DO claim**: "We calibrated our graph structure and market footprints against 180,000 listings from the Gwern darknet market archive, using fabricated identity labels to demonstrate provable de-anonymization and multi-hop graph attribution against ground truth."
