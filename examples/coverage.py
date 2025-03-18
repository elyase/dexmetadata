"""
DEX pool coverage analysis

Get data with:
spice https://dune.com/queries/4866741/8059379/ --csv
"""

import asyncio
import csv
import glob
import logging
import os
from collections import defaultdict
from typing import Dict, List, Tuple

from dexmetadata import fetch

logging.basicConfig(format="%(message)s", level=logging.INFO)
log = logging.getLogger()

RPC_URLS = {
    "base": "https://base-rpc.publicnode.com",
    "ethereum": "https://ethereum-rpc.publicnode.com",
}


def load_pools():
    """Load pool data from first matching CSV"""
    pools = defaultdict(set)
    dex_map = defaultdict(dict)

    # Look for CSV in the same directory as the script
    script_dir = os.path.dirname(os.path.abspath(__file__))
    csv_pattern = os.path.join(script_dir, "dune__*.csv")

    try:
        path = next(glob.iglob(csv_pattern))
    except StopIteration:
        log.error(f"No CSV file found matching pattern: {csv_pattern}")
        log.error(
            "Please ensure you have run the Dune query and downloaded the CSV file"
            "\n\n"
            "spice https://dune.com/queries/4866741/8059379/ --csv"
        )
        raise

    with open(path) as f:
        for row in csv.DictReader(f):
            chain = row["dex"].split("_", 1)[0]
            if chain in RPC_URLS:
                addr = row["project_contract_address"]
                pools[chain].add(addr)
                dex_map[chain][addr] = row["dex"]

    return pools, dex_map


def validate(pool):
    """Check if pool has valid token data"""
    if pool is None:
        log.debug("Pool is None")
        return False

    req_fields = ("symbol", "name", "address", "decimals")

    for i, token in enumerate([pool.token0, pool.token1]):
        log.debug(f"\nValidating Token{i}:")
        for field in req_fields:
            value = getattr(token, field, None)
            if not value and not isinstance(value, (int, bool)):
                log.debug(f"❌ Token{i} missing or empty {field}: {value}")
                return False
            log.debug(f"✓ Token{i} {field}: {value}")

    return True


def process_chain(
    chain: str, addrs: List[str], dex_map: Dict[str, str]
) -> Tuple[str, float, float, List[str]]:
    """Fetch and validate pools for a single chain"""
    try:
        pools = fetch(
            list(addrs),
            rpc_url=RPC_URLS[chain],
            batch_size=30,
            max_concurrent_batches=25,
        )

        success = sum(p is not None for p in pools)
        valid = sum(validate(p) for p in pools)

        if failed := [a for a, p in zip(addrs, pools) if not validate(p)]:
            log.info(f"\nFailed {chain} pools:")
            log.info(
                "\n".join(
                    f"https://{chain}scan.org/address/{a} - {dex_map[a]}"
                    for a in failed[:10]
                )
            )

        return (chain, 100 * success / len(addrs), 100 * valid / len(addrs), failed)

    except Exception as e:
        log.error(f"{chain} error: {e}")
        return (chain, 0.0, 0.0, [])


def main():
    try:
        pools, dex_map = load_pools()
        log.info(
            f"Testing {sum(len(p) for p in pools.values())} pools across {len(pools)} chains"
        )

        results = []
        failed_pools_by_dex = defaultdict(list)

        for chain, addrs in pools.items():
            chain_result = process_chain(chain, addrs, dex_map[chain])
            results.append(chain_result)

            # Process failed pools
            _, _, _, failed_pools = chain_result
            for addr in failed_pools:
                if addr in dex_map[chain]:
                    dex_id = dex_map[chain][addr]
                    # Extract DEX name from the identifier (e.g., "base_maverick_1" -> "maverick")
                    parts = dex_id.split("_")
                    if len(parts) >= 2:
                        dex_name = parts[1]
                        failed_pools_by_dex[dex_name].append(dex_id)

        log.info("\nChain Success Rates:")
        for chain, success, valid, _ in sorted(results, key=lambda x: -x[1]):
            log.info(f"{chain:12} {success:6.1f}% fetched, {valid:6.1f}% valid")

        avg_success = sum(s for _, s, _, _ in results) / len(results)
        avg_valid = sum(v for _, _, v, _ in results) / len(results)
        log.info(f"\nAverage: {avg_success:.1f}% success, {avg_valid:.1f}% valid")

        # Sort and display failed pools by DEX
        log.info("\nFailed Pools by DEX (in order of most failures):")
        sorted_dexes = sorted(
            failed_pools_by_dex.items(), key=lambda x: len(x[1]), reverse=True
        )

        for dex_name, dex_ids in sorted_dexes:
            log.info(f"\n{dex_name.title()} ({len(dex_ids)} failed pools):")
            for dex_id in dex_ids:
                log.info(f"  - {dex_id}")

    except Exception as e:
        log.error(f"Error: {e}")
        raise


if __name__ == "__main__":
    main()
