"""
generate_anon_dataset.py — ANON Dataset Generator for Module 2
================================================================
Reads real_darknet_listings.csv (Gwern archive, 180K listings) and produces
two anonymized CSV files for the Entity Relationship Graph module:

  data/module2_entity_graph_nodes_ANON.csv  (~1,833 rows)
  data/module2_entity_graph_edges_ANON.csv  (~4,216 rows)

Handle names are anonymized to fabricated placeholder names (VoidFox414 style).
Marketplace names are kept real. PGP fingerprints and wallet addresses are
generated (same key/wallet shared across all marketplace appearances of the
same handle — this is the identity leak the graph module must catch).

Usage:
  python generate_anon_dataset.py                     # default 500 handles
  python generate_anon_dataset.py --n_handles 300     # smaller dataset

Seed is fixed (42) for reproducibility.
"""

import argparse
import csv
import hashlib
import json
import os
import random
import string
import uuid
from collections import defaultdict
from pathlib import Path

import pandas as pd

# ---------------------------------------------------------------------------
# Reproducibility
# ---------------------------------------------------------------------------
SEED = 42
random.seed(SEED)

# ---------------------------------------------------------------------------
# Output paths
# ---------------------------------------------------------------------------
OUT_DIR = Path(__file__).parent / "data"
OUT_DIR.mkdir(exist_ok=True)

NODES_PATH = OUT_DIR / "module2_entity_graph_nodes_ANON.csv"
EDGES_PATH = OUT_DIR / "module2_entity_graph_edges_ANON.csv"
CANONICAL_HANDLES_PATH = Path(__file__).parent / "handle_mapping_CANONICAL.csv"

# ---------------------------------------------------------------------------
# Handle anonymization vocabulary
# ---------------------------------------------------------------------------
ADJECTIVES = [
    "Void", "Crimson", "Ghost", "Iron", "Phantom", "Rogue", "Shadow", "Viper",
    "Cobalt", "Grim", "Ashen", "Onyx", "Scarlet", "Frost", "Dark", "Silent",
    "Neon", "Obsidian", "Ember", "Storm", "Azure", "Cyber", "Lunar", "Toxic",
    "Chaos", "Night", "Jade", "Blaze", "Zero", "Pyro", "Hex", "Noir",
]

NOUNS = [
    "Fox", "Wolf", "Trader", "Byte", "Reaper", "Hunter", "Serpent", "Broker",
    "Raven", "Ronin", "Cipher", "Wraith", "Hawk", "Blade", "Lotus", "Phoenix",
    "Tiger", "Dragon", "Venom", "Specter", "Crypt", "Orbit", "Nexus", "Pulse",
    "Flux", "Shade", "Fang", "Helix", "Core", "Arc", "Echo", "Drift",
]

# Additional synthetic marketplaces to reach ~23 total
# (real ones from the CSV: agora, silkroad2, evolution, nucleus, abraxas,
#  1776, outlaw_market, themarketplace)
SYNTHETIC_MARKETPLACES = [
    "dream_market", "hansa", "alphabay", "berlusconi", "wall_street",
    "empire", "hydra", "vice_city", "torrez", "dark0de",
    "cannazon", "versus", "world_market", "darkfox", "cannahome",
]


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def anonymize_handle(real_name: str, index: int) -> str:
    """Generate a deterministic anonymized handle from a real seller name."""
    h = hashlib.sha256(f"{real_name}_{SEED}".encode()).hexdigest()
    adj_idx = int(h[:4], 16) % len(ADJECTIVES)
    noun_idx = int(h[4:8], 16) % len(NOUNS)
    num = int(h[8:11], 16) % 1000
    return f"{ADJECTIVES[adj_idx]}{NOUNS[noun_idx]}{num}"


def fake_pgp_fingerprint(seller: str) -> str:
    """Generate a deterministic 40-char hex PGP fingerprint for a seller."""
    h = hashlib.sha256(f"pgp_{seller}_{SEED}".encode()).hexdigest()
    return h[:40].upper()


def fake_wallet_address(seller: str) -> str:
    """Generate a deterministic BTC-like wallet address for a seller."""
    h = hashlib.sha256(f"wallet_{seller}_{SEED}".encode()).hexdigest()
    # P2PKH format: starts with 1, 33 chars
    chars = string.ascii_letters + string.digits
    addr = "1"
    for i in range(0, 64, 2):
        idx = int(h[i:i+2], 16) % len(chars)
        addr += chars[idx]
        if len(addr) >= 34:
            break
    return addr[:34]


