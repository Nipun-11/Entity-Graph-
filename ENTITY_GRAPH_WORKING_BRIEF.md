# SIH26151 — Entity Relationship Graph Module
## Claude AI Working Document (Member 2)

> **How to use this file:** Paste this entire document at the start of every new Claude session.
> Claude will have full context about what you're building, what already exists,
> and exactly what to work on next — no re-explaining needed.

---

## 1. Project Background

**Competition:** Smart India Hackathon 2026 (SIH26151)
**Problem Statement:** Dark Web Threat Actor De-Anonymization
**Organization:** NTRO (National Technical Research Organisation)
**Category:** Software | **Theme:** Blockchain & Cybersecurity

### What the Overall System Does

The system de-anonymizes dark web threat actors by combining **three independent signals** into one confidence-scored attribution. There is **zero real dark-web data** — everything runs on a synthetic dataset with planted ground truth. This is stated proactively to judges; the system demonstrates the *detection method*, not live scraping.

```
[Module 1 — Infra+Timing]  ──┐
[Module 2 — Entity Graph]  ──┤──► [Module 4 — Fusion Layer] ──► [Module 5 — Dashboard]
[Module 3 — Stylometry]    ──┘
```

| Member | Module | What it does |
|--------|--------|-------------|
| 1 | Infra + Timing | Cert/banner leaks + response-timing fingerprinting |
| **2 (YOU)** | **Entity Graph** | Maps actors across marketplaces via handles, PGP keys, wallets, trust links |
| 3 | Stylometry | Writing style + behavioral habits that survive rebrand |
| 4 | Fusion Layer | Combines all three signals into one adaptive confidence score |
| 5 | Dashboard | Visualizes everything, CSV/JSON/report export |

---

## 2. Your Module — What It Must Do

**From the official PS:** *"mapping threat actors across multiple marketplaces into a single relationship graph of handles, PGP keys, wallets and trust links."*

### Core deliverables (Definition of Done):

- [x] Ingest `investigator_view.json` — flat per-handle records (handle, marketplace, PGP fingerprint, wallet, trust links)
- [x] Build a NetworkX property graph — nodes = Handle/PGPKey/Wallet/Marketplace, edges = USES/POSTS_ON/VOUCHED_BY/TRANSACTED_WITH
- [x] Resolve identity clusters — detect shared PGP/wallet across handles → propose `SAME_ACTOR_AS` edges
- [x] Output confidence scores per edge/cluster (NOT auto-declaring matches — always scored)
- [x] Expose a query interface — `query(handle_id)` → all linked entities + confidence
- [x] Export fusion-layer JSON (`graph_signal_export.json`) — Member 4 consumes this
- [x] Evaluate against `ground_truth.json` — per-category Precision/Recall/F1
- [ ] **Upgrade dataset generator** → 60 actors, 8 categories, 5 anomaly sub-types (IN PROGRESS)
- [ ] **Rewire pipeline** to consume `investigator_view.json` (flat UUID-based format) instead of old `synthetic_personas.json`
- [ ] **Upgrade resolver** for anomaly handling (escrow trap, null fields, rotated PGP)
- [ ] **Per-category evaluation** (not just blended F1)

---

## 3. Graph Schema (Locked)

### Node Types
| Node | Key field | Description |
|------|-----------|-------------|
| `Handle` | `handle_id` (UUID) | One scraped marketplace profile |
| `PGPKey` | `fingerprint` (40-char hex) | Cryptographic identity key |
| `Wallet` | `address` (BTC-like string) | Crypto wallet address |
| `Marketplace` | `name` (string) | The dark web forum/market |

> Actor nodes are NOT built by the module — ground truth only.

