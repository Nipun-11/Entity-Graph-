# 🌐 SIH26151 — Cross-Module Data Architecture & Synthesis Blueprint

**Project Title**: De-anonymization of Dark Web Threat Actors and Linking to Suspect Real-World Entities  
**Document Purpose**: Definitive blueprint specifying which **Real-World Datasets** are merged across all modules and exactly which **Network/Behavioral Signals** must be synthetically generated or derived to achieve 100% cross-module data consistency.

---

## 📌 Executive Summary: The Single Source of Truth

To prevent data incompatibility across the team, all 3 analytical modules must consume one common master file: **`master_personas.json`** (as specified in [unified_canonical_schema.md](file:///c:/Users/harsh/OneDrive/Documents/projects/tordeanon/unified_canonical_schema.md)).

```
                                  ┌────────────────────────────────────────────────────────┐
                                  │               REAL DARKNET RAW ARCHIVES                │
                                  │  • Gwern Darknet Market Archive (180k listings)        │
                                  │  • Netsec-SJTU 2021 Dataset (367k listings)            │
                                  │  • Swan07 DarkReddit Forum Corpus (412 threads)        │
                                  └───────────────────────────┬────────────────────────────┘
                                                              │
                                                              ▼
                                  ┌────────────────────────────────────────────────────────┐
                                  │                  master_personas.json                  │
                                  │             (Single Shared Master Source)              │
                                  │                                                        │
                                  │  • actor_id: "ACTOR-01" (Ground Truth Identity)        │
                                  │  • persona_id: "P-3ae0dfac" (Permanent Join Key)       │
                                  │  • handle: "blackhand" (Real Darknet Handle)           │
                                  │  • marketplace: "Agora" (Real Darknet Market)          │
                                  │  • pgp_fingerprint: "635CAC38E7B1..." (40-hex)         │
                                  │  • wallet_address: "15FYrsK9EjHv..." (BTC / XMR)       │
                                  │  • hidden_service_url: "agorabasement7x9k.onion"       │
                                  └───────┬───────────────────┼────────────────────┬───────┘
                                          │                   │                    │
                        ┌─────────────────┘                   │                    └─────────────────┐
                        ▼                                     ▼                                      ▼
             ┌─────────────────────┐               ┌─────────────────────┐                ┌─────────────────────┐
             │      MODULE 1       │               │      MODULE 2       │                │      MODULE 3       │
             │   Infra & Timing    │               │    Entity Graph     │                │  Stylometry & Ops   │
             │  (Network Traffic)  │               │   (OSINT & Crypto)  │                │ (NLP & Behavioral)  │
             └──────────┬──────────┘               └──────────┬──────────┘                └──────────┬──────────┘
                        │                                     │                                      │
                        └─────────────────────────────────────┼──────────────────────────────────────┘
                                                              │
                                                              ▼
                                  ┌────────────────────────────────────────────────────────┐
                                  │             MODULE 4: FUSION ENGINE                    │
                                  │     Merges: (persona_id_a, persona_id_b, confidence)   │
                                  └────────────────────────────────────────────────────────┘
```

---

## 📊 Detailed Module-by-Module Breakdown

---

### 1️⃣ Module 1: Tor Misconfiguration & Timing Matcher (Member 1)
* **Goal**: Detect co-located hidden services, SSL/TLS certificate leaks, banner fingerprints, and correlated network response latencies.

| Data Attribute | Type | Source / How to Obtain | Why Synthetic / Real? |
|---|---|---|---|
| **Marketplace Onion Domains** (`hidden_service_url`) | **Real** | Historical `.onion` addresses of Agora, Silk Road 2, Evolution, Nucleus, Dread (`silkroad6ownowfk.onion`, `agorabasement.onion`). | Real darknet infrastructure addresses. |
| **Server Banners & Cert Fingerprints** (`banner_string`, `cert_fingerprint`) | **Semi-Real** | Real web server headers (e.g., `nginx/1.4.6`, `Apache/2.4.7 (Ubuntu)`, OpenSSL self-signed SHA256 hashes). | Real server header formats; deliberate leaks to clearnet IP mapped in master file. |
| **Tor Circuit Latency Traces** (`response_latency_ms`, `jitter`) | **Synthetic** | Generated via `scipy.stats.norm` / `gamma` distribution time-series (e.g. Co-located services share mean $\mu = 450\text{ms}, \sigma = 35\text{ms}$). | **Must be synthetic** because web archives contain static HTML/CSV scrapes, not live Wireshark/NetFlow packet timing captures. |

---

### 2️⃣ Module 2: Entity Relationship Graph (Member 2)
* **Goal**: Build a multi-hop property graph connecting vendor handles, PGP key fingerprints, crypto wallets, and trust vouches.

| Data Attribute | Type | Source / How to Obtain | Why Synthetic / Real? |
|---|---|---|---|
| **Vendor Handles & Marketplaces** (`handle`, `marketplace`) | **Real** | Extracted directly from Gwern Darknet Market Archive (`blackhand`, `DoctorFreedom`, `Drugs4you`, `MedIndia`). | Real darknet threat actor entities. |
| **PGP Key Fingerprints** (`pgp_fingerprint`) | **Real Format** | 40-character hexadecimal SHA-1 key IDs formatted from PGP public key blocks. | Derived from real vendor profiles. |
| **Crypto Wallet Addresses** (`wallet_address`) | **Real Format** | Authentic Bitcoin (P2PKH `1...`, P2SH `3...`, Bech32 `bc1...`) and Monero (`4...`) addresses. | Grounded in authentic cryptocurrency address formats. |
| **Multi-Hop Trust Links & Vouch Edges** (`trust_links[]`) | **Synthetic / Controlled Ground Truth** | Explicit edges: `vendor_A --[VOUCHED_FOR]--> vendor_B` and `vendor_A --[SHARED_WALLET]--> vendor_C`. | **Controlled Ground Truth**: In unlabelled darknet dumps, ground-truth Sybil links are police secrets. A controlled set of 10–15 ground-truth edges must be injected to demonstrate multi-hop graph traversal. |

---

### 3️⃣ Module 3: Stylometry & Operational Profiling (Member 3 - Harshit)
* **Goal**: Disambiguate threat actors by analyzing linguistic habits (word/char TF-IDF, 55 function words, TTR) and operational behavioral patterns (24h UTC posting, market sequences, shipping routes).

| Data Attribute | Type | Source / How to Obtain | Why Synthetic / Real? |
|---|---|---|---|
| **Vendor Text & Descriptions** (`product_description`, `title`) | **100% Real** | Gwern Darknet Market Archive (`180,317 listings`) + Swan07 DarkReddit forum corpus (`412 underground posts`). | Real writing style written by authentic darknet vendors. |
| **Marketplace Presence & Sequence** (`marketplace`, `market_sequence`) | **100% Real** | Real multi-market presence vectors across `Agora`, `Silk Road 2`, `Evolution`, `Nucleus`, `Abraxas`, `1776`, etc. | 100% real historical migration data. |
| **Shipping Logistics Footprint** (`ship_from`, `ship_to`) | **100% Real** | Real origin/destination geography (`Germany`, `United States`, `United Kingdom`, `Canada`, `EU`, `Worldwide`). | 100% real shipping origin data. |
| **24-hour UTC Posting Clock** (`posting_hour_utc`) | **Real / Derived** | Extracted from real timestamps in Swan07 / Dread forum archives; mapped to a 24-bin histogram for listing-only vendors. | Authentic active-hour distribution. |
| **PGP Key Rotation Cadence** (`key_rotation_interval`) | **Derived** | Extracted from regex mentions of PGP update warnings or modeled rotation cadence (e.g. 30/60/90 days). | Matches darknet vendor OpSec practices. |

---

### 4️⃣ Module 4: Fusion & Confidence Scoring Engine (Member 4)
* **Goal**: Merge signals from Modules 1, 2, and 3 into an unified evidential confidence score.

| Input Signal | Source Module | Join Key | Expected Schema |
|---|---|---|---|
| `cert_match_score`, `timing_similarity_score` | Module 1 (Infra) | `(persona_id_a, persona_id_b)` | `0.0 to 1.0` float |
| `graph_link_strength`, `shared_pgp_wallet` | Module 2 (Entity Graph) | `(persona_id_a, persona_id_b)` | `0.0 to 1.0` float |
| `text_similarity_score`, `operational_similarity_score` | Module 3 (Stylometry) | `(persona_id_a, persona_id_b)` | `0.0 to 1.0` float |

---

## 🗃️ Datasets Master Merge Table

| Dataset Name | Source / Repository | Size | Records | What We Extract | Used in Module |
|---|---|---|---|---|---|
| **Gwern Darknet Market Archive** | [munhouiani/Drug-Listings-Dataset](https://github.com/munhouiani/Drug-Listings-Dataset) | 192 MB (CSV) | 180,317 rows | Real handles, real listing text, shipping origins, 8 real marketplaces (`Agora`, `Silk Road 2`, `Evolution`, `Nucleus`, etc.) | **Stylometry (Mod 3)** + **Entity Graph (Mod 2)** |
| **Netsec-SJTU 2021 Darknet Corpus** | [Netsec-SJTU/darkweb-market-dataset-2021](https://github.com/Netsec-SJTU/darkweb-market-dataset-2021) | 125 MB (Excel) | 367,464 rows | Modern 2021 market vendors (`Vice City`, `Argatha`, `Dutch Master`), product descriptions, categories | **Stylometry (Mod 3)** + **Cross-Era Entity Resolution** |
| **Swan07 Underground Forum Corpus** | [HuggingFace / swan07](https://huggingface.co/datasets/swan07/authorship-verification) | 1.2 MB (CSV) | 412 threads | Real forum discussions on PGP, Monero, Tor relays, Whonix, and exploits with authentic timestamps | **Stylometry (Mod 3)** |
| **Elliptic / Darknet Wallet Cluster** | Academic Public BTC Dumps | ~2 MB (JSON) | 500+ addresses | Authentic P2PKH, P2SH, and Bech32 Bitcoin wallet strings | **Entity Graph (Mod 2)** |
| **Tor Historical Hidden Service Directory** | Tor Metrics / CollecTor | ~500 KB (JSON) | 50+ onion URLs | Authentic `.onion` URLs and SSL certificate subject metadata | **Infra + Timing (Mod 1)** |

---

## ⚙️ Summary: What is REAL vs What is SYNTHESIZED?

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                                 100% REAL DATA                                         │
│  ✔ Vendor Usernames / Handles (blackhand, DoctorFreedom, Drugs4you, MedIndia, etc.)   │
│  ✔ Vendor Text & Product Descriptions (180,000+ real darknet listings)                │
│  ✔ Market Names (Agora, Silk Road 2, Evolution, Nucleus, Abraxas, Vice City, 1776)     │
│  ✔ Operational Shipping Origin & Logistics (Germany, US, UK, Canada, EU, Worldwide)  │
│  ✔ Onion Domain Names (silkroad6ownowfk.onion, agorabasement.onion)                    │
│  ✔ Crypto Wallet & PGP Fingerprint Formats (Valid Base58 BTC, 40-hex SHA1 PGP)        │
└───────────────────────────────────────────┬────────────────────────────────────────────┘
                                            │
                                            ▼
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                              SYNTHESIZED / DERIVED SIGNALS                             │
│  (Why? Because static web scrapes cannot physically record live network wire events)   │
│                                                                                        │
│  ⚡ Active Tor Network Packet Latency & Jitter (Simulated via Normal/Gamma ms arrays)  │
│  ⚡ Ground-Truth Multi-Hop Trust Links (10–15 planted vouches for Graph Traversal)     │
│  ⚡ Controlled Rebrand Pair Ground-Truth (To validate ROC-AUC & Recall for judges)    │
└────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 🚀 Next Action Plan for the Team

1. **Build `generate_canonical_master_dataset.py`**:
   - Merge Gwern (180k rows) + Netsec (367k rows) into **`master_personas.json`**.
   - Create 60–80 real threat actor entities with their multi-market surfaces, valid PGP, wallets, and onion URLs.
2. **Distribute `master_personas.json` to Team Members**:
   - Member 1 (Infra): Takes `.onion` URLs & generates latency arrays.
   - Member 2 (Entity Graph): Takes handles, PGP, & wallets to build the NetworkX / Neo4j graph.
   - Member 3 (Harshit - Stylometry): Takes handles & text to run TF-IDF, 55 function words, and Likelihood Ratio.
   - Member 4 (Fusion): Ingests the 3 JSON output signals and outputs the fused threat alert.