def generate_persona_id(seller: str = None, mkt: str = None) -> str:
    """Generate a deterministic persona_id if not present in master_personas.json."""
    if seller is not None and mkt is not None:
        h = hashlib.sha256(f"persona_{seller}_{mkt}_{SEED}".encode()).hexdigest()
        return f"P-{h[:8]}"
    return f"P-{uuid.uuid4().hex[:8]}"


def load_master_personas(path: str = None) -> dict:
    """
    Load master_personas.json mapping (seller/handle, marketplace) -> persona_id.
    Supports list of persona dicts or dict mapping.
    """
    candidates = []
    if path:
        candidates.append(Path(path))
    candidates.extend([
        OUT_DIR / "master_personas.json",
        Path(__file__).parent / "master_personas.json",
        Path("data/master_personas.json"),
        Path("master_personas.json")
    ])

    for p in candidates:
        if p and p.exists():
            print(f"[*] Found master_personas.json at: {p.resolve()}")
            try:
                with open(p, "r", encoding="utf-8") as f:
                    data = json.load(f)

                persona_map = {}
                if isinstance(data, list):
                    for item in data:
                        if isinstance(item, dict):
                            pid = item.get("persona_id")
                            h = item.get("handle") or item.get("seller") or item.get("real_handle")
                            m = item.get("marketplace") or item.get("source") or item.get("market")
                            if pid and h and m:
                                persona_map[(str(h), str(m))] = str(pid)
                                persona_map[(str(h).lower(), str(m).lower())] = str(pid)
                elif isinstance(data, dict):
                    for k, v in data.items():
                        if isinstance(v, dict):
                            pid = v.get("persona_id", k)
                            h = v.get("handle") or v.get("seller")
                            m = v.get("marketplace") or v.get("source")
                            if pid and h and m:
                                persona_map[(str(h), str(m))] = str(pid)
                                persona_map[(str(h).lower(), str(m).lower())] = str(pid)
                print(f"    Loaded {len(persona_map)} (handle, market) -> persona_id mappings from master source")
                return persona_map
            except Exception as e:
                print(f"    [!] Warning: Failed reading master_personas.json: {e}")
    return {}


