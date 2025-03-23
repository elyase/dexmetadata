"""
DEX metadata coverage analysis.

This module provides tools for analyzing DEX pool metadata coverage
across different chains and protocols, based on a sample of real-world swap data.
"""

import asyncio
import csv
import logging
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from rich.console import Console
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TaskProgressColumn,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
)
from rich.table import Table

from dexmetadata import fetch

logger = logging.getLogger(__name__)
console = Console()

# Default RPC URLs for testing - can be overridden
DEFAULT_RPC_URLS = {
    "base": "https://base-rpc.publicnode.com",
    "ethereum": "https://ethereum-rpc.publicnode.com",
    "optimism": "https://optimism-rpc.publicnode.com",
    "arbitrum": "https://arbitrum-rpc.publicnode.com",
    "polygon": "https://polygon-rpc.publicnode.com",
    "blast": "https://blast-rpc.publicnode.com",
    "zora": "https://rpc.zora.energy",
    "avalanche_c": "https://avalanche-rpc.publicnode.com",
    "bnb": "https://bsc-rpc.publicnode.com",
    "linea": "https://linea-rpc.publicnode.com",
    "zkevm": "https://polygon-zkevm-rpc.publicnode.com",
    "zksync": "https://zksync-rpc.publicnode.com",
    "scroll": "https://scroll-rpc.publicnode.com",
    "mantle": "https://mantle-rpc.publicnode.com",
    "nova": "https://nova-rpc.publicnode.com",
    "fantom": "https://fantom-rpc.publicnode.com",
    "gnosis": "https://gnosis-rpc.publicnode.com",
}


class SwapSample:
    """Container for swap sample data and analytics."""

    def __init__(self, csv_path: Optional[Path] = None):
        self.pools_by_chain = defaultdict(set)
        self.pools_by_protocol = defaultdict(set)
        self.protocol_by_pool = {}
        self.protocol_popularity = defaultdict(int)
        self.chain_popularity = defaultdict(int)
        self.swaps_by_chain_protocol = defaultdict(lambda: defaultdict(int))
        self.total_swaps = 0
        self.total_swaps_by_chain = defaultdict(int)

        if csv_path:
            self.load_csv(csv_path)

    def load_csv(self, csv_path: Path):
        """Load swap sample data from CSV."""
        if not csv_path.exists():
            raise FileNotFoundError(f"CSV file not found: {csv_path}")

        with open(csv_path) as f:
            reader = csv.DictReader(f)
            for row in reader:
                self.total_swaps += 1

                # Extract chain and protocol from dex identifier
                parts = row["dex"].split("__")
                if len(parts) < 2:
                    continue

                chain = parts[0]
                protocol = "__".join(parts[1:])  # Keep full protocol identifier

                # Add pool to collections
                pool_id = row["pool_id"]
                self.pools_by_chain[chain].add(pool_id)
                self.pools_by_protocol[protocol].add(pool_id)
                self.protocol_by_pool[pool_id] = protocol

                # Get volume if available
                volume = 0
                if "percentage" in row:
                    try:
                        volume = float(row["percentage"])
                    except (ValueError, TypeError):
                        pass

                # Track swaps per chain and protocol
                self.swaps_by_chain_protocol[chain][protocol] += 1
                self.total_swaps_by_chain[chain] += 1

                # Update protocol and chain popularity with volume
                self.protocol_popularity[protocol] += volume
                self.chain_popularity[chain] += volume

            # Log stats
            logger.info(f"Loaded {self.total_swaps} swaps from {csv_path}")
            logger.info(f"Found chains: {list(self.pools_by_chain.keys())}")
            logger.info(f"Number of chains: {len(self.pools_by_chain)}")
            logger.info(f"Number of protocols: {len(self.pools_by_protocol)}")

    def get_unique_pools(self) -> Dict[str, Set[str]]:
        """Get unique pools by chain."""
        return {chain: pools.copy() for chain, pools in self.pools_by_chain.items()}


