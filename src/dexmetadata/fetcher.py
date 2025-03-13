"""
Module for fetching metadata about DEX pools across different chains.

This module implements a deployless multicall approach to fetch token metadata
from DEX pools in a single blockchain request, without requiring any deployed
contracts.
"""

import asyncio
import logging
import sys
from typing import Any, Dict, List, Optional

from eth_abi import decode, encode
from rich.console import Console
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
)
from web3 import Web3
from web3.main import AsyncWeb3

from .bytecode import POOL_dexmetadata_BYTECODE
from .decoder import POOL_METADATA_RESULT_TYPE

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

# Global connection pool for Web3 providers
_web3_providers = {}
_connection_semaphore = asyncio.Semaphore(10)  # Limit concurrent connections
console = Console()


def fetch(
    pool_addresses: List[str],
    rpc_url: str = None,
    network: str = "base",
    batch_size: int = 30,
    show_progress: bool = True,
    max_concurrent_batches: int = 25,
) -> List[Dict[str, Any]]:
    """
    Fetch metadata for DEX pools using deployless multicall with batching.

    Args:
        pool_addresses: List of pool contract addresses
        rpc_url: RPC URL to connect to (defaults to Ankr's Base RPC)
        network: Network name to use with Ankr's RPC if rpc_url is not provided
        batch_size: Maximum number of addresses to process in a single call
        show_progress: Whether to show a progress bar (default: True)

    Returns:
        List of dictionaries containing metadata for each pool:
        [
            {
                'pool_address': '0x...',
                'token0_address': '0x...',
                'token0_name': 'Token A',
                'token0_symbol': 'TKA',
                'token0_decimals': 18,
                'token1_address': '0x...',
                'token1_name': 'Token B',
                'token1_symbol': 'TKB',
                'token1_decimals': 6,
            },
            ...
        ]
    """
    try:
        # Check if we're already in an event loop
        loop = asyncio.get_running_loop()
        # We're in an async context, create a new loop in a thread
        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor() as pool:
            future = pool.submit(
                asyncio.run,
                fetch_async(
                    pool_addresses=pool_addresses,
                    rpc_url=rpc_url,
                    network=network,
                    batch_size=batch_size,
                    show_progress=show_progress,
                    max_concurrent_batches=max_concurrent_batches,
                ),
            )
            return future.result()
    except RuntimeError:
        # No running event loop, create a new one
        return asyncio.run(
            fetch_async(
                pool_addresses=pool_addresses,
                rpc_url=rpc_url,
                network=network,
                batch_size=batch_size,
                show_progress=show_progress,
                max_concurrent_batches=max_concurrent_batches,
            )
        )


