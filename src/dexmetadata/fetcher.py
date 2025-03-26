"""
Module for fetching metadata about DEX pools across different chains.

This module implements a deployless multicall approach to fetch token metadata
from DEX pools in a single blockchain request, without requiring any deployed
contracts.
"""

import asyncio
import logging
from typing import Any, Dict, List, Literal, NamedTuple, Optional, Set, Type, Union

from web3 import Web3
from web3.main import AsyncWeb3

from .bytecode import POOL_METADATA_BYTECODE, UNISWAP_V4_METADATA_BYTECODE
from .cache import get_default_cache
from .constants import get_chain_id_from_network
from .handlers import DefaultPoolFetcher, UniswapV4PoolFetcher, pool_handler_registry
from .models import Pool
from .progress import ProgressTracker, console
from .utils import is_valid_metadata

logger = logging.getLogger(__name__)


class PoolIdentifiers(NamedTuple):
    """Container for categorized pool identifiers."""

    regular_pools: List[str]
    uniswap_v4_pools: List[str]


class PoolResult(NamedTuple):
    """Container for pool fetch results."""

    original_id: str
    metadata: Optional[Dict[str, Any]]


class Web3Provider:
    """Web3 provider with async connection management."""

    def __init__(self, rpc_url: str):
        self.rpc_url = rpc_url
        self.provider = None

    async def __aenter__(self):
        """Initialize the provider when entering context."""
        self.provider = AsyncWeb3(AsyncWeb3.AsyncHTTPProvider(self.rpc_url))
        return self.provider

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Clean up the provider when exiting context."""
        if self.provider and hasattr(self.provider, "provider"):
            provider_obj = self.provider.provider

            # Handle different session attribute names
            if hasattr(provider_obj, "session") and provider_obj.session:
                await provider_obj.session.close()
            if hasattr(provider_obj, "_session") and provider_obj._session:
                await provider_obj._session.close()
            # Handle Web3.py 6.x style provider
            if hasattr(provider_obj, "http_session") and provider_obj.http_session:
                await provider_obj.http_session.close()


class MetadataFetcher:
    """Main class for fetching DEX pool metadata."""

    def __init__(
        self,
        pool_identifiers: List[str],
        rpc_url: str,
        chain_id: int,
        batch_size: int = 30,
        max_concurrent_batches: int = 25,
        show_progress: bool = True,
        use_cache: bool = True,
        cache_max_pools: int = 10000,
        cache_max_size_mb: Optional[float] = None,
        cache_persist: bool = True,
    ):
        self.pool_identifiers = pool_identifiers
        self.rpc_url = rpc_url
        self.chain_id = chain_id
        self.batch_size = batch_size
        self.max_concurrent_batches = max_concurrent_batches
        self.show_progress = show_progress
        self.use_cache = use_cache
        self.cache_max_pools = cache_max_pools
        self.cache_max_size_mb = cache_max_size_mb
        self.cache_persist = cache_persist

        # Initialize cache if enabled
        self.cache = None
        if use_cache:
            self.cache = get_default_cache(
                max_pools=cache_max_pools,
                max_size_mb=cache_max_size_mb,
                persist=cache_persist,
            )
            logger.info(f"Cache initialized with {len(self.cache)} entries")

    def categorize_identifiers(self) -> Dict[Type[DefaultPoolFetcher], List[str]]:
        """
        Categorize pool identifiers by handler type.
        """
        return pool_handler_registry.categorize_identifiers(self.pool_identifiers)

    def get_cached_results(
        self, normalized_identifiers: List[str]
    ) -> Dict[str, Dict[str, Any]]:
        """
        Get cached results for the pool identifiers.
        Checks both standard and chain-specific keys if chain_id is available.
        """
        if not self.use_cache or not self.cache:
            return {}

        # Always start with regular cache keys
        logger.debug("Checking standard cache keys first")
        results = self.cache.get_many(normalized_identifiers)
        
        # If chain_id is available, also check chain-specific keys
        if hasattr(self.cache, "chain_specific_key") and self.chain_id:
            chain_specific_keys = [
                self.cache.chain_specific_key(id, self.chain_id) 
                for id in normalized_identifiers
            ]
            logger.debug(f"Also checking chain-specific cache keys for chain_id {self.chain_id}")
            # Get results with chain-specific keys
            chain_results = self.cache.get_many(chain_specific_keys)
            
            # Map from chain-specific keys back to original pool IDs
            for i, pool_id in enumerate(normalized_identifiers):
                chain_key = chain_specific_keys[i]
                if chain_key in chain_results and pool_id not in results:
                    # Only add the chain result if we don't already have a result for this pool
                    results[pool_id] = chain_results[chain_key]
                    
        return results

    def update_cache(
        self, results_by_id: Dict[str, Dict[str, Any]], cached_keys: Set[str]
    ):
        """
        Update cache with new results.
        """
        if not self.use_cache or not self.cache:
            return

        new_cache_entries = {}
        for identifier, result in results_by_id.items():
            normalized_id = identifier.lower()
            
            # Use chain-specific key if available
            if hasattr(self.cache, "chain_specific_key") and self.chain_id:
                cache_key = self.cache.chain_specific_key(normalized_id, self.chain_id)
            else:
                cache_key = normalized_id
                
            # Cache all results (including invalid ones) to prevent redundant fetches
            if cache_key not in cached_keys:
                # Always set is_valid flag based on validation result
                is_valid = is_valid_metadata(result)
                result["is_valid"] = is_valid
                
                # Add chain_id to cached result for future reference
                if self.chain_id and "chain_id" not in result:
                    result["chain_id"] = self.chain_id
                
                # Log caching of invalid pools for debugging
                if not is_valid:
                    logger.warning(f"Caching invalid pool: {normalized_id} with key {cache_key}")
                    
                new_cache_entries[cache_key] = result

        if new_cache_entries:
            self.cache.put_many(new_cache_entries)
            logger.info(f"Added {len(new_cache_entries)} new entries to cache")

    async def fetch_metadata(self) -> List[Dict[str, Any]]:
        """
        Fetch metadata for all pool identifiers.
        """
        # Handle empty input
        if not self.pool_identifiers:
            return []

        # Normalize identifiers for cache lookups
        normalized_identifiers = [
            identifier.lower() for identifier in self.pool_identifiers
        ]

        # Check cache for existing results
        cached_data = self.get_cached_results(normalized_identifiers)
        logger.info(f"Cache hits: {len(cached_data)}/{len(self.pool_identifiers)}")

        # Return immediately if all data is in cache
        if len(cached_data) == len(self.pool_identifiers):
            if self.show_progress:
                console.print(
                    f"[green]✓[/green] Fetched metadata for {len(cached_data)} pools (all from cache)"
                )
            return list(cached_data.values())

        # Initialize results and track which identifiers need to be fetched
        results_by_id = {k: v for k, v in cached_data.items()}
        cached_ids = set(cached_data.keys())

        # Filter out identifiers that are already cached
        identifiers_to_fetch = [
            id for id in self.pool_identifiers if id.lower() not in cached_ids
        ]

        # Categorize remaining identifiers by handler type
        handler_to_identifiers = pool_handler_registry.categorize_identifiers(
            identifiers_to_fetch
        )

        # Count total identifiers to fetch
        total_to_fetch = sum(len(ids) for ids in handler_to_identifiers.values())

        # Initialize progress tracking
        progress_tracker = ProgressTracker(total_to_fetch, self.show_progress)

        # Show cache hit info if there are any
        if self.show_progress and len(cached_data) > 0:
            console.print(f"[green]✓[/green] Found {len(cached_data)} pools in cache")

        progress_tracker.start()

        # Create semaphore for limiting concurrent batches
        batch_semaphore = asyncio.Semaphore(self.max_concurrent_batches)

        # Use a context manager for the Web3 provider
        async with Web3Provider(self.rpc_url) as web3_provider:
            # Process each handler type
            for handler_class, identifiers in handler_to_identifiers.items():
                if not identifiers:
                    continue

                try:
                    # Create appropriate handler instance
                    if handler_class == UniswapV4PoolFetcher:
                        # UniswapV4PoolFetcher requires chain_id
                        handler = handler_class(
                            web3_provider,
                            self.batch_size,
                            batch_semaphore,
                            self.chain_id,
                            progress_tracker,
                        )
                    else:
                        # Default handler initialization
                        handler = handler_class(
                            web3_provider,
                            self.batch_size,
                            batch_semaphore,
                            progress_tracker,
                        )

                    # Process pools with this handler
                    handler_results = await handler.process_pools(identifiers)

                    # Add results to the results dictionary with appropriate key
                    for result in handler_results:
                        # Use the unified identifier field as key
                        key = result.get("identifier", "").lower()

                        if key:
                            results_by_id[key] = result

                except Exception as e:
                    logger.error(
                        f"Error processing {handler_class.PROTOCOL_NAME} pools: {e}"
                    )
                    # Update progress tracker to account for failed identifiers
                    if progress_tracker:
                        progress_tracker.update(len(identifiers))

        # Stop progress tracking
        progress_tracker.stop()

        # Update cache with new entries
        self.update_cache(results_by_id, cached_ids)

        # Build final results in original order
        ordered_results = []
        normalized_results = {k.lower(): v for k, v in results_by_id.items()}

        for identifier in self.pool_identifiers:
            if identifier in results_by_id:
                ordered_results.append(results_by_id[identifier])
            elif identifier.lower() in normalized_results:
                ordered_results.append(normalized_results[identifier.lower()])
            else:
                logger.warning(f"Pool {identifier} not found in results")

        # Show summary
        if self.show_progress:
            if ordered_results:
                cache_msg = (
                    f" ({len(cached_data)} from cache)"
                    if self.use_cache and cached_data
                    else ""
                )
                console.print(
                    f"[green]✓[/green] Fetched metadata for {len(ordered_results)} pools{cache_msg}"
                )
            else:
                console.print("[yellow]⚠[/yellow] No pool metadata found")

        return ordered_results


def fetch(
    pool_identifiers: List[str],
    rpc_url: str = None,
    network: str = "base",
    chain_id: Optional[int] = None,
    batch_size: int = 30,
    show_progress: bool = True,
    max_concurrent_batches: int = 25,
    format: Literal["dict", "object"] = "object",
    use_cache: bool = True,
    cache_max_pools: int = 10000,
    cache_max_size_mb: Optional[float] = None,
    cache_persist: bool = True,
) -> List[Union[Dict[str, Any], Pool]]:
    """
    Fetch metadata for DEX pools using deployless multicall with batching.
    Supports both regular pool addresses and Uniswap v4 poolIds.

    Args:
        pool_identifiers: List of pool contract addresses or Uniswap v4 poolIds (bytes32 hex strings)
        rpc_url: RPC URL to connect to (defaults to publicnode.com RPC)
        network: Network name to use with publicnode.com RPC if rpc_url is not provided
        chain_id: Chain ID for the network (required for Uniswap v4 pools)
        batch_size: Maximum number of identifiers to process in a single call
        show_progress: Whether to show a progress bar (default: True)
        max_concurrent_batches: Maximum number of batches to process concurrently (default: 25)
        format: Output format - either "dict" or "object" (default: "object")
        use_cache: Whether to use cache (default: True)
        cache_max_pools: Maximum number of pools to cache (default: 10000)
        cache_max_size_mb: Maximum cache size in MB (overrides cache_max_pools if provided)
        cache_persist: Whether to persist cache to disk (default: True)

    Returns:
        List of pool metadata dictionaries or Pool objects
    """
    # Set up RPC URL if not provided
    if rpc_url is None and network is not None:
        rpc_url = f"https://{network}-rpc.publicnode.com"

    # Try to run asynchronously
    try:
        # Check if we're already in an event loop
        asyncio.get_running_loop()

        # We're in an async context, need to use thread
        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor() as pool:
            future = pool.submit(
                run_fetch_in_new_event_loop,
                pool_identifiers,
                rpc_url,
                network,
                chain_id,
                batch_size,
                show_progress,
                max_concurrent_batches,
                format,
                use_cache,
                cache_max_pools,
                cache_max_size_mb,
                cache_persist,
            )
            return future.result()
    except RuntimeError:
        # Not in an event loop, can use asyncio.run directly
        return asyncio.run(
            run_fetch_async(
                pool_identifiers,
                rpc_url,
                network,
                chain_id,
                batch_size,
                show_progress,
                max_concurrent_batches,
                format,
                use_cache,
                cache_max_pools,
                cache_max_size_mb,
                cache_persist,
            )
        )


async def run_fetch_async(
    pool_identifiers: List[str],
    rpc_url: str,
    network: str,
    chain_id: Optional[int],
    batch_size: int,
    show_progress: bool,
    max_concurrent_batches: int,
    format: Literal["dict", "object"],
    use_cache: bool,
    cache_max_pools: int,
    cache_max_size_mb: Optional[float],
    cache_persist: bool,
) -> List[Union[Dict[str, Any], Pool]]:
    """Run the fetch operation asynchronously."""
    # Determine chain ID if not provided
    if chain_id is None:
        # Try to get from network name or RPC URL
        chain_id = get_chain_id_from_network(network, rpc_url)

        if chain_id is None:
            # Try to get from web3 provider
            try:
                async with Web3Provider(rpc_url) as web3:
                    chain_id = await web3.eth.chain_id
                    logger.info(f"Detected chain ID: {chain_id}")
            except Exception as e:
                logger.error(f"Could not determine chain ID: {e}")
                raise ValueError(
                    f"Could not determine chain ID for network '{network}'. "
                    "Please provide chain_id parameter or ensure network name is valid."
                )

    # Create and run the fetcher
    fetcher = MetadataFetcher(
        pool_identifiers=pool_identifiers,
        rpc_url=rpc_url,
        chain_id=chain_id,
        batch_size=batch_size,
        max_concurrent_batches=max_concurrent_batches,
        show_progress=show_progress,
        use_cache=use_cache,
        cache_max_pools=cache_max_pools,
        cache_max_size_mb=cache_max_size_mb,
        cache_persist=cache_persist,
    )

    # Fetch the metadata
    results = await fetcher.fetch_metadata()

    # Convert to Pool objects if requested
    if format == "object":
        return [Pool.from_dict(data) for data in results]
    return results


def run_fetch_in_new_event_loop(
    pool_identifiers: List[str],
    rpc_url: str,
    network: str,
    chain_id: Optional[int],
    batch_size: int,
    show_progress: bool,
    max_concurrent_batches: int,
    format: Literal["dict", "object"],
    use_cache: bool,
    cache_max_pools: int,
    cache_max_size_mb: Optional[float],
    cache_persist: bool,
) -> List[Union[Dict[str, Any], Pool]]:
    """Run fetch_async in a new event loop."""
    # Create a new event loop
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    try:
        return loop.run_until_complete(
            run_fetch_async(
                pool_identifiers,
                rpc_url,
                network,
                chain_id,
                batch_size,
                show_progress,
                max_concurrent_batches,
                format,
                use_cache,
                cache_max_pools,
                cache_max_size_mb,
                cache_persist,
            )
        )
    finally:
        # Clean up any remaining tasks
        try:
            tasks = asyncio.all_tasks(loop)
            if tasks:
                cleanup_task = asyncio.gather(*tasks, return_exceptions=True)
                loop.run_until_complete(asyncio.wait_for(cleanup_task, timeout=5))
        except Exception:
            pass

        # Final cleanup
        try:
            loop.run_until_complete(asyncio.sleep(0))
        except Exception:
            pass

        loop.close()


def calculate_rate_limit_params(
    rate_limit: float,
    avg_response_time: float = 0.7,
    target_utilization: float = 0.5,
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
