#!/usr/bin/env python
"""
Command-line interface for dexmetadata package.
"""

import argparse
import asyncio
import json
import os
import sys
import time
from pathlib import Path
from typing import List, Optional

from dexmetadata.cache import (
    DEFAULT_CACHE_DIR,
    get_default_cache,
)
from dexmetadata.optimize import optimize

from . import fetch
from .coverage import DEFAULT_RPC_URLS, analyze_coverage_sync


def format_size(size_bytes: float) -> str:
    """Format bytes as a human-readable string with units."""
    if size_bytes < 1024:
        return f"{size_bytes:.2f} B"
    size_kb = size_bytes / 1024
    if size_kb < 1024:
        return f"{size_kb:.2f} KB"
    size_mb = size_kb / 1024
    if size_mb < 1024:
        return f"{size_mb:.2f} MB"
    size_gb = size_mb / 1024
    return f"{size_gb:.2f} GB"


def detect_output_format(output_file: str) -> str:
    """Detect output format from file extension."""
    if not output_file:
        return "text"

    ext = Path(output_file).suffix.lower()
    if ext == ".json":
        return "json"
    elif ext == ".csv":
        return "csv"
    return "text"


def fetch_cli(
    pool_addresses: List[str],
    network: str = "base",
    rpc_url: str = None,
    batch_size: int = 30,
    max_concurrent_batches: int = 25,
    show_progress: bool = True,
    output_file: str = None,
    output_format: str = None,
    use_cache: bool = True,
    cache_max_pools: int = 10000,
    cache_persist: bool = True,
):
    """Fetch metadata for pool addresses."""
    start_time = time.time()

    # Auto-detect format if not specified
    if output_format is None:
        output_format = detect_output_format(output_file)

    # Fetch the pool metadata
    pools = fetch(
        pool_addresses,
        network=network,
        rpc_url=rpc_url,
        batch_size=batch_size,
        max_concurrent_batches=max_concurrent_batches,
        show_progress=show_progress,
        use_cache=use_cache,
        cache_max_pools=cache_max_pools,
        cache_persist=cache_persist,
    )

    elapsed_time = time.time() - start_time
    throughput = len(pools) / max(0.001, elapsed_time)

    print(
        f"\nFetched {len(pools)} pools in {elapsed_time:.2f}s ({throughput:.1f} pools/s)"
    )

    # Handle output
    if output_file:
        with open(output_file, "w") as f:
            if output_format == "json":
                # Convert to dict for JSON serialization
                pool_dicts = [
                    {
                        "pool_address": pool.address,
                        "token0_address": pool.token0.address,
                        "token0_name": pool.token0.name,
                        "token0_symbol": pool.token0.symbol,
                        "token0_decimals": pool.token0.decimals,
                        "token1_address": pool.token1.address,
                        "token1_name": pool.token1.name,
                        "token1_symbol": pool.token1.symbol,
                        "token1_decimals": pool.token1.decimals,
                    }
                    for pool in pools
                ]
                json.dump(pool_dicts, f, indent=2)
            elif output_format == "csv":
                import csv

                if not pools:
                    print("No pools to write to CSV")
                    return

                # Convert to dict for CSV writer
                pool_dicts = [
                    {
                        "pool_address": pool.address,
                        "token0_address": pool.token0.address,
                        "token0_name": pool.token0.name,
                        "token0_symbol": pool.token0.symbol,
                        "token0_decimals": pool.token0.decimals,
                        "token1_address": pool.token1.address,
                        "token1_name": pool.token1.name,
                        "token1_symbol": pool.token1.symbol,
                        "token1_decimals": pool.token1.decimals,
                    }
                    for pool in pools
                ]

                fieldnames = [
                    "pool_address",
                    "token0_address",
                    "token0_name",
                    "token0_symbol",
                    "token0_decimals",
                    "token1_address",
                    "token1_name",
                    "token1_symbol",
                    "token1_decimals",
                ]

                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(pool_dicts)
            else:
                # Plain text format
                for pool in pools:
                    f.write(f"{str(pool)}\n\n")

            print(f"Output written to {output_file}")
    else:
        # Display results to console
        if pools:
            # Show the first few pools
            display_count = min(5, len(pools))
            for i in range(display_count):
                print(f"\nPool {i + 1}/{len(pools)}:")
                print(pools[i])

            if len(pools) > display_count:
                print(f"\n... and {len(pools) - display_count} more pools")
        else:
            print("No pools found")