### Edge Types
| Edge | Meaning | Weight |
|------|---------|--------|
| `Handle → PGPKey` (USES) | This handle uses this PGP key | — |
| `Handle → Wallet` (USES) | This handle uses this wallet | — |
| `Handle → Marketplace` (POSTS_ON) | This handle is active here | — |
| `Handle → Handle` (VOUCHED_BY) | Trust link — vouch | — |
| `Handle → Handle` (TRANSACTED_WITH) | Trust link — transaction | — |
| `Handle <-> Handle` (SAME_ACTOR_AS) | **Inferred** — with confidence score | 0.0–1.0 |

---

## 4. Data Files (Locked Schema)

### Input — `investigator_view.json` (fed to graph module)
```json
{
  "personas": [
    {
      "handle_id": "<uuid>",
      "handle": "CobaltBroker16",
      "marketplace": "BlackLotus",
      "pgp_fingerprint": "635CAC38E7B1F932881FE71D7B84DF386E8ED4C6",
      "wallet_address": "15FYrsK9EjHvIHCtlRJoWcURYxPY8EcFK1"
    }
  ],
  "trust_links": [
    { "from_handle_id": "<uuid>", "to_handle_id": "<uuid>", "type": "vouched_for | transacted_with" }
  ]
}
```

**Rules:**
- Flat format — one record = one scraped marketplace profile
- `pgp_fingerprint` or `wallet_address` can be `null` (malformed records — resolver must not crash)
- NO `actor_id` anywhere in this file
- Trust links always UUID-referenced (never by name)

### Evaluation Only — `ground_truth.json` (NEVER fed to graph module)
```json
{
  "actor_to_handles": {
    "ACTOR-11": ["<uuid_handle_A>", "<uuid_handle_B>"]
  },
  "categories": {
    "clean_single_handle": ["ACTOR-01"],
    "rebranded_full_reuse": ["ACTOR-11"],
    "rebranded_pgp_only": ["ACTOR-15"],
    "rebranded_wallet_only": ["ACTOR-18"],
    "ambiguous_wallet_overlap": ["ACTOR-22"],
    "ambiguous_trust_only": ["ACTOR-25"],
    "anomalies": ["ACTOR-28"],
    "no_match_noise": ["ACTOR-35"]
  }
}
```

---

## 5. Dataset — Ground Rules (v2 — 60-Actor Target)

### Scale
- **60 synthetic actors** → ~90–110 handle-records
- Dataset generator: `generate_dataset.py` — accepts `n_actors` param, uses `random.seed(42)` (reproducible)
- Bigger scale makes precision/recall statistically meaningful + dashboard looks like a real system

### 8 Categories (proportion-based, scales with `n_actors`)

| Category | Share | Handles/Actor | Expected Resolver Output |
|----------|-------|--------------|--------------------------|
| Clean / unique | ~45% | 1 | **No match** — control group |
| Rebranded — full reuse | ~12% | 2 | **HIGH** (0.90–0.97) — same PGP + same wallet |
| Rebranded — PGP-only | ~6% | 2 | **MED-HIGH** (0.70–0.85) — same PGP, diff wallet |
| Rebranded — wallet-only | ~6% | 2 | **MEDIUM** (0.60–0.85) — same wallet, diff PGP |
| Ambiguous — wallet overlap | ~8% | 2 | **MEDIUM** (0.60–0.85) — coincidental wallet share |
| Ambiguous — trust-link only | ~8% | 2 | **LOW** (0.20–0.35) — no hard identifiers |
| Anomalies | ~10% | varies | See below |
| Noise / no-match | ~5% | 1 | **No edge proposed** |

### 5 Anomaly Sub-Types

| Sub-type key | What it plants | What it tests |
|-------------|---------------|---------------|
| `pgp_multishare` | Same PGP across 3+ handles, different wallets | Resolver doesn't over-cluster on single signal |
| `shared_escrow_wallet` | Same wallet, different actors (mixer/escrow) | **False-positive trap** — ground truth = NOT same actor |
| `malformed_record` | `pgp_fingerprint: null` or `wallet_address: null` | Resolver doesn't crash on missing fields |
| `near_duplicate_name` | ShadowFox34 vs ShadowFox_34, zero identifier overlap | Resolver not fooled by name similarity |
| `rotated_pgp` | Same actor, old PGP on handle A, new PGP on handle B, same wallet + trust link | Combines weak (wallet) + trust to still link |

