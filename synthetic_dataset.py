"""
synthetic_dataset.py — Synthetic Dataset Generator
====================================================
Generates 15–20 personas with planted ground truth for the
Entity Relationship Graph Module (SIH26151).

Includes:
  - 12–14 unique personas (distinct identifiers)
  - 3–4 rebranded personas (shared PGP/wallet across handles)
  - 1–2 ambiguous personas (weak/coincidental overlap)
  - Trust links (vouches, reviews, referrals)

Output: data/synthetic_personas.json
"""

import json
import hashlib
import random
import os
import string
from datetime import datetime, timedelta


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _random_hex(n: int) -> str:
    """Return a random hex string of length n."""
    return "".join(random.choices("0123456789abcdef", k=n))


def _pgp_fingerprint() -> str:
    """Generate a realistic-looking PGP fingerprint (40 hex chars)."""
    return _random_hex(40).upper()


def _btc_address() -> str:
    """Generate a plausible BTC address (bech32-style)."""
    return "bc1q" + _random_hex(38)


def _xmr_address() -> str:
    """Generate a plausible Monero address."""
    return "4" + _random_hex(94)


def _handle(base: str, suffix: bool = True) -> str:
    """Generate a darknet-style handle."""
    if suffix:
        return f"{base}{random.randint(10, 999)}"
    return base


# ---------------------------------------------------------------------------
# Marketplaces
# ---------------------------------------------------------------------------

MARKETPLACES = [
    {"name": "Hydra Reborn", "type": "market"},
    {"name": "Shadow Bazaar", "type": "market"},
    {"name": "DarkTrade Forum", "type": "forum"},
    {"name": "Onion Exchange", "type": "market"},
    {"name": "CryptoAlley", "type": "forum"},
]


# ---------------------------------------------------------------------------
# Persona Definitions
# ---------------------------------------------------------------------------

