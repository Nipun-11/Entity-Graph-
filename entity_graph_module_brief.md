# SIH26151 — Entity Relationship Graph Module
## Working Brief (Member 2 — Your Module)

**Team project:** Dark Web Threat Actor De-anonymization
**Organization:** NTRO | **Category:** Software | **Theme:** Blockchain & Cybersecurity
**Your scope:** Module 2 of 3 signal modules (Infra+Timing / **Entity Graph** / Stylometry), feeding into the Fusion layer built by Member 4.

---

## 1. Background (so any AI/collaborator has full context)

The overall system de-anonymizes dark web threat actors by combining three independent signals into one confidence-scored attribution:

1. **Infra + timing matcher** (Member 1) — cert/banner/descriptor leaks + response-timing fingerprinting.
2. **Entity relationship graph** (you) — maps actors across marketplaces via handles, PGP keys, wallets, and trust links.
3. **Operational-style stylometry** (Member 3) — writing style + behavioral habits (time zone, posting order, key rotation) that survive a deliberate rebrand.

All three feed a **fusion layer** (Member 4) that produces an adaptive confidence score, surfaced through a **dashboard** (Member 5) with CSV/JSON/report export. Everything runs on a **synthetic dataset with planted ground truth** (15–20 personas, some rebranded, some ambiguous) — there is no live/real dark web scraping involved anywhere in this build; this is a detection/analysis method demonstrated on synthetic data, which is stated proactively to judges.

Your graph module's output isn't judged in isolation — it's judged on how well it hands the fusion layer a clean, queryable structure of *who is linked to whom, and how confidently*.

---

## 2. What Your Module Must Do

From the official PS: *"mapping threat actors across multiple marketplaces into a single relationship graph of handles, PGP keys, wallets and trust links."*

Concretely, your module needs to:

1. **Ingest** per-persona identifiers from the synthetic dataset: marketplace handle(s), PGP key(s), wallet address(es), and any stated trust links (vouches, reviews, referrals between actors).
2. **Build a graph** where nodes = entities (actors, handles, PGP keys, wallets) and edges = relationships (same-actor-as, transacted-with, vouched-for, co-posted-with).
3. **Resolve identity clusters** — when two different handles share a PGP key or wallet, that's a strong same-actor signal; your module should surface these as candidate merges, each with a confidence weight (not silent auto-merging).
4. **Expose a query interface** (even a simple one) that the fusion layer and dashboard can call: "given handle X, return all linked entities and the graph-derived confidence that they're the same actor."
5. **Output a per-edge/per-cluster confidence score** — this is what Member 4's fusion layer will combine with the timing signal and stylometry signal.

---

## 3. Suggested Graph Schema

**Node types:**
- `Actor` (synthetic ground-truth ID — hidden from the "investigator" view, used only for scoring accuracy)
- `Handle` (marketplace username)
- `PGPKey` (fingerprint)
- `Wallet` (address)
- `Marketplace` (the forum/market a handle appears on)

**Edge types:**
- `Handle --USES--> PGPKey`
- `Handle --USES--> Wallet`
- `Handle --POSTS_ON--> Marketplace`
- `Handle --VOUCHED_BY--> Handle`
- `Handle --TRANSACTED_WITH--> Handle`
- `Handle --SAME_ACTOR_AS--> Handle` *(this is the inferred edge you're generating, with a confidence score, not ground truth)*

**Suggested storage:** a lightweight graph DB (Neo4j) or, if you want zero setup overhead for a 36-hour hackathon, a property graph in-memory using `networkx` (Python) with export to JSON for the dashboard team. Given time pressure, **networkx + JSON export is the safer default** — you avoid a DB dependency across 6 laptops.

---

## 4. Your Slice of the Synthetic Dataset

Per the team's dataset design, **each module builds the synthetic data relevant to its own signal** — you don't wait on Member 6 for this part. For your module specifically, when the 15–20 personas are designed (Hr 0–4), you need each persona to carry:

- 1+ marketplace handles (2+ for personas that are "rebranded")
- 1 PGP key (reused across handles for rebranded personas — this is the leak your graph should catch)
- 1 wallet address (also reused for rebranded personas — second leak path)
- A few trust-link edges (some real personas vouching for each other, to give your graph non-trivial structure to traverse)

Coordinate with whoever is designing the 3–4 rebranded personas and the 1–2 "no match" ambiguous personas (per the finalized plan) — you need those wallet/PGP-key reuse patterns planted correctly, since **your module is the one that's supposed to catch the shared-PGP-key / shared-wallet link even when the handle and marketplace look unrelated.**

---

## 5. Your Hours in the 36-Hour Plan

| Hours | Task |
|---|---|
| 0–2 | Confirm your node/edge schema against what Member 1 (infra) and Member 4 (fusion) expect as input/output format |
| 2–4 | Help seed the identifier-reuse patterns (PGP key / wallet overlaps) into the synthetic persona set |
| 4–6 | Finalize your graph schema; set up repo/environment (networkx or Neo4j) |
| 6–8 | Confirm module ownership, environment working end-to-end on a toy example |
| **8–14** | **Core build: ingestion → graph construction → identity-cluster resolution → confidence-scored `SAME_ACTOR_AS` edges → JSON export** |
| 18–20 | Mid-point sync: confirm your JSON output is consumable by Member 4's fusion layer |
| 28–30 | Full pipeline run against synthetic dataset — confirm your module correctly flags the planted rebrand/reuse cases |

---

## 6. Definition of Done (what "finished" looks like for your module)

- [ ] Takes persona/identifier records as input (handles, PGP keys, wallets, trust links)
- [ ] Builds a graph with the schema above
- [ ] Detects shared PGP key / shared wallet across different handles and proposes a `SAME_ACTOR_AS` edge with a confidence score
- [ ] Exposes a simple query function/endpoint: input a handle → output all linked entities + confidence
- [ ] Exports graph + candidate matches as JSON in a format Member 4 can consume
- [ ] Correctly identifies the 3–4 planted rebranded personas via shared identifiers on your synthetic test run
- [ ] Does NOT auto-declare a match — always outputs a confidence score, leaving the final call to the fusion layer

---

## 7. Open Questions to Settle With the Team Early

1. Exact JSON schema Member 4's fusion layer expects (agree on this by Hr 6, not Hr 18).
2. Whether "trust link" edges (vouches) should also contribute to your confidence score, or stay as separate graph structure for the dashboard's relationship view only.
3. Confidence formula for `SAME_ACTOR_AS` — suggest starting simple: shared PGP key = high confidence (e.g. 0.9), shared wallet = high confidence (0.85), shared trust-link pattern alone = low confidence (0.3), and combine multiplicatively/additively — refine only if time allows.