def cache_info_cli():
    """Display information about the dexmetadata cache."""
    cache = get_default_cache(persist=True)  # Enable persistence to see persisted data

    try:
        stats = cache.get_stats()

        # Get cache directory information
        cache_dir = cache.cache_dir
        cache_dir_exists = Path(cache_dir).exists()

        # Calculate directory size for diskcache
        total_size = 0
        if cache_dir_exists:
            for dirpath, dirnames, filenames in os.walk(cache_dir):
                for filename in filenames:
                    file_path = os.path.join(dirpath, filename)
                    total_size += os.path.getsize(file_path)

        print("\n=== DexMetadata Cache Information ===")
        print(f"Cache Directory: {cache_dir}")
        print(f"Directory Exists: {'Yes' if cache_dir_exists else 'No'}")
        print(f"Total Cache Size: {format_size(total_size)}")
        print(f"Persistence Enabled: {'Yes' if stats['persist_enabled'] else 'No'}")
        print("\n--- Cache Statistics ---")
        print(f"Entries: {stats['entries']:,}")
        print(f"Maximum Entries: {stats['max_entries']:,}")
        print(f"Usage: {stats['usage_percent']:.1f}%")
        print(f"Approximate Size: {format_size(stats['approx_size_mb'] * 1024 * 1024)}")

        # Show hit/miss statistics if available
        if "hits" in stats and "misses" in stats:
            print(f"Cache Hits: {stats['hits']:,}")
            print(f"Cache Misses: {stats['misses']:,}")
            print(f"Hit Rate: {stats.get('hit_rate', 0):.1f}%")

    except Exception as e:
        print(f"\nError getting cache information: {e}")
        print("This might happen if the cache hasn't been initialized yet.")


def cache_clear_cli():
    """Clear the cache entirely."""
    try:
        cache = get_default_cache(
            persist=True
        )  # Enable persistence to clear persisted data
        entries_before = len(cache)
        cache.clear()
        print(f"Cache cleared successfully. Removed {entries_before:,} entries.")
    except Exception as e:
        print(f"Error clearing cache: {e}")


def optimize_cli(
    rpc_url: str,
    rate_limit: Optional[float] = None,
    is_per_second: bool = False,
    batch_size: Optional[int] = None,
    concurrency: Optional[int] = None,
) -> None:
    """Find optimal parameters for fetching pool metadata."""
    asyncio.run(optimize(rpc_url, rate_limit, is_per_second, batch_size, concurrency))


def setup_fetch_parser(subparsers):
    """Set up the parser for the fetch command."""
    parser = subparsers.add_parser(
        "fetch",
        help="Fetch metadata for DEX pools",
        description="Fetch token metadata for DEX pools using deployless multicall",
    )

    parser.add_argument(
        "pool_identifiers",
        nargs="+",
        help="Pool contract addresses or Uniswap v4 poolIds",
    )

    parser.add_argument(
        "--rpc-url",
        help="RPC URL to connect to (defaults to publicnode.com RPC)",
    )

    parser.add_argument(
        "--network",
        default="base",
        help="Network name to use with publicnode.com RPC if rpc-url is not provided",
    )

    parser.add_argument(
        "--chain-id",
        type=int,
        help="Chain ID for the network (required for Uniswap v4 pools)",
    )

    parser.add_argument(
        "--batch-size",
        type=int,
        default=30,
        help="Maximum number of identifiers to process in a single call",
    )

    parser.add_argument(
        "--max-concurrent",
        type=int,
        default=25,
        help="Maximum number of batches to process concurrently",
    )

    parser.add_argument(
        "--format",
        choices=["dict", "json"],
        default="json",
        help="Output format (default: json)",
    )

    parser.add_argument(
        "--no-progress",
        action="store_true",
        help="Disable progress bar",
    )

    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="Disable caching",
    )

    # Add output file options
    parser.add_argument(
        "--output",
        "-o",
        dest="output_file",
        help="Output file path (format auto-detected from extension: .json, .csv)",
    )

    parser.add_argument(
        "--output-format",
        choices=["text", "json", "csv"],
        help="Output format (text, json, csv). If not specified, format is auto-detected from output file extension",
    )

    parser.add_argument(
        "--no-cache-persist",
        action="store_true",
        help="Disable cache persistence to disk",
    )

    return parser