async def analyze_coverage(
    sample: SwapSample,
    rpc_urls: Optional[Dict[str, str]] = None,
    limit_pools_per_protocol: int = 1,
    show_progress: bool = True,
) -> Dict:
    """
    Analyze DEX pool metadata coverage.

    Args:
        sample: Swap sample data
        rpc_urls: RPC URLs for each chain (defaults to public nodes)
        limit_pools_per_protocol: Limit pools per protocol (default: 1)
        show_progress: Whether to show progress bars

    Returns:
        Analysis results
    """
    # Use default RPC URLs if none provided
    if rpc_urls is None:
        rpc_urls = DEFAULT_RPC_URLS

    # Prepare data structures for results
    chain_results = {}
    protocol_results = defaultdict(lambda: {"total": 0, "found": 0, "valid": 0})
    failed_by_protocol = defaultdict(list)

    # Track coverage for swap-based metrics
    swap_coverage_by_chain = defaultdict(int)
    total_swaps_by_chain = defaultdict(int)

    # Filter chains by available RPC URLs
    available_chains = {
        chain: pools
        for chain, pools in sample.get_unique_pools().items()
        if chain in rpc_urls
    }

    # Limit pools per protocol - select representative pools
    limited_chains = {}
    for chain, pool_ids in available_chains.items():
        # Group pools by protocol
        protocol_pools = defaultdict(list)
        for pool_id in pool_ids:
            if pool_id in sample.protocol_by_pool:
                protocol = sample.protocol_by_pool[pool_id]
                protocol_pools[protocol].append(pool_id)

        # Select pools to test
        limited_chains[chain] = []
        for protocol, pools in protocol_pools.items():
            limited_chains[chain].extend(pools[:limit_pools_per_protocol])

    # Process each chain
    with Progress(
        SpinnerColumn(),
        TextColumn("[bold blue]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        TimeElapsedColumn(),
        TimeRemainingColumn(),
        console=console,
        disable=not show_progress,
    ) as progress:
        # Set up progress tracking
        overall_task = progress.add_task(
            f"[green]Analyzing {len(limited_chains)} chains...",
            total=len(limited_chains),
        )

        chain_tasks = {}
        for chain, pool_ids in limited_chains.items():
            chain_tasks[chain] = progress.add_task(
                f"[cyan]{chain}[/cyan] ({len(pool_ids)} dexes)", total=len(pool_ids)
            )

        # Define helper function to process each chain
        async def process_chain(chain, pool_ids, chain_task_id):
            rpc_url = rpc_urls[chain]

            # Use smaller batch size for Ethereum to avoid out-of-gas errors
            batch_size = 15 if "ethereum" in rpc_url.lower() else 30
            if "ethereum" in rpc_url.lower():
                logger.info(
                    f"Using reduced batch size ({batch_size}) for {chain} to prevent 'out of gas' errors"
                )

            # Fetch metadata with explicit cache settings
            try:
                logger.info(
                    f"Fetching {len(pool_ids)} pools for {chain} with batch size {batch_size}"
                )
                logger.info(f"Cache is enabled: use_cache=True")

                # Get cache stats before fetch
                from .cache import get_default_cache

                cache = get_default_cache(persist=True)
                logger.info(f"Cache entries before fetch: {len(cache)}")

                # Fetch with cache enabled
                pools = fetch(
                    pool_ids,
                    rpc_url=rpc_url,
                    batch_size=batch_size,
                    max_concurrent_batches=25,
                    show_progress=False,
                    use_cache=True,
                    cache_persist=True,  # Ensure persistence is enabled
                    format="dict",
                )

                # Check cache after fetch
                logger.info(f"Cache entries after fetch: {len(cache)}")

                # Count results
                total = len(pool_ids)
                found = sum(p is not None for p in pools)

                # Validate pools
                def is_valid(p):
                    return p is not None and (
                        ("is_valid" in p and p["is_valid"]) or "is_valid" not in p
                    )

                valid = sum(is_valid(p) for p in pools)

                # Identify failed pools
                failed_pools = [
                    pool_id
                    for pool_id, pool in zip(pool_ids, pools)
                    if not is_valid(pool)
                ]

                # Update progress
                progress.update(chain_task_id, completed=total)

                return {
                    "chain": chain,
                    "total": total,
                    "found": found,
                    "valid": valid,
                    "failed_pools": failed_pools,
                }

            except Exception as e:
                logger.error(f"Error analyzing {chain}: {e}")
                progress.update(chain_task_id, completed=len(pool_ids))
                return {
                    "chain": chain,
                    "total": len(pool_ids),
                    "found": 0,
                    "valid": 0,
                    "failed_pools": pool_ids,
                }

        # Process chains sequentially
        results = {}
        for chain, pool_ids in limited_chains.items():
            rpc_url = rpc_urls[chain]

            # Use smaller batch size for Ethereum to avoid out-of-gas errors
            batch_size = 15 if "ethereum" in rpc_url.lower() else 30
            if "ethereum" in rpc_url.lower():
                logger.info(
                    f"Using reduced batch size ({batch_size}) for {chain} to prevent 'out of gas' errors"
                )

            # Fetch metadata with explicit cache settings
            try:
                logger.info(
                    f"Fetching {len(pool_ids)} pools for {chain} with batch size {batch_size}"
                )
                logger.info(f"Cache is enabled: use_cache=True")

                # Get cache stats before fetch
                from .cache import get_default_cache

                cache = get_default_cache(persist=True)
                logger.info(f"Cache entries before fetch: {len(cache)}")

                # Fetch with cache enabled
                pools = fetch(
                    pool_ids,
                    rpc_url=rpc_url,
                    batch_size=batch_size,
                    max_concurrent_batches=25,
                    show_progress=False,
                    use_cache=True,
                    cache_persist=True,  # Ensure persistence is enabled
                    format="dict",
                )

                # Check cache after fetch
                logger.info(f"Cache entries after fetch: {len(cache)}")

                # Count results
                total = len(pool_ids)
                found = sum(p is not None for p in pools)

                # Validate pools
                def is_valid(p):
                    return p is not None and (
                        ("is_valid" in p and p["is_valid"]) or "is_valid" not in p
                    )

                valid = sum(is_valid(p) for p in pools)

                # Identify failed pools
                failed_pools = [
                    pool_id
                    for pool_id, pool in zip(pool_ids, pools)
                    if not is_valid(pool)
                ]

                # Store results
                results[chain] = {
                    "total": total,
                    "found": found,
                    "valid": valid,
                    "failed_pools": failed_pools,
                }

                # Update progress
                progress.update(chain_tasks[chain], completed=total)

            except Exception as e:
                logger.error(f"Error analyzing {chain}: {e}")
                results[chain] = {
                    "total": len(pool_ids),
                    "found": 0,
                    "valid": 0,
                    "failed_pools": pool_ids,
                }

            progress.update(overall_task, advance=1)

    # Process results by chain
    for chain, result in results.items():
        # Remove 'chain' key from result if it exists (we're already using the chain key from the dictionary)
        if "chain" in result:
            del result["chain"]

        total, found, valid, failed_pools = (
            result["total"],
            result["found"],
            result["valid"],
            result["failed_pools"],
        )
        chain_swap_total = sample.total_swaps_by_chain.get(chain, 0)

        # Map pools to protocols for reporting
        failed_protocols = defaultdict(list)
        for pool_id in failed_pools:
            if pool_id in sample.protocol_by_pool:
                protocol = sample.protocol_by_pool[pool_id]
                failed_protocols[protocol].append(pool_id)

        # Log summary of failed pools
        if failed_protocols:
            logger.info(f"Failed pools on {chain} by protocol:")
            for protocol, pools in failed_protocols.items():
                if protocol in sample.swaps_by_chain_protocol[chain]:
                    swaps = sample.swaps_by_chain_protocol[chain][protocol]
                    swaps_pct = (
                        swaps / chain_swap_total * 100 if chain_swap_total > 0 else 0
                    )
                    logger.info(
                        f"  {protocol}: {len(pools)} pools failed ({swaps_pct:.1f}% of chain's swaps)"
                    )

        # Calculate swap coverage
        swap_coverage = 0.0

        # For each protocol on this chain, calculate how many swaps would be covered
        for protocol, swap_count in sample.swaps_by_chain_protocol[chain].items():
            # Check if this protocol is valid
            protocol_valid = False
            protocol_is_major = swap_count > 0.05 * chain_swap_total

            # Check available pools for this protocol
            for pool_id in limited_chains.get(chain, []):
                if (
                    sample.protocol_by_pool.get(pool_id) == protocol
                    and pool_id not in failed_pools
                ):
                    protocol_valid = True
                    break

            # Log diagnostic info for major failed protocols
            if not protocol_valid and protocol_is_major:
                logger.warning(
                    f"Major protocol {protocol} on {chain} failed validation"
                )
                logger.warning(
                    f"  - Protocol accounts for {swap_count}/{chain_swap_total} swaps ({swap_count / chain_swap_total * 100:.1f}%)"
                )

            # If protocol is valid, add its swaps to the coverage count
            if protocol_valid:
                swap_coverage += swap_count

        # Calculate coverage percentages
        swap_coverage_pct = (
            swap_coverage / chain_swap_total * 100 if chain_swap_total > 0 else 0
        )
        found_pct = found / total * 100 if total else 0
        valid_pct = valid / total * 100 if total else 0

        # Store chain results
        chain_results[chain] = {
            "total": total,
            "found": found,
            "valid": valid,
            "found_pct": found_pct,
            "valid_pct": valid_pct,
            "swap_coverage_pct": swap_coverage_pct,
        }

        # Track for overall stats
        swap_coverage_by_chain[chain] = swap_coverage
        total_swaps_by_chain[chain] = chain_swap_total

        # Track protocols for failed pools
        for pool_id in failed_pools:
            if pool_id in sample.protocol_by_pool:
                protocol = sample.protocol_by_pool[pool_id]
                failed_by_protocol[protocol].append(pool_id)

    # Calculate protocol coverage
    for chain, pool_ids in limited_chains.items():
        counted_protocols = set()
        for pool_id in pool_ids:
            if pool_id in sample.protocol_by_pool:
                protocol = sample.protocol_by_pool[pool_id]
                if protocol not in counted_protocols:
                    protocol_results[protocol]["total"] += 1
                    counted_protocols.add(protocol)

                # Valid pools count towards protocol success
                if pool_id not in failed_by_protocol[protocol]:
                    protocol_results[protocol]["found"] += 1
                    protocol_results[protocol]["valid"] += 1

    # Calculate percentages for protocols
    for protocol, results in protocol_results.items():
        total = results["total"]
        if total > 0:
            results["found_pct"] = results["found"] / total * 100
            results["valid_pct"] = results["valid"] / total * 100

    # Calculate overall statistics
    total_pools = sum(r["total"] for r in chain_results.values())
    total_found = sum(r["found"] for r in chain_results.values())
    total_valid = sum(r["valid"] for r in chain_results.values())

    total_swaps = sum(total_swaps_by_chain.values())
    covered_swaps = sum(swap_coverage_by_chain.values())
    overall_swap_coverage_pct = (
        covered_swaps / total_swaps * 100 if total_swaps > 0 else 0
    )

    overall = {
        "total_pools": total_pools,
        "found_pools": total_found,
        "valid_pools": total_valid,
        "found_pct": total_found / total_pools * 100 if total_pools else 0,
        "valid_pct": total_valid / total_pools * 100 if total_pools else 0,
        "total_swaps": total_swaps,
        "covered_swaps": covered_swaps,
        "swap_coverage_pct": overall_swap_coverage_pct,
    }

    return {
        "overall": overall,
        "chain_results": chain_results,
        "protocol_results": protocol_results,
    }


def display_chain_coverage(results: Dict) -> None:
    """Display chain coverage in a Rich table."""
    chain_results = results["chain_results"]
    overall = results["overall"]

    # Create table
    table = Table(title="DEX Metadata Coverage by Chain")
    table.add_column("Chain", style="cyan")
    table.add_column("Swap Coverage %", justify="right")
    table.add_column("Pools", justify="right")

    # Sort by swap coverage percentage
    sorted_chains = sorted(
        chain_results.items(), key=lambda x: x[1]["swap_coverage_pct"], reverse=True
    )

    # Add rows
    for chain, data in sorted_chains:
        table.add_row(
            chain,
            f"{data['swap_coverage_pct']:.1f}%",
            f"{data['valid']}/{data['total']}",
        )

    # Add overall row
    table.add_row(
        "OVERALL",
        f"{overall['swap_coverage_pct']:.1f}%",
        f"{overall['valid_pct']:.1f}%",
        style="bold",
    )

    # Print table
    console.print(table)


def display_protocol_coverage(
    results: Dict, sample: SwapSample, chains: List[str]
) -> None:
    """Display protocol failure rates by chain."""
    # Create table
    table = Table(title="Failure Rates by Protocol Grouped by Chain")
    table.add_column("Protocol", style="cyan")
    table.add_column("Chain", style="blue")
    table.add_column("Failure Rate", justify="right")

    # Calculate failure rates
    failure_rates = []

    for chain in chains:
        for protocol in sample.swaps_by_chain_protocol[chain]:
            # Protocol is valid if it has successful results
            protocol_valid = (
                protocol in results["protocol_results"]
                and results["protocol_results"][protocol]["valid"] > 0
            )

            # Calculate failure rate as percentage of chain's total swaps
            protocol_swaps = sample.swaps_by_chain_protocol[chain].get(protocol, 0)
            total_chain_swaps = sample.total_swaps_by_chain.get(chain, 0)

            if not protocol_valid and total_chain_swaps > 0:
                failure_rate = (protocol_swaps / total_chain_swaps) * 100
                failure_rates.append((protocol, chain, failure_rate))

    # Sort by chain first, then by failure rate (highest first) within each chain
    failure_rates.sort(key=lambda x: (x[1], -x[2]))

    # Add rows
    for protocol, chain, failure_rate in failure_rates:
        if failure_rate > 0:
            # Clean protocol name for display
            display_name = protocol.replace("__", "_")
            table.add_row(display_name, chain, f"{failure_rate:.1f}%")

    # Print table
    console.print(table)


async def run_coverage_analysis(
    csv_path: Optional[Path] = None,
    rpc_urls: Optional[Dict[str, str]] = None,
    show_progress: bool = True,
) -> Dict:
    """Run complete coverage analysis."""
    # Find CSV file if not provided
    if csv_path is None:
        candidates = [
            Path("last_month_swap_sample.csv"),
            Path("examples/last_month_swap_sample.csv"),
            Path(__file__).parent.parent.parent
            / "examples"
            / "last_month_swap_sample.csv",
        ]

        for path in candidates:
            if path.exists():
                csv_path = path
                break

        if csv_path is None:
            raise FileNotFoundError(
                "Swap sample CSV not found. Please download it with:"
                "\n\nspice https://dune.com/queries/4866741/8059379/ --csv && "
                'mv "$(ls -t dune__4866741__*.csv | head -1)" last_month_swap_sample.csv'
            )

    # Load sample data
    sample = SwapSample(csv_path)

    if show_progress:
        console.print(f"[bold]Analyzing DEX pool metadata coverage...[/bold]")
        console.print(f"[dim]Sample data: {csv_path.name}[/dim]")

    # Run analysis
    results = await analyze_coverage(sample, rpc_urls, show_progress=show_progress)

    # Display results
    display_chain_coverage(results)
    console.print()

    # Display protocol coverage
    chains = list(results["chain_results"].keys())
    display_protocol_coverage(results, sample, chains)

    return results


def analyze_coverage_sync(
    csv_path: Optional[Path] = None,
    rpc_urls: Optional[Dict[str, str]] = None,
    show_progress: bool = True,
) -> Dict:
    """Synchronous wrapper for coverage analysis."""
    return asyncio.run(run_coverage_analysis(csv_path, rpc_urls, show_progress))
