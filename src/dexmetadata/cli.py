#!/usr/bin/env python
"""
Command-line interface for dexmetadata package.
"""

import asyncio
import sys
from typing import List, Optional, Union

import cyclopts
from cyclopts import App, Parameter

from dexmetadata import calculate_rate_limit_params, fetch
from dexmetadata.fetcher import get_web3
from dexmetadata.optimizer import (
    calculate_concurrency,
    find_max_batch_size,
    measure_response_time,
)

app = App(
    name="dexmetadata",
    description="A deployless multicall library for fetching DEX pool metadata",
)


@app.command(name="fetch")
def fetch_cli(
    pools: List[str] = Parameter(
        help="Pool addresses to fetch metadata for",
    ),
    network: str = Parameter(
        default="base", help="Network name (e.g., base, ethereum, arbitrum)"
    ),
    rpc_url: Optional[str] = Parameter(
        default=None, help="RPC URL (defaults to https://rpc.ankr.com/{network})"
    ),
    batch_size: int = Parameter(
        default=30, help="Number of pools to fetch in a single multicall batch"
    ),
    max_concurrent_batches: int = Parameter(
        default=25, help="Maximum number of concurrent batch requests"
    ),
    rpm: Optional[float] = Parameter(
        default=None, help="Maximum requests per minute (rate limit)"
    ),
    rps: Optional[float] = Parameter(
        default=None, help="Maximum requests per second (rate limit)"
    ),
    show_progress: bool = Parameter(default=True, help="Show progress bar"),
    output_file: Optional[str] = Parameter(
        default=None, help="File to write JSON output to"
    ),
    output_format: str = Parameter(default="json", help="Output format (json or csv)"),
):
    """Fetch metadata for DEX pools."""
    import csv
    import json
    import time
    from pprint import pprint

    start_time = time.time()

    # Determine RPC URL
    actual_rpc_url = rpc_url or f"https://rpc.ankr.com/{network}"

    # Calculate rate limit parameters if provided
    rate_limit = rpm if rpm is not None else (rps if rps is not None else None)
    is_per_second = rps is not None

    if rate_limit:
        # If rate limit is provided, calculate optimal parameters
        params = calculate_rate_limit_params(
            rate_limit=rate_limit, is_per_second=is_per_second, batch_size=batch_size
        )
        max_concurrent_batches = params.get(
            "max_concurrent_batches", max_concurrent_batches
        )

    # Fetch pool metadata
    pools_data = fetch(
        pools,
        network=network,
        rpc_url=actual_rpc_url,
        batch_size=batch_size,
        max_concurrent_batches=max_concurrent_batches,
        show_progress=show_progress,
    )

    duration = time.time() - start_time
    valid_pools = sum(1 for pool in pools_data if pool.get("token0_name"))

    print(
        f"\nFetched {valid_pools} pools in {duration:.2f}s ({len(pools_data) / duration:.2f} pools/s)"
    )

    # Handle output
    if output_file:
        with open(output_file, "w") as f:
            if output_format.lower() == "json":
                json.dump(pools_data, f, indent=2)
            elif output_format.lower() == "csv":
                if not pools_data:
                    print("No data to write to CSV")
                    return

                # Get field names from first pool
                fieldnames = list(pools_data[0].keys())
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(pools_data)
            else:
                print(f"Unsupported output format: {output_format}")
                return
        print(f"Output written to {output_file}")
    else:
        # Print sample output
        print("\nSample output:")
        pprint(pools_data[0] if pools_data else "No pools found")


@app.command(name="optimize")
def optimize_cli(
    network: str = Parameter(
        default="base", help="Network name (e.g., base, ethereum, arbitrum)"
    ),
    rpc_url: Optional[str] = Parameter(
        default=None, help="RPC URL (defaults to https://rpc.ankr.com/{network})"
    ),
    rpm: Optional[float] = Parameter(
        default=None, help="Rate limit in requests per minute"
    ),
    rps: Optional[float] = Parameter(
        default=None, help="Rate limit in requests per second"
    ),
    batch_size: Optional[int] = Parameter(
        default=None, help="Specify a batch size instead of testing"
    ),
    verbose: bool = Parameter(default=False, help="Show detailed output"),
):
    """Find optimal parameters for fetching pool metadata based on your RPC connection."""
    # Process arguments
    actual_rpc_url = rpc_url or f"https://rpc.ankr.com/{network}"
    rate_limit = rpm if rpm is not None else (rps if rps is not None else None)
    is_per_second = rps is not None

    async def run_optimization():
        # Step 1: Determine maximum batch size
        max_batch_size = batch_size or await find_max_batch_size(actual_rpc_url)
        if batch_size:
            print(f"Using batch size: {max_batch_size}")
        else:
            print(f"Maximum working batch size: {max_batch_size}")

        # Step 2: Measure response time and calculate concurrency
        avg_response_time = await measure_response_time(
            actual_rpc_url, max_batch_size, verbose=verbose
        )
        max_concurrent = calculate_concurrency(
            rate_limit, avg_response_time, is_per_second
        )

        # Step 3: Output results
        print("\nOptimal parameters:")
        print(f"  batch_size: {max_batch_size}")
        print(f"  max_concurrent_batches: {max_concurrent}")

        return {
            "batch_size": max_batch_size,
            "max_concurrent_batches": max_concurrent,
            "avg_response_time": avg_response_time,
        }

    return asyncio.run(run_optimization())


def main():
    """Entry point for the CLI."""
    sys.exit(app())


if __name__ == "__main__":
    main()
