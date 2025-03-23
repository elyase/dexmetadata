"""
Handler for regular DEX pools (non-Uniswap V4).
"""

import asyncio
import logging
from typing import Any, Dict, List, Optional

from eth_abi import encode
from web3 import Web3
from web3.main import AsyncWeb3

from ..bytecode import POOL_METADATA_BYTECODE
from ..decoder import decode_metadata_response
from ..utils import is_valid_metadata
from .base import PoolFetcher

logger = logging.getLogger(__name__)


class DefaultPoolFetcher(PoolFetcher):
    """Handler for regular DEX pools (non-UniswapV4)."""

    PROTOCOL_NAME = "default"
    SUPPORTS_TYPE_CHECK = lambda id: Web3.is_address(id)

    async def process_batch(self, batch_addresses: List[str]) -> List[Dict[str, Any]]:
        """Process a single batch of regular pool addresses."""
        async with self.batch_semaphore:
            try:
                # Encode constructor arguments
                constructor_args = encode(["address[]"], [batch_addresses])
                data = POOL_METADATA_BYTECODE + constructor_args.hex().replace("0x", "")

                # Make the call
                result = await self.make_eth_call(data)

                if not result:
                    logger.warning(
                        f"Empty response from eth_call for batch of {len(batch_addresses)} addresses"
                    )
                    if self.progress_tracker:
                        self.progress_tracker.update(len(batch_addresses))

                    # Return placeholder data for each address in the batch
                    return [
                        self._create_invalid_pool_metadata(addr)
                        for addr in batch_addresses
                    ]

                # Decode the response
                decoded_pools = decode_metadata_response(result)

                # Mark pools as valid or invalid based on their content and add identifier
                for pool in decoded_pools:
                    pool["is_valid"] = is_valid_metadata(pool)
                    # Set protocol information (empty for default handler as these are generic DEX pools)
                    pool["protocol"] = ""
                    # Add unified identifier field
                    pool["identifier"] = pool["pool_address"]

                # Update progress
                if self.progress_tracker:
                    self.progress_tracker.update(len(batch_addresses))

                return decoded_pools

            except Exception as e:
                logger.error(f"Error processing regular pools batch: {e}")
                if self.progress_tracker:
                    self.progress_tracker.update(len(batch_addresses))

                # Return placeholder data for each address in the batch
                return [
                    self._create_invalid_pool_metadata(addr) for addr in batch_addresses
                ]

    def _create_invalid_pool_metadata(self, pool_address: str) -> Dict[str, Any]:
        """Create placeholder metadata for an invalid pool."""
        return {
            "pool_address": pool_address,  # Keep for backward compatibility
            "identifier": pool_address,  # Unified identifier field
            "token0_address": "",
            "token0_name": "",
            "token0_symbol": "",
            "token0_decimals": 0,
            "token1_address": "",
            "token1_name": "",
            "token1_symbol": "",
            "token1_decimals": 0,
            "protocol": "",
            "is_valid": False,
        }
