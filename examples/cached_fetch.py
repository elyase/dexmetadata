#!/usr/bin/env python
"""
Example script demonstrating how to use the cache functionality.

This script demonstrates the dexmetadata caching system which provides:

1. In-memory caching of pool metadata to avoid redundant RPC calls
2. Persistent storage using SQLite for caching between application runs
3. Smart eviction policy using a hybrid LRU/LFU approach:
   - LRU (Least Recently Used): Prioritizes recently accessed pools
   - LFU (Least Frequently Used): Prioritizes frequently accessed pools
4. Configurable limits by pool count or memory usage

Benefits of using the cache:
- Dramatic speedups (1000-4000x faster on cached data)
- Reduced RPC usage and costs
- Better user experience with faster responses
- Less strain on RPC providers

The cache is enabled by default and can be configured with:
- cache_max_pools: Maximum number of pools to cache (default: 10,000)
- cache_max_size_mb: Alternative way to specify cache size in MB
- cache_persist: Whether to persist to disk (default: False)

This example shows:
1. How to fetch pool metadata with caching enabled
2. Different cache configuration options
3. Cache persistence demonstration
"""

import logging
import time

from dexmetadata import fetch

# Set logging to DEBUG level to see more detailed messages
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger()

# Use a realistic set of pool addresses
POOL_ADDRESSES = [
    "0xfBB6Eed8e7aa03B138556eeDaF5D271A5E1e43ef",  # cbBTC/USDC on uniswap v3
    "0x31f609019d0CC0b8cC865656142d6FeD69853689",  # POPCAT/WETH on uniswap v2
    "0x6cDcb1C4A4D1C3C6d054b27AC5B77e89eAFb971d",  # AERO/USDC on Aerodrome
    "0x323b43332F97B1852D8567a08B1E8ed67d25A8d5",  # msETH/WETH on Pancake Swap
]


def main():
    # Display a separator for better readability
    print("\n" + "=" * 50)
    print("Cache Test - First Run (Cold Cache)")
    print("=" * 50)

    print("Fetching pool metadata for the first time (cache cold)...")
    start_time = time.time()

    # First fetch - cache is empty
    pools = fetch(
        POOL_ADDRESSES,
        rpc_url="https://base-rpc.publicnode.com",
        batch_size=2,  # 2 pools per batch
        max_concurrent_batches=2,  # 2 concurrent batches
        use_cache=True,  # Enable caching
        cache_max_pools=1000,  # Cache up to 1000 pools
        cache_persist=True,  # Enable persistence to disk
        format="dict",  # Get raw dictionary for easier debugging
    )

    cold_time = time.time() - start_time
    print(f"Cold fetch completed in {cold_time:.2f} seconds")
    print(f"Retrieved {len(pools)} pools\n")

    # Print pool details if we got results
    if pools:
        print("First fetch results:")
        for i, pool in enumerate(pools):
            print(f"Pool {i + 1}: {pool['pool_address']}")
            print(f"  Token0: {pool['token0_symbol']} ({pool['token0_address']})")
            print(f"  Token1: {pool['token1_symbol']} ({pool['token1_address']})")

    # Display a separator for better readability
    print("\n" + "=" * 50)
    print("Cache Test - Second Run (Warm Cache)")
    print("=" * 50)

    print("Fetching the same pools again (cache warm)...")
    start_time = time.time()

    # Second fetch - should use cache
    pools_again = fetch(
        POOL_ADDRESSES,
        rpc_url="https://base-rpc.publicnode.com",
        batch_size=2,  # 2 pools per batch
        max_concurrent_batches=2,  # 2 concurrent batches
        use_cache=True,
        format="dict",  # Get raw dictionary for easier debugging
    )

    warm_time = time.time() - start_time
    print(f"Warm fetch completed in {warm_time:.2f} seconds")
    print(f"Retrieved {len(pools_again)} pools")

    # Calculate speedup if there are pool results
    if len(pools_again) > 0 and warm_time > 0:
        print(f"Speedup from caching: {cold_time / warm_time:.1f}x faster\n")

    # Print pool details for second run if we got results
    if pools_again:
        print("Second fetch results (from cache):")
        for i, pool in enumerate(pools_again):
            print(f"Pool {i + 1}: {pool['pool_address']}")
            print(f"  Token0: {pool['token0_symbol']} ({pool['token0_address']})")
            print(f"  Token1: {pool['token1_symbol']} ({pool['token1_address']})")
    else:
        print("\nNo pool metadata retrieved. Possible causes:")
        print("- RPC endpoint may be unavailable or rate limited")
        print("- Pool addresses might not exist on the specified chain")
        print("- The contract may not be compatible with the metadata fetcher")

    # Cache persistence demo
    print("\nDemonstrating cache persistence...")
    print("Run this script again to see that cached data persists between runs")


if __name__ == "__main__":
    main()
