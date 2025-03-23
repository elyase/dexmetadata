"""
DEX pool coverage analysis

Get data with:
spice https://dune.com/queries/4866741/8059379/ --csv && mv "$(ls -t dune__4866741__*.csv | head -1)" last_month_swap_sample.csv
"""

import asyncio
import csv
import glob
import logging
import os
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from dexmetadata import fetch

logging.basicConfig(format="%(message)s", level=logging.INFO)
log = logging.getLogger()

# Add RPC URLs for major chains - use public nodes for testing
# For production, replace with reliable RPC endpoints
RPC_URLS = {
    # Working chains
    "base": "https://base-rpc.publicnode.com",
    "ethereum": "https://ethereum-rpc.publicnode.com",
    "bnb": "https://bsc-rpc.publicnode.com",
    "arbitrum": "https://arbitrum-one-rpc.publicnode.com",
    "polygon": "https://polygon-bor-rpc.publicnode.com",
    "optimism": "https://optimism-rpc.publicnode.com",
    "berachain": "https://berachain-rpc.publicnode.com",
    "sonic": "https://sonic-rpc.publicnode.com",
    "gnosis": "https://gnosis-rpc.publicnode.com",
    "avalanche": "https://avalanche-c-chain-rpc.publicnode.com",
    "sei": "https://sei-evm-rpc.publicnode.com",
    "unichain": "https://unichain-rpc.publicnode.com",
    "scroll": "https://scroll-rpc.publicnode.com",
    "blast": "https://blast-rpc.publicnode.com",
    # The following chains had issues with publicnode.com RPCs
    # Uncomment and update if you have working RPC endpoints
    # "worldchain": "https://worldchain-rpc.publicnode.com",
    # "celo": "https://celo-rpc.publicnode.com",
    # "mantle": "https://mantle-rpc.publicnode.com",
    # "zksync": "https://zksync-era-rpc.publicnode.com",
    # "ronin": "https://ronin-rpc.publicnode.com",
    # "flare": "https://flare-rpc.publicnode.com",
    # "fantom": "https://fantom-rpc.publicnode.com",
    # "zkevm": "https://polygon-zkevm-rpc.publicnode.com",
    # "linea": "https://linea-rpc.publicnode.com",
    # "kaia": "https://kaia-rpc.publicnode.com",
}


def load_pools():
    """Load pool data from first matching CSV"""
    pools = defaultdict(set)
    dex_map = defaultdict(dict)
    skipped_chains = defaultdict(int)
    total_pools = 0

    # Track unique DEX types to test only one pool per type
    unique_dex_types = {}  # Format: {dex_type: (chain, addr)}

    # Look for CSV in the same directory as the script
    path = Path(__file__).parent / "last_month_swap_sample.csv"

    if not path.exists():
        log.error(f"CSV file not found: {path}")
        log.error(
            "Please ensure you have run the Dune query and downloaded the CSV file"
            "\n\n"
            "spice https://dune.com/queries/4866741/8059379/ --csv"
        )
        raise FileNotFoundError(f"CSV file not found: {path}")

    with open(path) as f:
        for row in csv.DictReader(f):
            total_pools += 1
            chain = row["dex"].split("__", 1)[0]
            if chain in RPC_URLS:
                addr = row["pool_id"]
                dex_type = "_".join(
                    row["dex"].split("__")[1:]
                )  # Extract DEX type without chain prefix

                # Store just one pool per unique DEX type
                if dex_type not in unique_dex_types:
                    unique_dex_types[dex_type] = (chain, addr)
                    pools[chain].add(addr)
                    dex_map[chain][addr] = row["dex"]
            else:
                skipped_chains[chain] += 1

    # Print skipped chains info
    skipped_total = sum(skipped_chains.values())
    log.info(f"\nSkipped {skipped_total} pools on chains without RPC URLs:")
    for chain, count in sorted(skipped_chains.items(), key=lambda x: -x[1]):
        log.info(f"  {chain}: {count} pools")

    total_unique_pools = sum(len(addrs) for addrs in pools.values())
    log.info(f"\nOriginal pool count: {total_pools}")
    log.info(
        f"Testing only {total_unique_pools} pools (one per DEX type) to improve performance"
    )
    log.info("To increase coverage, add more RPC URLs to the RPC_URLS dictionary")

    return pools, dex_map


def validate(pool):
    """Check if pool has valid token data"""
    if pool is None:
        return False

    req_fields = ("symbol", "name", "address", "decimals")

    for token in [pool.token0, pool.token1]:
        for field in req_fields:
            value = getattr(token, field, None)
            if not value and not isinstance(value, (int, bool)):
                return False

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

        failed = [a for a, p in zip(addrs, pools) if not validate(p)]
        if failed:
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


async def main_async():
    """Async version of main function to properly handle aiohttp sessions"""
    pools, dex_map = load_pools()

    if not pools:
        log.warning("No pools to test on configured chains")
        return

    log.info(
        f"Testing {sum(len(p) for p in pools.values())} unique pools across {len(pools)} chains"
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

    # Summarize results by chain
    log.info("\nChain Success Rates:")
    for chain, success, valid, _ in sorted(results, key=lambda x: -x[1]):
        log.info(f"{chain:12} {success:6.1f}% fetched, {valid:6.1f}% valid")

    # Calculate averages
    avg_success = sum(s for _, s, _, _ in results) / max(1, len(results))
    avg_valid = sum(v for _, _, v, _ in results) / max(1, len(results))
    log.info(f"\nAverage: {avg_success:.1f}% success, {avg_valid:.1f}% valid")

    # Calculate aggregate success
    total_tested = sum(len(pools[chain]) for chain in pools)
    total_success = sum(int(len(pools[chain]) * s / 100) for chain, s, _, _ in results)
    total_valid = sum(int(len(pools[chain]) * v / 100) for chain, _, v, _ in results)

    if total_tested > 0:
        log.info(
            f"Aggregate: {100 * total_success / total_tested:.1f}% success, {100 * total_valid / total_tested:.1f}% valid"
        )

    # Sort and display failed pools by DEX
    log.info("\nFailed Pools by DEX (in order of most failures):")
    sorted_dexes = sorted(
        failed_pools_by_dex.items(), key=lambda x: len(x[1]), reverse=True
    )

    if sorted_dexes:
        for dex_name, dex_ids in sorted_dexes:
            log.info(f"\n{dex_name.title()} ({len(dex_ids)} failed pools):")
            for dex_id in dex_ids[:10]:  # Limit to first 10 per DEX
                log.info(f"  - {dex_id}")
            if len(dex_ids) > 10:
                log.info(f"  ... and {len(dex_ids) - 10} more")
    else:
        log.info("No failed pools found for the chains being tested!")

    # Reminder about coverage
    log.info(
        "\nNOTE: This report only covers one pool per unique DEX type for efficiency."
    )


def main():
    """Entry point that properly handles asyncio resources"""
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
