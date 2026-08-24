You are building **Module 2: Entity Relationship Graph** for a Smart India Hackathon project (SIH26151 — Dark Web Threat Actor De-anonymization). I've attached a file called `ANTIGRAVITY_BUILD_SPEC.md` — that is your complete specification. Read it fully before writing any code.

## What to do

Build this module end-to-end in Python, exactly as specified in the attached file. In summary:

1. **Set up the project structure**: `graph_engine.py`, `traversal.py`, `export.py`, plus a `data/` folder for the input CSVs and a `requirements.txt`.

2. **`graph_engine.py`** — Load the two ANON dataset CSVs (paths given in the spec, §2), group nodes by `handle`, collapse each handle-group into a single canonical entity node (§3–4.1), build a `networkx.MultiDiGraph` with the remaining edge types (`VOUCHED_FOR`, `CO_OCCURRED_IN_THREAD`, `TRANSACTED_WITH`), use `SHARED_PGP_AND_WALLET` edges only as a sanity check on the collapse (not as graph edges). Expose a `get_graph()` function.

3. **`traversal.py`** — Multi-hop path finding (2–3 hops) between canonical entities using `networkx` built-ins, computing `path_confidence` (multiply edge confidences along a path) and `graph_link_strength` (combine path count + strongest path confidence), per §4.2.

4. **`export.py`** — Produce `entity_graph_output.json` in exactly the two-part shape defined in §4.3 (pairwise scoring objects + full node/edge graph export). Preserve `aka_persona_ids` on every entity node — do not drop it, it's the cross-module join key.

5. **Validation** — Implement and run the checklist in §5 (confirm every `SHARED_PGP_AND_WALLET` pair collapsed correctly, spot-check known connections, test a genuine 2-3 hop indirect path, confirm isolated entities return `connected: false`). Print/report the results.

6. Add a short `README.md` for this module summarizing what it does, how to run it (`python export.py` or equivalent entry point), and the output file it produces — written for a teammate (Saraa) picking this up mid-build, per §7 of the spec.

## Non-negotiables (do not deviate from these, even if it seems more "correct" another way)

- Use **only** the `_ANON` CSV files referenced in the spec. Never substitute real dark-web vendor handles or regenerate data from real sources — see §2 and §9 for why.
- `persona_id` is the cross-module join key, not `handle` — preserve it through the collapse as `aka_persona_ids` on every entity node.
- The canonical-collapse-by-handle design (§3) is locked — don't redesign it into something else (e.g. don't switch to a different clustering approach).
- Follow the exact output JSON schema in §4.3 — Fusion and Dashboard teammates are building against this shape already.
- Do not write or include the pitch-narrative language on your own — if you generate any README/demo-script text, use the exact framing given in §8 of the spec (synthetic dataset modeled on real patterns, planted ground truth for validation), not a claim that real-world actors were "resolved" or "identified."

## Libraries

`networkx`, `pandas` (required). `pyvis` optional if you want to add a quick visualization for the dashboard handoff — not required for the core deliverable.

## If you run low on context/budget partway through

Make sure `get_graph()` is implemented and working before anything else — that's the stable interface the rest of the pipeline depends on, and it's what a teammate would continue from if the build is handed off incomplete. Prioritize: loader/collapse → `get_graph()` → traversal → export → validation → README, in that order, so a partial build is still usable.

Work through this now — set up the files, implement each piece per the spec, and run the validation checklist at the end to confirm everything works before finishing.
