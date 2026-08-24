# Entity Graph — Synthetic Dataset Ground Rules
## SIH26151 — Module 2 (Entity Relationship Graph)

This document is the single source of truth for how the synthetic dataset is generated. Any regeneration, resizing, or handoff to another teammate should follow these rules exactly, so the dataset stays internally consistent and evaluation numbers stay comparable across runs.

---

## 1. Schema (locked)

**Format:** flat, per-handle record (one row = one scraped marketplace profile). No pre-split identifier arrays — splitting handles/PGP-keys/wallets into separate entities is the graph module's job, not the dataset's.

```json
{
  "handle_id": "<uuid>",
  "handle": "<string>",
  "marketplace": "<string>",
  "pgp_fingerprint": "<40-char hex>",
  "wallet_address": "<btc-like string>"
}
```

- `handle_id` — UUID, stable identity for a single handle-record. This is what the graph, the resolver, and the fusion-layer export all key off of.
- No `actor_id` anywhere in the investigator-facing file. Ground truth lives in a **separate file only**, never fed to the module.

**Trust links:**
```json
{ "from_handle_id": "<uuid>", "to_handle_id": "<uuid>", "type": "vouched_for | transacted_with" }
```
Always UUID-referenced, never by handle name (names can collide/change; UUIDs can't).

---

## 2. Files (locked)

| File | Contains | Fed to graph module? |
|---|---|---|
| `investigator_view.json` | `personas[]` + `trust_links[]` | **Yes** — this is the only input |
| `ground_truth.json` | `actor_to_handles` map + `categories` dict | **No** — evaluation only |

Keep these two files strictly separate. If a third file is ever needed (e.g. a "noisy version with typos" for robustness testing), it gets its own filename — never merge ground truth into the investigator view.

---

## 3. Scale

- **Target: 60 synthetic actors** (up from the 18-actor pilot), producing roughly 90–110 handle-records once rebrands/multi-handles are counted in.
- Bigger dataset exists to (a) make precision/recall numbers statistically meaningful instead of "4 out of 4," and (b) give the dashboard/query demo enough volume to look like a real system, not a toy.
- Script must accept an `n_actors` parameter (or equivalent) so size can be tuned without rewriting logic — don't hardcode category counts, derive them from proportions (see §4).

---

## 4. Category Ground Rules

Every actor belongs to exactly one category. Category **proportions**, not fixed counts, drive generation, so the dataset scales cleanly.

| Category | Target share | Handles per actor | What it tests |
|---|---|---|---|
| **Clean / unique** | ~45% | 1 | Control group — resolver must NOT invent a match |
| **Rebranded — full reuse** | ~12% | 2 | Same PGP **and** same wallet reused under a new handle/marketplace → HIGH confidence expected |
| **Rebranded — PGP-only reuse** | ~6% | 2 | Same PGP, different wallet → tests partial-signal resolution |
| **Rebranded — wallet-only reuse** | ~6% | 2 | Same wallet, different PGP → tests partial-signal resolution |
| **Ambiguous — wallet overlap only** | ~8% | 2 | Shared wallet, unrelated PGP, no trust link → MEDIUM confidence, believable coincidence |
| **Ambiguous — trust-link overlap only** | ~8% | 2 | No shared identifiers at all, only a vouch/transaction pattern → LOW confidence |
| **Anomalies** | ~10% | varies | See §5 — deliberately weird/broken records |
| **Noise / true no-match** | ~5% | 1 each | Same marketplace, zero identifier overlap, zero trust link → must stay unlinked |

Every category must be traceable in `ground_truth.json → categories`, one list per row above, so per-category precision/recall can be computed instead of one blended number.

---

## 5. Anomalies (new — explicitly required)

Real scraped data is messy. The resolver has to be tested against messiness, not just clean planted leaks. Anomaly sub-types to include (spread across the ~10% anomaly share):

1. **Reused PGP key across 3+ unrelated marketplaces with no other overlap** — tests whether the resolver over-trusts a single signal type at scale (a key broker or compromised key scenario) vs. correctly clustering it as one actor.
2. **Wallet address reused for a legitimate reason that isn't the same actor** (e.g. a shared escrow/mixer wallet used by multiple distinct actors) — a deliberate **false-positive trap**. Ground truth marks these as DIFFERENT actors despite the wallet match, so the resolver's blind "shared wallet = match" logic gets tested honestly.
3. **Malformed/partial record** — a handle with a missing wallet or missing PGP field entirely (simulates incomplete scrape). Resolver must not crash and must not falsely link on missing data.
4. **Near-duplicate handle names** (e.g. `ShadowFox34` vs `ShadowFox_34` vs `Shadow-Fox34`) with **no** identifier overlap — tests that the resolver isn't fooled by superficial name similarity alone (a naive string-similarity approach would wrongly flag these).
5. **Stale/rotated PGP key** — one actor with two handle-records where the PGP key differs because it was legitimately rotated, but the wallet stays the same and a trust-link pattern confirms it's one actor — tests combining a weak signal (wallet) with a supporting signal (trust link) to still reach a confident call.

Each anomaly gets a clear ground-truth label (`anomaly_type` field) so it's reportable as its own line item to judges — "here's how the system handles messy/adversarial data," not just clean planted leaks.

---

## 6. Confidence Tier Mapping (for the resolver to target)

| Signal combination | Expected confidence band |
|---|---|
| Shared PGP + shared wallet | High (0.90–0.97) |
| Shared PGP only | Medium-high (0.70–0.85) |
| Shared wallet only | Medium (0.60–0.85) |
| Trust-link pattern only | Low (0.20–0.35) |
| Shared wallet flagged as escrow/mixer trap | Should NOT resolve high — tests resolver's false-positive resistance |
| No shared signal | No edge proposed |

This table is the target behavior spec for `identity_resolver.py` — not something the dataset generator computes itself. The generator only plants the ground truth; the resolver's job is to independently arrive at scores that respect these bands.

---

## 7. Non-negotiables

- **Reproducibility:** fixed random seed, so re-running the generator produces the identical dataset (important for consistent demo + scoring across the team).
- **No real data:** all handles, keys, wallets, marketplace names are fabricated. Nothing is scraped or drawn from real dark-web sources at any point.
- **Investigator view never contains actor_id or category labels.** Only `ground_truth.json` knows the answer key.
- **Every planted pattern must be independently verifiable** by re-deriving it from `investigator_view.json` alone (e.g. you should be able to prove a rebrand by literally comparing two records' PGP/wallet fields) — no hidden logic that only the generator's internal state knows.
- **Category proportions, not fixed counts**, so scaling `n_actors` up/down keeps the dataset shape consistent.

---

## 8. What Changes From the 18-Actor Pilot

- Scale: 18 → 60 actors.
- Rebrand category is split into 3 sub-types (full/PGP-only/wallet-only) instead of one uniform "both match" pattern.
- Ambiguous category gains a second sub-type (trust-link-only, in addition to wallet-only).
- New top-level **anomalies** category (5 sub-types) — did not exist in the pilot.
- Everything else (file split, flat schema, UUID handle_ids, category dict in ground truth) carries over unchanged — it already tested well.