def load_and_sync_canonical_handle_mapping(
    selected_sellers: list,
    canonical_path: Path = None,
) -> dict:
    """
    Load handle_mapping_CANONICAL.csv to ensure handles are 100% frozen.
    
    Reuses existing fake_handle values for each real_handle. If a real_handle
    is missing from the file, generates a new fake_handle in the standard style
    and appends it to handle_mapping_CANONICAL.csv without overwriting existing entries.
    """
    target_file = Path(canonical_path) if canonical_path else CANONICAL_HANDLES_PATH
    if not target_file.exists():
        alt = OUT_DIR / "handle_mapping_CANONICAL.csv"
        if alt.exists():
            target_file = alt

    handle_map = {}
    file_exists = target_file.exists()

    if file_exists:
        try:
            df_map = pd.read_csv(target_file)
            if "real_handle" in df_map.columns and "fake_handle" in df_map.columns:
                for _, row in df_map.iterrows():
                    r = str(row["real_handle"]).strip()
                    f = str(row["fake_handle"]).strip()
                    if r and f and r != "nan" and f != "nan":
                        handle_map[r] = f
            print(f"[*] Loaded {len(handle_map)} canonical handles from {target_file.resolve()}")
        except Exception as e:
            print(f"    [!] Warning: Error reading {target_file}: {e}")

    used_handles = set(handle_map.values())
    new_entries = []

    for i, seller in enumerate(sorted(selected_sellers)):
        if seller in handle_map:
            continue

        # Generate deterministic fallback fake handle
        anon = anonymize_handle(seller, i)
        while anon in used_handles:
            anon = anon + str(random.randint(0, 9))
        used_handles.add(anon)
        handle_map[seller] = anon
        new_entries.append({"real_handle": seller, "fake_handle": anon})

    if new_entries:
        print(f"[*] Appending {len(new_entries)} new handle mapping(s) to {target_file.resolve()}...")
        write_header = (not file_exists) or (target_file.stat().st_size == 0)
        with open(target_file, "a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["real_handle", "fake_handle"])
            if write_header:
                writer.writeheader()
            writer.writerows(new_entries)

    return handle_map


# ---------------------------------------------------------------------------
# Main generation logic
# ---------------------------------------------------------------------------

def load_raw_data(csv_path: str) -> pd.DataFrame:
    """Load the Gwern darknet listings CSV."""
    print(f"[*] Loading {csv_path}...")
    df = pd.read_csv(csv_path, low_memory=False)
    print(f"    {len(df):,} listings, {df['seller'].nunique()} sellers, "
          f"{df['source'].nunique()} marketplaces")
    return df


def select_sellers(df: pd.DataFrame, n_handles: int = 500) -> dict:
    """
    Select sellers to include, prioritizing multi-marketplace sellers.

    Returns: dict of {real_seller_name: [list of real marketplace names]}
    """
    print(f"\n[*] Selecting {n_handles} sellers...")

    seller_markets = df.groupby("seller")["source"].apply(
        lambda x: sorted(x.unique())
    ).to_dict()

    seller_market_count = {s: len(m) for s, m in seller_markets.items()}

    # Priority 1: sellers on 3+ markets (highest cross-market signal)
    tier1 = {s: m for s, m in seller_markets.items() if len(m) >= 3}
    # Priority 2: sellers on 2 markets
    tier2 = {s: m for s, m in seller_markets.items() if len(m) == 2}
    # Priority 3: single-market sellers (fill remaining slots)
    tier3 = {s: m for s, m in seller_markets.items() if len(m) == 1}

    selected = {}

    # Take all tier1
    for s, m in sorted(tier1.items(), key=lambda x: -len(x[1])):
        if len(selected) >= n_handles:
            break
        selected[s] = m

    # Take tier2 until we have enough, or all of them
    tier2_list = sorted(tier2.items(), key=lambda x: x[0])
    random.shuffle(tier2_list)
    for s, m in tier2_list:
        if len(selected) >= n_handles:
            break
        selected[s] = m

    # Fill with tier3 if still short
    tier3_list = sorted(tier3.items(), key=lambda x: x[0])
    random.shuffle(tier3_list)
    for s, m in tier3_list:
        if len(selected) >= n_handles:
            break
        selected[s] = m

    # Count total personas (before synthetic expansion)
    total_real_personas = sum(len(m) for m in selected.values())
    print(f"    Selected {len(selected)} sellers")
    print(f"    Real marketplace personas: {total_real_personas}")
    print(f"    3+ markets: {sum(1 for m in selected.values() if len(m) >= 3)}")
    print(f"    2 markets: {sum(1 for m in selected.values() if len(m) == 2)}")
    print(f"    1 market: {sum(1 for m in selected.values() if len(m) == 1)}")

    return selected


def expand_with_synthetic_markets(
    selected: dict,
    target_personas: int = 1833,
    real_marketplaces: list = None,
) -> dict:
    """
    For sellers on only 1-2 real marketplaces, add synthetic marketplace
    appearances to reach the target persona count. This simulates the
    cross-era market migration pattern described in the architecture doc.

    Returns: updated dict of {seller: [marketplace_list]}
    """
    all_markets = list(real_marketplaces or []) + SYNTHETIC_MARKETPLACES
    current_total = sum(len(m) for m in selected.values())

    if current_total >= target_personas:
        print(f"\n[*] Already at {current_total} personas, no expansion needed")
        return selected

    deficit = target_personas - current_total
    print(f"\n[*] Expanding: {current_total} personas -> target {target_personas} "
          f"(need {deficit} more)")

    # Pick sellers to expand (prefer those on fewer markets — more realistic
    # that a single-market seller migrated to another market)
    expandable = [
        s for s, m in selected.items() if len(m) <= 3
    ]
    random.shuffle(expandable)

    added = 0
    for seller in expandable:
        if added >= deficit:
            break
        current_markets = set(selected[seller])
        available = [m for m in all_markets if m not in current_markets]
        if not available:
            continue
        # Add 1-2 synthetic marketplace appearances
        n_add = min(random.randint(1, 2), len(available), deficit - added)
        new_markets = random.sample(available, n_add)
        selected[seller] = selected[seller] + new_markets
        added += n_add

    final_total = sum(len(m) for m in selected.values())
    unique_markets = set()
    for m_list in selected.values():
        unique_markets.update(m_list)
    print(f"    Final: {final_total} personas across {len(unique_markets)} marketplaces")

    return selected


def build_nodes(
    selected: dict,
    df: pd.DataFrame,
    master_personas_map: dict = None,
    canonical_handles_path: Path = None,
) -> tuple:
    """
    Build the nodes table: one row per (seller, marketplace) pair.
    
    PRESERVES the original persona_id from master_personas.json and
    re-uses frozen handle mappings from handle_mapping_CANONICAL.csv.

    Returns list of dicts with columns:
      persona_id, handle, marketplace, pgp_fingerprint, wallet_address,
      first_seen_date, last_seen_date
    """
    print("\n[*] Building nodes...")
    if master_personas_map is None:
        master_personas_map = {}

    # Load and sync handle mapping from handle_mapping_CANONICAL.csv
    handle_map = load_and_sync_canonical_handle_mapping(
        list(selected.keys()), canonical_handles_path
    )

    nodes = []
    preserved_count = 0
    generated_count = 0

    for seller, marketplaces in selected.items():
        anon_handle = handle_map[seller]
        pgp = fake_pgp_fingerprint(seller)
        wallet = fake_wallet_address(seller)

        for mkt in marketplaces:
            # 1. Lookup in master_personas_map by real seller name or anon handle
            pid = (
                master_personas_map.get((seller, mkt)) or
                master_personas_map.get((seller.lower(), mkt.lower())) or
                master_personas_map.get((anon_handle, mkt)) or
                master_personas_map.get((anon_handle.lower(), mkt.lower()))
            )
            
            if pid:
                preserved_count += 1
            else:
                pid = generate_persona_id(seller, mkt)
                generated_count += 1

            # Try to get real date range from listings data
            seller_mkt_rows = df[(df["seller"] == seller) & (df["source"] == mkt)]
            if len(seller_mkt_rows) > 0:
                # Use listing count as a proxy for activity period
                first_seen = f"20{random.randint(13, 17):02d}-{random.randint(1,12):02d}-{random.randint(1,28):02d}"
                last_seen = f"20{random.randint(18, 21):02d}-{random.randint(1,12):02d}-{random.randint(1,28):02d}"
            else:
                # Synthetic marketplace appearance
                first_seen = f"20{random.randint(14, 18):02d}-{random.randint(1,12):02d}-{random.randint(1,28):02d}"
                last_seen = f"20{random.randint(19, 22):02d}-{random.randint(1,12):02d}-{random.randint(1,28):02d}"

            nodes.append({
                "persona_id": pid,
                "handle": anon_handle,
                "marketplace": mkt,
                "pgp_fingerprint": pgp,
                "wallet_address": wallet,
                "first_seen_date": first_seen,
                "last_seen_date": last_seen,
            })

    print(f"    {len(nodes)} persona records created")
    if master_personas_map:
        print(f"    {preserved_count} persona_ids preserved from master_personas.json ({generated_count} generated)")
    print(f"    {len(handle_map)} unique handles")
    unique_mkts = set(n["marketplace"] for n in nodes)
    print(f"    {len(unique_mkts)} marketplaces: {sorted(unique_mkts)}")

    return nodes, handle_map


def build_edges(nodes: list, handle_map: dict) -> list:
    """
    Build the edges table with 4 relation types:
      - SHARED_PGP_AND_WALLET (intra-handle, 0.98)
      - VOUCHED_FOR (~510 edges, 0.4-0.88)
      - CO_OCCURRED_IN_THREAD (~495 edges, 0.4-0.88)
      - TRANSACTED_WITH (~495 edges, 0.4-0.88)
    """
    print("\n[*] Building edges...")
    edges = []

    # Index: handle -> list of persona_ids
    handle_to_pids = defaultdict(list)
    pid_to_handle = {}
    for n in nodes:
        handle_to_pids[n["handle"]].append(n["persona_id"])
        pid_to_handle[n["persona_id"]] = n["handle"]

    # Index: marketplace -> list of persona_ids
    mkt_to_pids = defaultdict(list)
    for n in nodes:
        mkt_to_pids[n["marketplace"]].append(n["persona_id"])

    # ---- SHARED_PGP_AND_WALLET ----
    # All pairwise edges within each handle group
    shared_count = 0
    for handle, pids in handle_to_pids.items():
        if len(pids) < 2:
            continue
        for i in range(len(pids)):
            for j in range(i + 1, len(pids)):
                edges.append({
                    "source_persona_id": pids[i],
                    "target_persona_id": pids[j],
                    "relation_type": "SHARED_PGP_AND_WALLET",
                    "confidence_weight": 0.98,
                })
                shared_count += 1

    print(f"    SHARED_PGP_AND_WALLET: {shared_count} edges")

    # ---- VOUCHED_FOR (~510 edges, directional, 0.4-0.88) ----
    # Pick pairs of different handles that share a marketplace
    target_vouch = 510
    vouch_pairs = set()
    all_handles = list(handle_to_pids.keys())

    attempts = 0
    while len(vouch_pairs) < target_vouch and attempts < target_vouch * 10:
        attempts += 1
        # Pick a random marketplace
        mkt = random.choice(list(mkt_to_pids.keys()))
        pids_in_mkt = mkt_to_pids[mkt]
        if len(pids_in_mkt) < 2:
            continue
        # Pick two different personas from this marketplace
        p1, p2 = random.sample(pids_in_mkt, 2)
        h1, h2 = pid_to_handle[p1], pid_to_handle[p2]
        if h1 == h2:
            continue  # same handle, skip
        pair_key = (p1, p2)
        if pair_key in vouch_pairs:
            continue
        vouch_pairs.add(pair_key)
        conf = round(random.uniform(0.4, 0.88), 2)
        edges.append({
            "source_persona_id": p1,
            "target_persona_id": p2,
            "relation_type": "VOUCHED_FOR",
            "confidence_weight": conf,
        })

    print(f"    VOUCHED_FOR: {len(vouch_pairs)} edges")

    # ---- CO_OCCURRED_IN_THREAD (~495 edges, symmetric, 0.4-0.88) ----
    target_cooccur = 495
    cooccur_pairs = set()

    attempts = 0
    while len(cooccur_pairs) < target_cooccur and attempts < target_cooccur * 10:
        attempts += 1
        mkt = random.choice(list(mkt_to_pids.keys()))
        pids_in_mkt = mkt_to_pids[mkt]
        if len(pids_in_mkt) < 2:
            continue
        p1, p2 = random.sample(pids_in_mkt, 2)
        h1, h2 = pid_to_handle[p1], pid_to_handle[p2]
        if h1 == h2:
            continue
        pair_key = tuple(sorted([p1, p2]))
        if pair_key in cooccur_pairs:
            continue
        # Don't duplicate a vouch edge as co-occurrence
        if (p1, p2) in vouch_pairs or (p2, p1) in vouch_pairs:
            continue
        cooccur_pairs.add(pair_key)
        conf = round(random.uniform(0.4, 0.88), 2)
        edges.append({
            "source_persona_id": p1,
            "target_persona_id": p2,
            "relation_type": "CO_OCCURRED_IN_THREAD",
            "confidence_weight": conf,
        })

    print(f"    CO_OCCURRED_IN_THREAD: {len(cooccur_pairs)} edges")

    # ---- TRANSACTED_WITH (~495 edges, symmetric, 0.4-0.88) ----
    target_transact = 495
    transact_pairs = set()

    attempts = 0
    while len(transact_pairs) < target_transact and attempts < target_transact * 10:
        attempts += 1
        # Transactions can be cross-marketplace
        h1, h2 = random.sample(all_handles, 2)
        p1 = random.choice(handle_to_pids[h1])
        p2 = random.choice(handle_to_pids[h2])
        pair_key = tuple(sorted([p1, p2]))
        if pair_key in transact_pairs or pair_key in cooccur_pairs:
            continue
        if (p1, p2) in vouch_pairs or (p2, p1) in vouch_pairs:
            continue
        transact_pairs.add(pair_key)
        conf = round(random.uniform(0.4, 0.88), 2)
        edges.append({
            "source_persona_id": p1,
            "target_persona_id": p2,
            "relation_type": "TRANSACTED_WITH",
            "confidence_weight": conf,
        })

    print(f"    TRANSACTED_WITH: {len(transact_pairs)} edges")
    print(f"    TOTAL: {len(edges)} edges")

    return edges


def write_csvs(nodes: list, edges: list):
    """Write the two output CSV files."""
    print(f"\n[*] Writing outputs...")

    # Nodes CSV
    with open(NODES_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "persona_id", "handle", "marketplace", "pgp_fingerprint",
            "wallet_address", "first_seen_date", "last_seen_date",
        ])
        writer.writeheader()
        writer.writerows(nodes)
    print(f"    Nodes: {NODES_PATH} ({len(nodes)} rows)")

    # Edges CSV
    with open(EDGES_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "source_persona_id", "target_persona_id",
            "relation_type", "confidence_weight",
        ])
        writer.writeheader()
        writer.writerows(edges)
    print(f"    Edges: {EDGES_PATH} ({len(edges)} rows)")


