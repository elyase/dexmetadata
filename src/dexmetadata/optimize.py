"""
Find optimal parameters for fetching pool metadata based on your RPC connection.
"""

import asyncio
import logging
import time
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from typing import Optional

from dexmetadata import fetch

# Suppress logging and console output
logging.getLogger().setLevel(logging.CRITICAL)
null_output = StringIO()

# ANSI color codes (with bold)
RED = "\033[1;38;5;203m"
GREEN = "\033[1;38;5;118m"
YELLOW = "\033[1;38;5;220m"
RESET = "\033[0m"

# Test pool addresses
KNOWN_POOLS = [
    "0x31f609019d0CC0b8cC865656142d6FeD69853689",  # WETH/POPCAT
    "0xfBB6Eed8e7aa03B138556eeDaF5D271A5E1e43ef",  # USDC/cbBTC
    "0x6cDcb1C4A4D1C3C6d054b27AC5B77e89eAFb971d",  # USDC/AERO
    "0x323b43332F97B1852D8567a08B1E8ed67d25A8d5",  # WETH/msETH
] * 20000


async def fetch_with_size(
    rpc_url: str,
    pool_addresses: list[str],
    batch_size: int,
    max_concurrent: int = 1,
    silent: bool = True,
) -> list:
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
                    format="dict",
                    use_cache=False,
                ),
            )
        return result
    except Exception as e:
        if not silent:
            print(f"Error: {e}")
        return []


async def find_max_batch_size(rpc_url: str) -> int:
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


async def measure_response_time(rpc_url: str, batch_size: int) -> float:
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


def calculate_concurrency(
    rate_limit: Optional[float], avg_response_time: float, is_per_second: bool = False
) -> int:
    """Calculate optimal concurrency based on rate limit."""
    if not rate_limit:
        return 2  # Default concurrency

    # Convert to requests per minute if needed and apply safety margin (85%)
    rpm = (rate_limit * 60 if is_per_second else rate_limit) * 0.85

    # Calculate concurrency based on rate limit and response time
    # If user specified their own rate limit, trust it (might be their own node)
    return max(1, int((rpm * avg_response_time) / 60))


async def verify_parameters(rpc_url: str, batch_size: int, max_concurrent: int) -> int:
    """Verify the calculated parameters with a larger test set."""
    print("\nVerifying parameters with a larger test set...")

    # Use enough pools to test full concurrency (at least batch_size * max_concurrent)
    needed_pools = batch_size * max(3, max_concurrent)
    available_pools = len(KNOWN_POOLS)

    # Check if we're limited by available test pools
    if needed_pools > available_pools:
        print(
            f"{YELLOW}Warning: Limited by available test pools. Need {needed_pools} but only have {available_pools}.{RESET}"
        )
        print(
            f"{YELLOW}Results may not fully reflect performance at this concurrency level.{RESET}"
        )

    test_pools = KNOWN_POOLS[: min(needed_pools, available_pools)]
    start_time = time.time()

    result = await fetch_with_size(
        rpc_url, test_pools, batch_size, max_concurrent=max_concurrent, silent=False
    )

    duration = time.time() - start_time
    total_pools = len(test_pools)
    successful_pools = len([p for p in result if p.get("token0_name")])
    success_rate = successful_pools / total_pools

    # Calculate throughput (pools per second)
    throughput = successful_pools / duration if duration > 0 else 0
    # Calculate time per pool in milliseconds for better readability
    ms_per_pool = (duration / successful_pools) * 1000 if successful_pools > 0 else 0

    print(f"\nVerification Results:")
    print(f"Total pools tested: {total_pools}")
    print(f"Successfully fetched: {successful_pools}")
    print(f"Success rate: {success_rate:.1%}")
    print(f"Total time: {duration:.2f}s")
    print(f"Average time per pool: {ms_per_pool:.2f} ms")
    print(f"Throughput: {throughput:.1f} pools/second")
    print(f"Concurrent batches used: {max_concurrent}")

    # Calculate estimated throughput for ideal conditions
    # (if we could fully utilize all concurrent batches)
    if max_concurrent > total_pools / batch_size:
        ideal_concurrent = total_pools / batch_size
        ideal_throughput = (
            throughput * (max_concurrent / ideal_concurrent)
            if ideal_concurrent > 0
            else 0
        )
        print(
            f"Estimated throughput with full concurrency: {ideal_throughput:.1f} pools/second"
        )

    # Only suggest reducing concurrency if success rate is too low
    # We don't try increasing it to avoid exhausting RPC quotas
    if success_rate < 0.9:  # Less than 90% success rate
        suggested_concurrent = max(1, max_concurrent - 2)
        print(
            f"\n{RED}Warning: Success rate is low ({success_rate:.1%}). Consider reducing max_concurrent_batches to {suggested_concurrent}{RESET}"
        )
        return suggested_concurrent

    return max_concurrent


async def optimize(
    rpc_url: str,
    rate_limit: Optional[float] = None,
    is_per_second: bool = False,
    batch_size: Optional[int] = None,
    concurrency: Optional[int] = None,
) -> tuple[int, int]:
    """
    Find optimal parameters for fetching pool metadata.

    Args:
        rpc_url: RPC URL to test
        rate_limit: Rate limit in requests per minute or second
        is_per_second: Whether rate_limit is in requests per second
        batch_size: Optional fixed batch size to use
        concurrency: Optional fixed concurrency to use

    Returns:
        Tuple of (batch_size, max_concurrent_batches)
    """
    if not rate_limit and not concurrency:
        print(
            f"{YELLOW}Warning: No rate limit specified. Using conservative default concurrency.{RESET}"
        )
        print(
            f"{YELLOW}Specify rate limit for more accurate results based on your provider's limits.{RESET}"
        )
        print(
            f"{YELLOW}Or use concurrency to force a specific concurrency value.{RESET}"
        )

    # Step 1: Determine maximum batch size
    max_batch_size = batch_size or await find_max_batch_size(rpc_url)
    if batch_size:
        print(f"Using batch size: {max_batch_size}")
    else:
        print(f"Maximum working batch size: {max_batch_size}")

    # Step 2: Measure response time and calculate initial concurrency
    avg_response_time = await measure_response_time(rpc_url, max_batch_size)

    # Use manually specified concurrency if provided
    if concurrency:
        initial_concurrent = concurrency
        print(f"Using manually specified concurrency: {initial_concurrent}")
    else:
        initial_concurrent = calculate_concurrency(
            rate_limit, avg_response_time, is_per_second
        )

    # Step 3: Verify parameters with real test
    final_concurrent = await verify_parameters(
        rpc_url, max_batch_size, initial_concurrent
    )

    # Step 4: Output final results
    print("\nFinal optimal parameters:")
    print(f"  batch_size: {max_batch_size}")
    print(f"  max_concurrent_batches: {final_concurrent}")

    return max_batch_size, final_concurrent
