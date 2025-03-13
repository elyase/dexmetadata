#!/usr/bin/env python
"""
Find optimal parameters for fetching pool metadata based on your RPC connection.
"""

import argparse
import asyncio
import logging
import time
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO

from dexmetadata import fetch

# Suppress logging and console output
logging.getLogger().setLevel(logging.CRITICAL)
null_output = StringIO()

# ANSI color codes (with bold)
RED = "\033[1;38;5;203m"
GREEN = "\033[1;38;5;118m"
RESET = "\033[0m"

# Test pool addresses
KNOWN_POOLS = [
    "0x31f609019d0CC0b8cC865656142d6FeD69853689",  # WETH/POPCAT
    "0xfBB6Eed8e7aa03B138556eeDaF5D271A5E1e43ef",  # USDC/cbBTC
    "0x6cDcb1C4A4D1C3C6d054b27AC5B77e89eAFb971d",  # USDC/AERO
    "0x323b43332F97B1852D8567a08B1E8ed67d25A8d5",  # WETH/msETH
] * 100


async def fetch_with_size(
    rpc_url, pool_addresses, batch_size, max_concurrent=1, silent=True
):
    """Wrapper for fetch that handles async and output suppression."""
    try:
        with (
            redirect_stderr(null_output),
            redirect_stdout(null_output) if silent else redirect_stderr(null_output),
        ):
            loop = asyncio.get_running_loop()
            result = await loop.run_in_executor(
                None,
                lambda: fetch(
                    pool_addresses,
                    rpc_url=rpc_url,
                    batch_size=batch_size,
                    max_concurrent_batches=max_concurrent,
                    show_progress=not silent,
                ),
            )
        return result
    except Exception as e:
        if not silent:
            print(f"Error: {e}")
        return []


async def find_max_batch_size(rpc_url):
    """Find the maximum batch size that works for this RPC provider."""
    print("\nFinding maximum batch size...")
    print("Testing sizes: ", end="", flush=True)

    # Test sizes from largest to smallest
    test_sizes = [100, 75, 50, 40, 30, 25, 20, 15, 10, 4]

    for size in test_sizes:
        await asyncio.sleep(0.5)  # Avoid rate limiting

        # Prepare test pools (only need enough for the batch size)
        test_pool = KNOWN_POOLS[: min(size, len(KNOWN_POOLS))]
        if size > len(KNOWN_POOLS):
            test_pool = KNOWN_POOLS * (size // len(KNOWN_POOLS) + 1)
            test_pool = test_pool[:size]

        result = await fetch_with_size(rpc_url, test_pool, size)

        if result and len(result) > 0:
            print(f"{GREEN}{size}{RESET}", end=" ", flush=True)
            print()  # New line after progress
            return size
        else:
            print(f"{RED}{size}{RESET}", end=" ", flush=True)

    print()
    return 4  # Fallback


async def measure_response_time(rpc_url, batch_size):
    """Measure response time using the determined batch size."""
    print("\nMeasuring response time with optimal batch size...")

    test_pools = KNOWN_POOLS[:batch_size]
    start_time = time.time()

    result = await fetch_with_size(rpc_url, test_pools, batch_size)

    duration = time.time() - start_time

    if result and any(pool.get("token0_name") for pool in result):
        print(f"Average response time: {duration:.2f}s")
        return duration
    else:
        print("Failed to measure response time, using default of 0.7s")
        return 0.7


def calculate_concurrency(rate_limit, avg_response_time, is_per_second=False):
    """Calculate optimal concurrency based on rate limit."""
    if not rate_limit:
        return 2  # Default concurrency

    # Convert to requests per minute if needed and apply safety margin (85%)
    rpm = (rate_limit * 60 if is_per_second else rate_limit) * 0.85

    # Calculate max concurrent batches and cap at reasonable limits
    return min(max(1, int((rpm * avg_response_time) / 60)), 25)


async def main():
    parser = argparse.ArgumentParser(
        description="Find optimal parameters for fetching pool metadata"
    )
    parser.add_argument("--rpc", type=str, help="RPC URL")
    parser.add_argument("--network", type=str, default="base", help="Network name")
    parser.add_argument("--rpm", type=float, help="Rate limit in requests per minute")
    parser.add_argument("--rps", type=float, help="Rate limit in requests per second")
    parser.add_argument(
        "--batch-size", type=int, help="Specify a batch size instead of testing"
    )
    args = parser.parse_args()

    # Process arguments
    rpc_url = args.rpc or f"https://rpc.ankr.com/{args.network}"
    rate_limit = args.rpm if args.rpm else (args.rps if args.rps else None)
    is_per_second = bool(args.rps)

    # Step 1: Determine maximum batch size
    max_batch_size = args.batch_size or await find_max_batch_size(rpc_url)
    if args.batch_size:
        print(f"Using batch size: {max_batch_size}")
    else:
        print(f"Maximum working batch size: {max_batch_size}")

    # Step 2: Measure response time and calculate concurrency
    avg_response_time = await measure_response_time(rpc_url, max_batch_size)
    max_concurrent = calculate_concurrency(rate_limit, avg_response_time, is_per_second)

    # Step 3: Output results
    print("\nOptimal parameters:")
    print(f"  batch_size: {max_batch_size}")
    print(f"  max_concurrent_batches: {max_concurrent}")


if __name__ == "__main__":
    asyncio.run(main())
