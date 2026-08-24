"""
SIH26151 - Entity Relationship Graph Module
Synthetic dataset generator.

Generates threat-actor personas with handles, PGP keys, wallets, marketplaces,
and trust links. Plants ground-truth patterns:
  - Rebranded personas: new handle + new marketplace, but REUSE the same PGP
    key and/or wallet -> this is the leak the graph module must catch.
  - Clean/no-overlap personas: no reused identifiers -> control group, should
    NOT be flagged as linked to anyone.
  - A couple of "ambiguous" personas: partial overlap (e.g. shared wallet but
    different PGP key) -> should come out as MEDIUM confidence, not a clean
    match, feeding differentiator #4 (honest low-confidence output).

Two outputs are written:
  1. investigator_view.json  -> what the graph module actually ingests
     (handles, PGP keys, wallets, marketplaces, trust links). NO actor_id.
  2. ground_truth.json       -> actor_id -> [handle_ids] mapping, used only
     for scoring precision/recall. Not fed into the graph module.
"""

import json
import random
import string
import uuid
from pathlib import Path

random.seed(42)  # reproducible dataset

OUT_DIR = Path(__file__).parent / "data"
OUT_DIR.mkdir(exist_ok=True)

MARKETPLACES = [
    "DarkBazaar", "ShadowMart", "CipherExchange", "NightMarket",
    "VoidTrade", "OnionDepot", "GhostCartel", "BlackLotus",
]

HANDLE_ADJ = ["Silent", "Crimson", "Ghost", "Iron", "Phantom", "Rogue",
              "Shadow", "Viper", "Cobalt", "Grim", "Void", "Ashen"]
HANDLE_NOUN = ["Wolf", "Trader", "Byte", "Reaper", "Fox", "Hunter",
               "Serpent", "Broker", "Raven", "Ronin", "Cipher", "Wraith"]


def fake_pgp_fingerprint():
    return "".join(random.choices(string.hexdigits.upper()[:16], k=40))


def fake_wallet():
    # BTC-like address shape, synthetic only
    return "1" + "".join(random.choices(string.ascii_letters + string.digits, k=33))


def fake_handle(used):
    while True:
        h = f"{random.choice(HANDLE_ADJ)}{random.choice(HANDLE_NOUN)}{random.randint(1,999)}"
        if h not in used:
            used.add(h)
            return h


def make_persona(actor_id, handle, marketplace, pgp_key, wallet):
    return {
        "handle_id": str(uuid.uuid4()),
        "handle": handle,
        "marketplace": marketplace,
        "pgp_fingerprint": pgp_key,
        "wallet_address": wallet,
        "_actor_id": actor_id,  # stripped before writing investigator_view.json
    }


def main():
    used_handles = set()
    personas = []
    ground_truth = {}  # actor_id -> list of handle_ids

    n_actors = 18
    actor_ids = [f"ACTOR-{i+1:02d}" for i in range(n_actors)]

    # --- Category A: clean, single-handle actors (no leak, control group) ---
    clean_actors = actor_ids[0:10]
    for aid in clean_actors:
        h = fake_handle(used_handles)
        mkt = random.choice(MARKETPLACES)
        p = make_persona(aid, h, mkt, fake_pgp_fingerprint(), fake_wallet())
        personas.append(p)
        ground_truth[aid] = [p["handle_id"]]

    # --- Category B: rebranded actors (SAME pgp key + wallet reused
    #     under a brand new handle on a different marketplace) ---
    rebrand_actors = actor_ids[10:14]  # 4 personas
    for aid in rebrand_actors:
        pgp = fake_pgp_fingerprint()
        wallet = fake_wallet()
        mkt1, mkt2 = random.sample(MARKETPLACES, 2)
        h1 = fake_handle(used_handles)
        h2 = fake_handle(used_handles)
        p1 = make_persona(aid, h1, mkt1, pgp, wallet)
        p2 = make_persona(aid, h2, mkt2, pgp, wallet)  # full reuse -> should be HIGH confidence
        personas.extend([p1, p2])
        ground_truth[aid] = [p1["handle_id"], p2["handle_id"]]

    # --- Category C: ambiguous/partial-overlap actors (shares WALLET only,
    #     different PGP key -> should land as MEDIUM confidence, not a clean
    #     match; feeds the "honest low-confidence output" differentiator) ---
    ambiguous_actors = actor_ids[14:16]  # 2 personas
    for aid in ambiguous_actors:
        wallet = fake_wallet()
        mkt1, mkt2 = random.sample(MARKETPLACES, 2)
        h1 = fake_handle(used_handles)
        h2 = fake_handle(used_handles)
        p1 = make_persona(aid, h1, mkt1, fake_pgp_fingerprint(), wallet)
        p2 = make_persona(aid, h2, mkt2, fake_pgp_fingerprint(), wallet)  # only wallet shared
        personas.extend([p1, p2])
        ground_truth[aid] = [p1["handle_id"], p2["handle_id"]]

    # --- Category D: true "no match" -- two unrelated actors who just
    #     happen to trade on the same marketplace, no identifier overlap at
    #     all. Pure noise / negative control. ---
    noise_actors = actor_ids[16:18]
    shared_mkt = random.choice(MARKETPLACES)
    for aid in noise_actors:
        h = fake_handle(used_handles)
        p = make_persona(aid, h, shared_mkt, fake_pgp_fingerprint(), fake_wallet())
        personas.append(p)
        ground_truth[aid] = [p["handle_id"]]

    # --- Trust links: vouches between DIFFERENT actors (not same-actor
    #     signal) -- gives the graph some organic structure to traverse ---
    trust_links = []
    all_handle_ids_by_actor = {aid: [h["handle_id"] for h in personas if h["_actor_id"] == aid]
                                for aid in actor_ids}
    n_links = 14
    for _ in range(n_links):
        a1, a2 = random.sample(actor_ids, 2)
        h1 = random.choice(all_handle_ids_by_actor[a1])
        h2 = random.choice(all_handle_ids_by_actor[a2])
        trust_links.append({
            "from_handle_id": h1,
            "to_handle_id": h2,
            "type": random.choice(["vouched_for", "transacted_with"]),
        })

    # --- Write investigator-facing view (NO actor_id -- this is what the
    #     graph module actually ingests) ---
    investigator_view = {
        "personas": [
            {k: v for k, v in p.items() if k != "_actor_id"} for p in personas
        ],
        "trust_links": trust_links,
    }

    with open(OUT_DIR / "investigator_view.json", "w") as f:
        json.dump(investigator_view, f, indent=2)

    with open(OUT_DIR / "ground_truth.json", "w") as f:
        json.dump({
            "actor_to_handles": ground_truth,
            "categories": {
                "clean_single_handle": clean_actors,
                "rebranded_full_reuse": rebrand_actors,
                "ambiguous_partial_overlap": ambiguous_actors,
                "no_match_noise": noise_actors,
            },
        }, f, indent=2)

    print(f"Generated {len(personas)} handle-records across {n_actors} synthetic actors.")
    print(f"  Clean (no leak):            {len(clean_actors)}")
    print(f"  Rebranded (full reuse):     {len(rebrand_actors)} -> {len(rebrand_actors)*2} handle records")
    print(f"  Ambiguous (partial overlap):{len(ambiguous_actors)} -> {len(ambiguous_actors)*2} handle records")
    print(f"  Noise (no overlap):         {len(noise_actors)}")
    print(f"  Trust links:                {len(trust_links)}")
    print(f"\nWrote:\n  {OUT_DIR/'investigator_view.json'}\n  {OUT_DIR/'ground_truth.json'}")


if __name__ == "__main__":
    main()
