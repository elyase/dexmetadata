"""
Base class for DEX pool metadata handlers.
"""

import asyncio
import logging
from typing import Any, Dict, List, Optional

from web3.main import AsyncWeb3

logger = logging.getLogger(__name__)


class PoolFetcher:
    """Base class for pool metadata fetchers."""

    # Class-level attributes for protocol identification
    PROTOCOL_NAME = "base"
    SUPPORTS_TYPE_CHECK = None  # Function to check if handler supports an identifier

    def __init__(
        self,
        web3_provider: AsyncWeb3,
        batch_size: int,
        batch_semaphore: asyncio.Semaphore,
        progress_tracker: Optional = None,
    ):
        self.web3 = web3_provider
        self.batch_size = batch_size
        self.batch_semaphore = batch_semaphore
        self.progress_tracker = progress_tracker
        # Use a connection limit based on the batch semaphore value
        # This ensures we respect the user's concurrency settings
        connection_limit = batch_semaphore._value
        self.connection_semaphore = asyncio.Semaphore(connection_limit)

    @classmethod
    def supports(cls, identifier: str) -> bool:
        """Check if this fetcher supports the given pool identifier."""
        if cls.SUPPORTS_TYPE_CHECK is None:
            return False
        return cls.SUPPORTS_TYPE_CHECK(identifier)

    async def process_pools(self, pool_identifiers: List[str]) -> List[Dict[str, Any]]:
        """
        Process multiple pools in batches.

        This is the default implementation that works for most handlers:
        1. Creates batches from the pool identifiers
        2. Processes each batch concurrently
        3. Collects and returns the results

        Override if needed for special protocols.
        """
        if not pool_identifiers:
            return []

        # Pre-processing hook (can be overridden by subclasses)
        await self.pre_process_pools(pool_identifiers)

        # Create batches
        batches = [
            pool_identifiers[i : i + self.batch_size]
            for i in range(0, len(pool_identifiers), self.batch_size)
        ]

        # Process all batches concurrently
        tasks = [self.process_batch(batch) for batch in batches]
        batch_results = await asyncio.gather(*tasks)

        # Flatten results
        all_results = []
        for batch in batch_results:
            all_results.extend(batch)

        # Post-processing hook (can be overridden by subclasses)
        return await self.post_process_pools(all_results)

    async def pre_process_pools(self, pool_identifiers: List[str]) -> None:
        """
        Pre-process pools before batch processing.

        This is a hook that subclasses can override to perform
        protocol-specific initialization before processing pools.
        """
        pass

    async def post_process_pools(
        self, results: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Post-process pools after batch processing.

        This is a hook that subclasses can override to perform
        protocol-specific finalization after processing pools.
        """
        return results

    async def process_batch(self, batch_identifiers: List[str]) -> List[Dict[str, Any]]:
        """
        Process a single batch of pools.

        This method must be implemented by subclasses with protocol-specific logic.
        """
        raise NotImplementedError("Subclasses must implement this method")

    async def make_eth_call(self, data: str) -> bytes:
        """
        Make an eth_call with the provided data.

        This is a helper method that handles connection limiting and error logging.
        """
        try:
            async with self.connection_semaphore:
                return await self.web3.eth.call({"data": data})
        except Exception as e:
            logger.error(f"Error making eth_call: {e}")
            return b""