def generate_dataset(seed: int = 42) -> dict:
    """
    Generate a complete synthetic dataset.

    Returns a dict with:
      - personas: list of ground-truth persona records
      - handles: list of handle records (investigator-visible)
      - pgp_keys: list of PGP key records
      - wallets: list of wallet records
      - trust_links: list of trust-link edges
      - ground_truth_clusters: the answer key for evaluation
    """
    random.seed(seed)

    personas = []
    handles = []
    pgp_keys = []
    wallets = []
    trust_links = []
    ground_truth_clusters = {}

    # ------------------------------------------------------------------
    # 1) Unique personas (12 distinct actors, no identifier reuse)
    # ------------------------------------------------------------------
    unique_names = [
        "viper", "ghostcrypt", "nullbyte", "darkphoenix",
        "silkworm", "zeroday", "blackmamba", "cryptking",
        "neonshade", "phantomx", "ironcloak", "bytebandit",
    ]

    for i, name in enumerate(unique_names):
        actor_id = f"ACTOR_{i+1:03d}"
        pgp = _pgp_fingerprint()
        wallet = _btc_address() if random.random() > 0.3 else _xmr_address()
        marketplace = random.choice(MARKETPLACES)
        handle_name = _handle(name)

        personas.append({
            "actor_id": actor_id,
            "type": "unique",
            "true_handles": [handle_name],
        })

        handles.append({
            "handle_id": f"H_{handle_name}",
            "username": handle_name,
            "marketplace": marketplace["name"],
            "marketplace_type": marketplace["type"],
            "registered_date": (
                datetime(2024, 1, 1) + timedelta(days=random.randint(0, 500))
            ).isoformat(),
            "reputation_score": round(random.uniform(3.0, 5.0), 2),
            "total_listings": random.randint(5, 200),
        })

        pgp_keys.append({
            "fingerprint": pgp,
            "associated_handles": [handle_name],
            "created_date": (
                datetime(2023, 6, 1) + timedelta(days=random.randint(0, 300))
            ).isoformat(),
            "key_type": random.choice(["RSA-4096", "Ed25519"]),
        })

        wallets.append({
            "address": wallet,
            "currency": "BTC" if wallet.startswith("bc1") else "XMR",
            "associated_handles": [handle_name],
            "first_seen": (
                datetime(2023, 9, 1) + timedelta(days=random.randint(0, 400))
            ).isoformat(),
        })

        ground_truth_clusters[actor_id] = [handle_name]

    # ------------------------------------------------------------------
    # 2) Rebranded personas (4 actors with identifier reuse)
    #    Each has 2 handles across different marketplaces but shares
    #    a PGP key and/or wallet — the "leak" the graph must catch.
    # ------------------------------------------------------------------
    rebrand_configs = [
        {
            "actor_id": "ACTOR_R01",
            "names": ["spectre", "wraithseller"],
            "share_pgp": True,
            "share_wallet": True,
            "type": "rebrand_both",
        },
        {
            "actor_id": "ACTOR_R02",
            "names": ["acidrain", "voltdrop"],
            "share_pgp": True,
            "share_wallet": False,
            "type": "rebrand_pgp_only",
        },
        {
            "actor_id": "ACTOR_R03",
            "names": ["deepstate", "shadowgov"],
            "share_pgp": False,
            "share_wallet": True,
            "type": "rebrand_wallet_only",
        },
        {
            "actor_id": "ACTOR_R04",
            "names": ["venomstrike", "cobrafang"],
            "share_pgp": True,
            "share_wallet": True,
            "type": "rebrand_both",
        },
    ]

    for cfg in rebrand_configs:
        actor_id = cfg["actor_id"]
        shared_pgp = _pgp_fingerprint()
        unique_pgp_alt = _pgp_fingerprint()
        shared_wallet = _btc_address()
        unique_wallet_alt = _btc_address()

        # Ensure two different marketplaces
        mkts = random.sample(MARKETPLACES, 2)
        handle_records = []

        for j, name in enumerate(cfg["names"]):
            handle_name = _handle(name)
            handle_records.append(handle_name)

            handles.append({
                "handle_id": f"H_{handle_name}",
                "username": handle_name,
                "marketplace": mkts[j]["name"],
                "marketplace_type": mkts[j]["type"],
                "registered_date": (
                    datetime(2024, 1, 1) + timedelta(days=random.randint(0, 500))
                ).isoformat(),
                "reputation_score": round(random.uniform(3.5, 5.0), 2),
                "total_listings": random.randint(10, 300),
            })

            # PGP assignment
            if cfg["share_pgp"]:
                pgp_keys.append({
                    "fingerprint": shared_pgp,
                    "associated_handles": [handle_name],
                    "created_date": (
                        datetime(2023, 6, 1) + timedelta(days=random.randint(0, 200))
                    ).isoformat(),
                    "key_type": "RSA-4096",
                })
            else:
                pgp_keys.append({
                    "fingerprint": unique_pgp_alt if j == 1 else _pgp_fingerprint(),
                    "associated_handles": [handle_name],
                    "created_date": (
                        datetime(2023, 6, 1) + timedelta(days=random.randint(0, 200))
                    ).isoformat(),
                    "key_type": "RSA-4096",
                })

            # Wallet assignment
            if cfg["share_wallet"]:
                wallets.append({
                    "address": shared_wallet,
                    "currency": "BTC",
                    "associated_handles": [handle_name],
                    "first_seen": (
                        datetime(2023, 9, 1) + timedelta(days=random.randint(0, 300))
                    ).isoformat(),
                })
            else:
                wallets.append({
                    "address": unique_wallet_alt if j == 1 else _btc_address(),
                    "currency": "BTC",
                    "associated_handles": [handle_name],
                    "first_seen": (
                        datetime(2023, 9, 1) + timedelta(days=random.randint(0, 300))
                    ).isoformat(),
                })

        personas.append({
            "actor_id": actor_id,
            "type": cfg["type"],
            "true_handles": handle_records,
        })
        ground_truth_clusters[actor_id] = handle_records

    # ------------------------------------------------------------------
    # 3) Ambiguous personas (2 actors with weak/coincidental overlap)
    #    These should NOT be auto-matched — they test false-positive
    #    resilience. They only share trust links, not hard identifiers.
    # ------------------------------------------------------------------
    ambiguous_configs = [
        {
            "actor_id": "ACTOR_A01",
            "names": ["mirrorman", "glasswalker"],
            "type": "ambiguous_trust_only",
        },
        {
            "actor_id": "ACTOR_A02",
            "names": ["dustdevil", "sandstorm"],
            "type": "ambiguous_trust_only",
        },
    ]

    for cfg in ambiguous_configs:
        actor_id = cfg["actor_id"]
        mkts = random.sample(MARKETPLACES, 2)
        handle_records = []

        for j, name in enumerate(cfg["names"]):
            handle_name = _handle(name)
            handle_records.append(handle_name)

            handles.append({
                "handle_id": f"H_{handle_name}",
                "username": handle_name,
                "marketplace": mkts[j]["name"],
                "marketplace_type": mkts[j]["type"],
                "registered_date": (
                    datetime(2024, 3, 1) + timedelta(days=random.randint(0, 400))
                ).isoformat(),
                "reputation_score": round(random.uniform(2.5, 4.5), 2),
                "total_listings": random.randint(2, 50),
            })

            # Each has its OWN PGP and wallet — no sharing
            pgp_keys.append({
                "fingerprint": _pgp_fingerprint(),
                "associated_handles": [handle_name],
                "created_date": (
                    datetime(2023, 8, 1) + timedelta(days=random.randint(0, 200))
                ).isoformat(),
                "key_type": random.choice(["RSA-4096", "Ed25519"]),
            })
            wallets.append({
                "address": _btc_address(),
                "currency": "BTC",
                "associated_handles": [handle_name],
                "first_seen": (
                    datetime(2024, 1, 1) + timedelta(days=random.randint(0, 300))
                ).isoformat(),
            })

        personas.append({
            "actor_id": actor_id,
            "type": cfg["type"],
            "true_handles": handle_records,
        })
        # Ground truth: these are DIFFERENT actors — each handle is its own cluster
        for h in handle_records:
            ground_truth_clusters[f"{actor_id}_{h}"] = [h]

    # ------------------------------------------------------------------
    # 4) Trust links — vouches / referrals / transactions
    # ------------------------------------------------------------------
    all_handles = [h["username"] for h in handles]

    # Create realistic trust networks
    trust_pairs = [
        # Rebranded personas vouch for each other (suspicious pattern)
        ("spectre", "acidrain"),
        ("wraithseller", "voltdrop"),
        # Legitimate vouches between unique actors
        ("viper", "ghostcrypt"),
        ("nullbyte", "darkphoenix"),
        ("silkworm", "zeroday"),
        ("blackmamba", "cryptking"),
        ("neonshade", "phantomx"),
        ("ironcloak", "bytebandit"),
        # Ambiguous actors share some vouchers (weak signal)
        ("mirrorman", "glasswalker"),
        ("dustdevil", "sandstorm"),
        # Cross-category vouches
        ("viper", "spectre"),
        ("ghostcrypt", "deepstate"),
        ("nullbyte", "venomstrike"),
    ]

    for src_base, tgt_base in trust_pairs:
        # Find actual handle names (with random suffix)
        src_matches = [h for h in all_handles if h.startswith(src_base)]
        tgt_matches = [h for h in all_handles if h.startswith(tgt_base)]

        if src_matches and tgt_matches:
            src = src_matches[0]
            tgt = tgt_matches[0]
            link_type = random.choice(["vouch", "review", "referral"])
            trust_links.append({
                "source_handle": src,
                "target_handle": tgt,
                "link_type": link_type,
                "timestamp": (
                    datetime(2024, 6, 1) + timedelta(days=random.randint(0, 200))
                ).isoformat(),
                "context": f"{link_type.capitalize()} from {src} to {tgt}",
            })

    # Add some transaction links
    tx_pairs = random.sample(
        [(a, b) for a in all_handles for b in all_handles if a != b],
        min(15, len(all_handles) * 2),
    )
    for src, tgt in tx_pairs:
        trust_links.append({
            "source_handle": src,
            "target_handle": tgt,
            "link_type": "transaction",
            "timestamp": (
                datetime(2024, 1, 1) + timedelta(days=random.randint(0, 500))
            ).isoformat(),
            "context": f"Transaction between {src} and {tgt}",
        })

    # ------------------------------------------------------------------
    # Assemble final dataset
    # ------------------------------------------------------------------
    dataset = {
        "metadata": {
            "generated_at": datetime.now().isoformat(),
            "generator": "SIH26151 Entity Graph Module — Synthetic Dataset v1.0",
            "total_personas": len(personas),
            "total_handles": len(handles),
            "total_pgp_keys": len(set(p["fingerprint"] for p in pgp_keys)),
            "total_wallets": len(set(w["address"] for w in wallets)),
            "total_trust_links": len(trust_links),
            "planted_rebrands": len(rebrand_configs),
            "ambiguous_personas": len(ambiguous_configs),
            "note": "SYNTHETIC DATA ONLY — no real dark web data. "
                    "Created for SIH 2026 demonstration purposes.",
        },
        "personas": personas,
        "handles": handles,
        "pgp_keys": pgp_keys,
        "wallets": wallets,
        "trust_links": trust_links,
        "ground_truth_clusters": ground_truth_clusters,
    }

    return dataset


def save_dataset(dataset: dict, output_dir: str = "data") -> str:
    """Save dataset to JSON file."""
    os.makedirs(output_dir, exist_ok=True)
    path = os.path.join(output_dir, "synthetic_personas.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(dataset, f, indent=2, ensure_ascii=False)
    print(f"[OK] Synthetic dataset saved to {path}")
    print(f"    - {dataset['metadata']['total_personas']} personas")
    print(f"    - {dataset['metadata']['total_handles']} handles")
    print(f"    - {dataset['metadata']['total_pgp_keys']} unique PGP keys")
    print(f"    - {dataset['metadata']['total_wallets']} unique wallets")
    print(f"    - {dataset['metadata']['total_trust_links']} trust links")
    print(f"    - {dataset['metadata']['planted_rebrands']} planted rebrands")
    return path


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    ds = generate_dataset()
    save_dataset(ds)