Each anomaly has `"anomaly_type"` field in ground_truth for per-sub-type reporting to judges.

---

## 6. Confidence Scoring Spec (Resolver Target)

| Signal combination | Target confidence band |
|-------------------|----------------------|
| Shared PGP + shared wallet | **High: 0.90–0.97** |
| Shared PGP only | **Med-High: 0.70–0.85** |
| Shared wallet only | **Medium: 0.60–0.85** |
| Trust-link pattern only | **Low: 0.20–0.35** |
| Shared escrow/mixer wallet (trap) | Should NOT resolve high (cap at 0.40) |
| No shared signal | **No edge proposed** |

**Combination formula:** Noisy-OR: `confidence = 1 - product(1 - score_i)`

**Special rules:**
- If `wallet` is flagged as `shared_escrow` in anomaly context → cap confidence at 0.40
- If any field is `null` → skip that signal silently, do not crash
- `SAME_ACTOR_AS` edge proposed only when combined confidence >= 0.20

---

## 7. Fusion-Layer Output Contract (What Member 4 Consumes)

File: `data/graph_signal_export.json`

```json
{
  "graph_signal": {
    "module": "entity_graph",
    "version": "1.0",
    "timestamp": "<ISO-8601>",
    "clusters": [
      {
        "cluster_id": "C001",
        "handle_ids": ["<uuid_A>", "<uuid_B>"],
        "handles": ["CobaltBroker16", "AshenByte420"],
        "confidence": 0.97,
        "shared_identifiers": {
          "pgp_keys": ["635CAC38..."],
          "wallets": ["15FYrs..."]
        },
        "evidence": [
          { "signal": "shared_pgp_key", "detail": "635CAC38...", "raw_confidence": 0.90 },
          { "signal": "shared_wallet", "detail": "15FYrs...", "raw_confidence": 0.85 }
        ]
      }
    ],
    "pairwise_matches": [
      {
        "handle_id_a": "<uuid>",
        "handle_id_b": "<uuid>",
        "confidence": 0.97,
        "evidence": [...]
      }
    ],
    "statistics": {
      "total_handles": 24,
      "total_clusters": 4,
      "avg_confidence": 0.93
    }
  }
}
```

---

## 8. Current Codebase — What Exists