async def fetch_async(
    pool_addresses: List[str],
    rpc_url: str,
    network: str,
    batch_size: int,
    max_concurrent_batches: int,
    show_progress: bool,
) -> List[Dict[str, Any]]:
    """
    Asynchronously fetch metadata for DEX pools using deployless multicall with batching.

    Args:
        pool_addresses: List of pool contract addresses
        rpc_url: RPC URL to connect to (defaults to Ankr's Base RPC)
        network: Network name to use with Ankr's RPC if rpc_url is not provided
        batch_size: Maximum number of addresses to process in a single call (default: 120)
        max_concurrent_batches: Maximum number of batches to process concurrently (default: 5)
        show_progress: Whether to show a progress bar (default: True)

    Returns:
        List of dictionaries containing metadata for each pool
    """
    if rpc_url is None and network is not None:
        rpc_url = f"https://rpc.ankr.com/{network}"

    # Get or create an async Web3 provider
    web3_provider = await get_web3_provider(rpc_url)

    # Handle empty input
    if not pool_addresses:
        logger.debug("No pool addresses provided")
        return []

    # Filter and validate addresses
    valid_addresses = []

    # Validate addresses without progress bar
    for addr in pool_addresses:
        try:
            if Web3.is_address(addr):  # Static method that doesn't need a provider
                valid_addresses.append(Web3.to_checksum_address(addr))
            else:
                logger.warning(f"Invalid address format: {addr}")
        except Exception as e:
            logger.warning(f"Error validating address {addr}: {e}")

    # If no valid addresses after filtering, return empty list
    if not valid_addresses:
        logger.debug("No valid addresses found after filtering")
        return []

    # Split addresses into batches
    batches = []
    for i in range(0, len(valid_addresses), batch_size):
        batches.append(valid_addresses[i : i + batch_size])

    # Initialize progress display
    fetch_progress = None
    if show_progress:
        fetch_progress = Progress(
            SpinnerColumn(),
            TextColumn("[bold green]Fetching pool metadata..."),
            BarColumn(),
            MofNCompleteColumn(),
            TimeElapsedColumn(),
        )
        total_pools = len(valid_addresses)
        task_id = fetch_progress.add_task("Fetching", total=total_pools)
        fetch_progress.start()

    # Create a semaphore to limit concurrent batches
    batch_semaphore = asyncio.Semaphore(max_concurrent_batches)

    completed_pools = 0
    total_batches = len(batches)

    # Define the task for processing a batch
    async def process_batch(
        batch_index: int, batch_addresses: List[str]
    ) -> List[Dict[str, Any]]:
        nonlocal completed_pools

        async with batch_semaphore:
            batch_desc = f"Batch {batch_index + 1}/{total_batches}"
            logger.debug(
                f"Processing {batch_desc} with {len(batch_addresses)} addresses"
            )

            try:
                # Encode constructor arguments with batch addresses
                constructor_args = encode(["address[]"], [batch_addresses])
                data = POOL_dexmetadata_BYTECODE + constructor_args.hex().replace(
                    "0x", ""
                )

                # Make the call (no 'to' field for deployless execution)
                async with _connection_semaphore:
                    result = await web3_provider.eth.call({"data": data})

                # Handle empty response
                if not result:
                    logger.warning(f"Empty response from eth_call for {batch_desc}")
                    if fetch_progress:
                        fetch_progress.update(task_id, advance=len(batch_addresses))
                    completed_pools += len(batch_addresses)
                    return []

                # Decode the response
                decoded_pools = decode([POOL_METADATA_RESULT_TYPE], result)[0]
                batch_results = [
                    {
                        "pool_address": pool[0],
                        "token0_address": pool[1][0],
                        "token0_name": pool[1][1],
                        "token0_symbol": pool[1][2],
                        "token0_decimals": pool[1][3],
                        "token1_address": pool[2][0],
                        "token1_name": pool[2][1],
                        "token1_symbol": pool[2][2],
                        "token1_decimals": pool[2][3],
                    }
                    for pool in decoded_pools
                ]

                logger.debug(
                    f"Successfully processed {batch_desc} with {len(batch_results)} results"
                )

                # Update progress based on number of pools in this batch
                if fetch_progress:
                    fetch_progress.update(task_id, advance=len(batch_addresses))
                completed_pools += len(batch_addresses)

                return batch_results

            except Exception as e:
                logger.error(f"Error fetching pool metadata for {batch_desc}: {e}")
                # Update progress even on error
                if fetch_progress:
                    fetch_progress.update(task_id, advance=len(batch_addresses))
                completed_pools += len(batch_addresses)
                return []  # Return empty list for failed batch

    # Create and run tasks for all batches
    tasks = [process_batch(i, batch) for i, batch in enumerate(batches)]
    batch_results = await asyncio.gather(*tasks)

    # Stop progress display
    if fetch_progress:
        fetch_progress.stop()

    # Flatten the results
    all_results = [result for batch in batch_results for result in batch]

    # Show summary
    if show_progress:
        if len(all_results) > 0:
            console.print(
                f"[green]✓[/green] Fetched metadata for {len(all_results)} pools"
            )
        else:
            console.print("[yellow]⚠[/yellow] No pool metadata found")

    logger.debug(f"Finished processing all batches. Total results: {len(all_results)}")
    return all_results


async def get_web3_provider(rpc_url: str) -> AsyncWeb3:
    """
    Get or create an async Web3 provider for the given RPC URL.
    Uses a connection pool to avoid creating too many connections.

    Args:
        rpc_url: The RPC URL to connect to

    Returns:
        An AsyncWeb3 instance
    """
    # Check if we already have a provider for this URL
    if rpc_url in _web3_providers:
        return _web3_providers[rpc_url]

    # Create a new provider
    async_provider = AsyncWeb3.AsyncHTTPProvider(rpc_url)
    web3 = AsyncWeb3(async_provider)

    # Store in the pool
    _web3_providers[rpc_url] = web3

    return web3


def calculate_rate_limit_params(
    rate_limit: float,
    avg_response_time: float = 0.7,
    target_utilization: float = 0.5,  # More conservative default
    is_per_second: bool = False,
) -> dict:
    """
    Calculate optimal batch_size and max_concurrent_batches based on RPC rate limits.

    Args:
        rate_limit: Maximum requests per minute (or per second if is_per_second=True)
        avg_response_time: Average response time in seconds (default: 0.7s)
        target_utilization: Target utilization of rate limit (default: 0.5 or 50%)
        is_per_second: Whether rate_limit is per second (True) or per minute (False)

    Returns:
        Dictionary with recommended parameters and utilization information
    """
    # Convert to requests per minute if needed
    rate_limit_rpm = rate_limit * 60 if is_per_second else rate_limit

    # Calculate max concurrent requests to stay within rate limit
    safe_rpm = rate_limit_rpm * target_utilization
    max_concurrent = int(safe_rpm * avg_response_time / 60)

    # Cap max concurrent and ensure at least 1
    max_concurrent = max(1, min(max_concurrent, 5))  # Cap at 5 for stability

    # Determine batch size based on concurrency
    if max_concurrent >= 4:
        batch_size = 10
    elif max_concurrent >= 2:
        batch_size = 20
    else:
        batch_size = 30

    # Calculate estimated requests per minute
    estimated_rpm = (60 / avg_response_time) * max_concurrent

    return {
        "batch_size": batch_size,
        "max_concurrent_batches": max_concurrent,
        "estimated_rpm": round(estimated_rpm, 1),
        "rate_limit_rpm": rate_limit_rpm,
        "utilization": round(estimated_rpm / rate_limit_rpm * 100, 1),
    }