def setup_coverage_parser(subparsers):
    """Set up the parser for the coverage command."""
    parser = subparsers.add_parser(
        "coverage",
        help="Analyze DEX pool metadata coverage",
        description="Analyze coverage of DEX pool metadata across chains and protocols",
    )

    parser.add_argument(
        "--csv-path",
        type=Path,
        help="Path to swap sample CSV file (defaults to last_month_swap_sample.csv)",
    )

    parser.add_argument(
        "--rpc-url",
        nargs=2,
        metavar=("CHAIN", "URL"),
        action="append",
        help="Custom RPC URL for a chain (can be specified multiple times)",
    )

    parser.add_argument(
        "--no-progress",
        action="store_true",
        help="Disable progress display",
    )

    return parser


def setup_optimize_parser(subparsers):
    """Set up the parser for the optimize command."""
    parser = subparsers.add_parser(
        "optimize", help="Find optimal parameters for fetching pool metadata"
    )

    parser.add_argument(
        "--rpc-url",
        type=str,
        default="https://base-rpc.publicnode.com",
        help="RPC URL to test (default: https://base-rpc.publicnode.com)",
    )

    parser.add_argument(
        "--rpm",
        type=float,
        help="Rate limit in requests per minute",
    )

    parser.add_argument(
        "--rps",
        type=float,
        help="Rate limit in requests per second",
    )

    parser.add_argument(
        "--batch-size",
        type=int,
        help="Specify a batch size instead of testing",
    )

    parser.add_argument(
        "--concurrency",
        type=int,
        help="Force specific concurrency value (override calculated value)",
    )

    return parser


def handle_fetch(args):
    """Handle the fetch command."""
    return fetch_cli(
        pool_addresses=args.pool_identifiers,
        network=args.network,
        rpc_url=args.rpc_url,
        batch_size=args.batch_size,
        max_concurrent_batches=args.max_concurrent,
        show_progress=not args.no_progress,
        output_file=args.output_file,
        output_format=args.output_format,
        use_cache=not args.no_cache,
        cache_persist=not getattr(args, "no_cache_persist", False),
    )


def handle_coverage(args):
    """Handle the coverage command."""
    # Process custom RPC URLs if provided
    rpc_urls = DEFAULT_RPC_URLS.copy()
    if args.rpc_url:
        for chain, url in args.rpc_url:
            rpc_urls[chain] = url

    # Check if CSV file exists first if specified
    if args.csv_path and not args.csv_path.exists():
        print(f"\n[ERROR] CSV file not found: {args.csv_path}")
        print("\nPlease download the sample data with:")
        print(
            "spice https://dune.com/queries/4866741/8059379/ --csv && \\\n"
            'mv "$(ls -t dune__4866741__*.csv | head -1)" last_month_swap_sample.csv'
        )
        return 1

    try:
        # Run coverage analysis
        analyze_coverage_sync(
            csv_path=args.csv_path,
            rpc_urls=rpc_urls,
            show_progress=not args.no_progress,
        )
        return 0
    except FileNotFoundError as e:
        print(f"\n[ERROR] {str(e)}")
        return 1
    except Exception as e:
        import traceback

        print(f"\n[ERROR] An error occurred during coverage analysis: {str(e)}")
        print(traceback.format_exc())
        return 1


def handle_optimize(args):
    """Handle the optimize command."""
    return optimize_cli(
        rpc_url=args.rpc_url,
        rate_limit=args.rpm if args.rpm else args.rps,
        is_per_second=bool(args.rps),
        batch_size=args.batch_size,
        concurrency=args.concurrency,
    )


def main():
    """Main entry point for the CLI."""
    parser = argparse.ArgumentParser(
        description="DEX metadata tools",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    # Set up subparsers
    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # Set up command parsers
    fetch_parser = setup_fetch_parser(subparsers)
    coverage_parser = setup_coverage_parser(subparsers)
    optimize_parser = setup_optimize_parser(subparsers)

    # Add cache commands
    subparsers.add_parser("cache-info", help="Show cache information")
    subparsers.add_parser("cache-clear", help="Clear the cache")

    # Parse arguments
    args = parser.parse_args()

    # Handle commands
    if args.command == "fetch":
        return handle_fetch(args)
    elif args.command == "coverage":
        return handle_coverage(args)
    elif args.command == "optimize":
        return handle_optimize(args)
    elif args.command == "cache-info":
        return cache_info_cli()
    elif args.command == "cache-clear":
        cache_clear_cli()
        return 0
    else:
        parser.print_help()
        return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