All files at: `C:\Users\savag\Downloads\De-Anonymity\`

| File | Status | Notes |
|------|--------|-------|
| `generate_dataset.py` | Exists (18-actor pilot) | **Needs upgrade** to 60-actor, 8-category, 5-anomaly spec |
| `investigator_view.json` | Exists | 18-actor pilot output — will be regenerated |
| `ground_truth.json` | Exists | 18-actor pilot output — will be regenerated |
| `graph_engine.py` | Exists | Built on old format (name-based). **Needs rewiring to UUID-based** |
| `identity_resolver.py` | Exists | Works but missing: escrow trap, null-field safety, rotated-PGP logic |
| `query_interface.py` | Exists | Flask REST + Python function API |
| `export.py` | Exists | Fusion-layer JSON + CSV — **needs UUID handle_ids in output** |
| `evaluate.py` | Exists | Blended F1 only — **needs per-category breakdown** |
| `main.py` | Exists | Pipeline orchestrator — **needs new data-loading path** |
| `dashboard/index.html` | Exists | D3.js force-directed graph — working and verified |
| `dashboard/style.css` | Exists | Premium dark theme |
| `dashboard/app.js` | Exists | Graph interaction, cluster highlight, search, export |
| `synthetic_dataset.py` | Old/ignore | Previous generator with different format — use `generate_dataset.py` instead |
| `dataset_ground_rules.md` | Exists | The spec this document is based on |
| `entity_graph_module_brief.md` | Exists | Original PS brief |
| `ENTITY_GRAPH_WORKING_BRIEF.md` | This file | Master context for Claude sessions |

---

## 9. Remaining Work — Priority Order

### Priority 1 — Dataset Generator Upgrade
**File:** `generate_dataset.py`
- Upgrade from 18 to 60 actors
- Add `n_actors` parameter (default 60)
- Proportion-based category counts (no hardcoding)
- All 8 categories with correct identifier reuse patterns
- All 5 anomaly sub-types with `anomaly_type` in ground truth
- Outputs: `data/investigator_view.json` + `data/ground_truth.json`

### Priority 2 — Rewire Graph Engine to UUID Format
**File:** `graph_engine.py`
- Primary key for Handle nodes = `handle_id` (UUID), NOT `username`
- `_handle_index` maps `handle_id` → `node_id`
- Add secondary `_handle_name_index` mapping `handle` (name) → `handle_id` for display
- `ingest_dataset()` reads from new flat `investigator_view.json` format
- Trust links resolved via UUID

### Priority 3 — Upgrade Identity Resolver
**File:** `identity_resolver.py`
- Null-field safety: skip `pgp_fingerprint` if `None`, skip `wallet_address` if `None`
- Escrow wallet penalty: caller passes in `escrow_wallet_ids` set → if wallet is in it, cap at 0.40
- Tune confidence constants to match §6 bands
- Trust-link noisy-OR combination works as supporting signal for rotated-PGP case

### Priority 4 — Per-Category Evaluation
**File:** `evaluate.py`
- Load categories from `ground_truth.json`
- Compute P/R/F1 for each category separately
- Print anomaly sub-type results as own section
- Report which specific planted patterns were caught vs missed

### Priority 5 — Fix Export UUIDs
**File:** `export.py`
- `handle_ids` field in clusters = list of UUIDs
- `handles` field = list of display names
- Both always present in output

### Priority 6 — Wire Main Pipeline
**File:** `main.py`
- Load `data/investigator_view.json` + `data/ground_truth.json`
- Pass flat personas directly to new graph engine ingestion method

---

## 10. How to Start Each Claude Session

Paste this document, then say:

- **"Priority 1 — upgrade generate_dataset.py to 60 actors"**
- **"Priority 2 — rewire graph_engine.py to UUID-based format"**
- **"Priority 3 — upgrade resolver for anomaly handling"**
- **"Priority 4 — per-category evaluation"**
- **"Run the full pipeline"** → `python main.py`
- **"Launch dashboard"** → `python main.py --serve`

### Quick commands
```bash
python main.py              # full pipeline
python main.py --serve      # pipeline + dashboard at localhost:5000
python generate_dataset.py  # regenerate dataset only
python evaluate.py          # evaluate only
```

---

## 11. Non-Negotiables

1. `investigator_view.json` never contains `actor_id` or category labels
2. `ground_truth.json` is never fed into the graph module
3. Fixed `random.seed(42)` — identical dataset every run
4. No real dark-web data anywhere
5. Every planted pattern independently verifiable from `investigator_view.json` alone
6. Resolver never auto-declares a match — always outputs a confidence score
7. Fusion layer export must use UUIDs, not just handle names

---

## 12. Key Design Decisions

| Decision | Choice | Reason |
|----------|--------|--------|
| Graph library | NetworkX (in-memory) | Zero setup overhead for hackathon |
| Node ID format | UUID for handles, fingerprint for PGP, address for wallet | Stable — names can collide |
| Confidence formula | Noisy-OR | Standard for combining independent binary signals |
| API | Flask REST + Python functions | Dashboard uses REST; fusion layer calls Python directly |
| False-positive guard | Escrow wallet penalty + name-similarity resistance | Keeps resolver honest |
| Dashboard | D3.js force-directed, dark theme | Already built and verified working |
| Dataset format | Flat per-handle records (your generate_dataset.py format) | Closest to real scraped data; graph module does the splitting |