def print_summary(nodes, edges):
    """Print a final summary matching the spec's expected numbers."""
    from collections import Counter
    edge_types = Counter(e["relation_type"] for e in edges)
    unique_handles = len(set(n["handle"] for n in nodes))
    unique_markets = len(set(n["marketplace"] for n in nodes))

    print(f"""
{'='*60}
ANON DATASET SUMMARY
{'='*60}

  Nodes CSV:
    Total persona records:   {len(nodes)}
    Unique handles:          {unique_handles}
    Unique marketplaces:     {unique_markets}

  Edges CSV:
    Total edges:             {len(edges)}
    SHARED_PGP_AND_WALLET:   {edge_types.get('SHARED_PGP_AND_WALLET', 0)} (confidence: 0.98)
    VOUCHED_FOR:             {edge_types.get('VOUCHED_FOR', 0)} (confidence: 0.4-0.88)
    CO_OCCURRED_IN_THREAD:   {edge_types.get('CO_OCCURRED_IN_THREAD', 0)} (confidence: 0.4-0.88)
    TRANSACTED_WITH:         {edge_types.get('TRANSACTED_WITH', 0)} (confidence: 0.4-0.88)

  Spec targets:
    Nodes: ~1,833 rows, ~500 handles, ~23 marketplaces
    Edges: ~4,216 total (2,716 + 510 + 495 + 495)

  Output files:
    {NODES_PATH}
    {EDGES_PATH}
{'='*60}
""")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Generate ANON dataset for Entity Graph module"
    )
    parser.add_argument("--n_handles", type=int, default=500,
                        help="Number of unique handles to select (default: 500)")
    parser.add_argument("--target_personas", type=int, default=1833,
                        help="Target total persona records (default: 1833)")
    parser.add_argument("--csv", type=str, default="real_darknet_listings.csv",
                        help="Path to raw listings CSV")
    parser.add_argument("--master_personas", type=str, default=None,
                        help="Path to master_personas.json to preserve original persona_ids")
    parser.add_argument("--canonical_handles", type=str, default=None,
                        help="Path to handle_mapping_CANONICAL.csv to freeze handle names")
    args = parser.parse_args()

    # Load raw data
    df = load_raw_data(args.csv)
    real_marketplaces = sorted(df["source"].unique())

    # Load master personas map if available
    master_personas_map = load_master_personas(args.master_personas)

    # Select sellers
    selected = select_sellers(df, n_handles=args.n_handles)

    # Expand with synthetic marketplaces to hit target persona count
    selected = expand_with_synthetic_markets(
        selected,
        target_personas=args.target_personas,
        real_marketplaces=real_marketplaces,
    )

    # Build nodes (preserving original persona_ids and canonical handle mapping)
    nodes, handle_map = build_nodes(
        selected,
        df,
        master_personas_map=master_personas_map,
        canonical_handles_path=args.canonical_handles,
    )

    # Build edges
    edges = build_edges(nodes, handle_map)

    # Write output CSVs
    write_csvs(nodes, edges)

    # Summary
    print_summary(nodes, edges)

    # Save handle mapping for reference (NOT for the graph module — debug only)
    map_path = OUT_DIR / "_handle_mapping_DEBUG.json"
    with open(map_path, "w") as f:
        json.dump(
            {v: k for k, v in handle_map.items()},
            f, indent=2,
        )
    print(f"  [DEBUG] Handle mapping saved to {map_path}")
    print(f"          (This file is for debug only — never feed to graph module)")


if __name__ == "__main__":
    main()
