"""
Handler for Uniswap V4 pools.
"""

import asyncio
import logging
from typing import Any, Dict, List, Optional

from eth_abi import encode
from web3 import Web3
from web3.main import AsyncWeb3

from ..bytecode import UNISWAP_V4_METADATA_BYTECODE
from ..decoder import decode_metadata_response, register_pool_id
from ..progress import ProgressTracker
from ..utils import is_valid_metadata
from .base import PoolFetcher

logger = logging.getLogger(__name__)

# Mapping of chain IDs to Uniswap v4 PositionManager addresses
# https://docs.uniswap.org/contracts/v4/deployments
UNISWAP_V4_POSITION_MANAGERS: Dict[int, str] = {
    1: "0xbd216513d74c8cf14cf4747e6aaa6420ff64ee9e",  # Ethereum
    10: "0x3c3ea4b57a46241e54610e5f022e5c45859a1017",  # Optimism
    8453: "0x7c5f5a4bbd8fd63184577525326123b519429bdc",  # Base
    42161: "0xd88f38f930b7952f2db2432cb002e7abbf3dd869",  # Arbitrum One
    137: "0x1ec2ebf4f37e7363fdfe3551602425af0b3ceef9",  # Polygon
    81457: "0x4ad2f4cca2682cbb5b950d660dd458a1d3f1baad",  # Blast
    7777777: "0xf66c7b99e2040f0d9b326b3b7c152e9663543d63",  # Zora
    480: "0xc585e0f504613b5fbf874f21af14c65260fb41fa",  # Worldchain
    57073: "0x1b35d13a2e2528f192637f14b05f0dc0e7deb566",  # Ink
    1868: "0x1b35d13a2e2528f192637f14b05f0dc0e7deb566",  # Soneium
    43114: "0xb74b1f14d2754acfcbbe1a221023a5cf50ab8acd",  # Avalanche
    56: "0x7a4a5c919ae2541aed11041a1aeee68f1287f95b",  # BNB Smart Chain
    1301: "0xf969aee60879c54baaed9f3ed26147db216fd664",  # Unichain Sepolia
    11155111: "0x429ba70129df741B2Ca2a85BC3A2a3328e5c09b4",  # Sepolia
    84532: "0x4b2c77d209d3405f41a037ec6c77f7f5b8e2ca80",  # Base Sepolia
    421614: "0xAc631556d3d4019C95769033B5E719dD77124BAc",  # Arbitrum Sepolia
    130: "0x4529a01c7a0410167c5740c487a8de60232617bf",  # Unichain
}


def get_position_manager_address(chain_id: int) -> str:
    """
    Get the Uniswap v4 PositionManager address for a given chain ID.

    Args:
        chain_id: The blockchain network's chain ID

    Returns:
        The PositionManager contract address for the specified chain

    Raises:
        ValueError: If no PositionManager address is found for the chain ID
    """
    address = UNISWAP_V4_POSITION_MANAGERS.get(chain_id)
    if not address:
        raise ValueError(f"No Uniswap v4 PositionManager found for chain ID {chain_id}")
    return address


def is_uniswap_v4_pool_id(input_str: str) -> bool:
    """
    Determine if an input string is likely a Uniswap v4 poolId.

    Args:
        input_str: The string to check

    Returns:
        True if the string matches the pattern of a Uniswap v4 poolId
    """
    # Remove 0x prefix if present
    clean_str = input_str.lower()
    if clean_str.startswith("0x"):
        clean_str = clean_str[2:]

    # Pool IDs are 32 bytes (64 hex characters)
    if len(clean_str) != 64:
        return False

    return True


class UniswapV4PoolFetcher(PoolFetcher):
    """Handler for Uniswap V4 pools."""

    PROTOCOL_NAME = "uniswap_v4"
    SUPPORTS_TYPE_CHECK = is_uniswap_v4_pool_id

    def __init__(
        self,
        web3_provider: AsyncWeb3,
        batch_size: int,
        batch_semaphore: asyncio.Semaphore,
        chain_id: int,
        progress_tracker: Optional[ProgressTracker] = None,
    ):
        super().__init__(web3_provider, batch_size, batch_semaphore, progress_tracker)
        self.chain_id = chain_id

        # Get position manager address
        self.position_manager_address = get_position_manager_address(chain_id)

    async def pre_process_pools(self, pool_identifiers: List[str]) -> None:
        """Register pool IDs for lookup during decoding."""
        for pool_id in pool_identifiers:
            register_pool_id(pool_id)

    async def post_process_pools(
        self, results: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Mark each pool as Uniswap v4 and handle native token addresses."""
        for pool in results:
            # Mark protocol as Uniswap v4
            pool["protocol"] = "Uniswap v4"
            pool["is_uniswap_v4"] = True  # Keep for backward compatibility

            # Add unified identifier field
            pool["identifier"] = pool["pool_id"]

            # Handle native token (ETH) for token0
            if pool.get(
                "token0_address"
            ) == "0x0000000000000000000000000000000000000000" and not pool.get(
                "token0_symbol"
            ):
                pool["token0_name"] = "Ether"
                pool["token0_symbol"] = "ETH"
                pool["token0_decimals"] = 18

            # Handle native token (ETH) for token1
            if pool.get(
                "token1_address"
            ) == "0x0000000000000000000000000000000000000000" and not pool.get(
                "token1_symbol"
            ):
                pool["token1_name"] = "Ether"
                pool["token1_symbol"] = "ETH"
                pool["token1_decimals"] = 18

            # Set validity flag
            pool["is_valid"] = is_valid_metadata(pool)

        return results

    async def process_batch(self, batch_pool_ids: List[str]) -> List[Dict[str, Any]]:
        """Process a single batch of Uniswap V4 pool IDs."""
        async with self.batch_semaphore:
            try:
                # Convert poolIds from hex strings to bytes25
                bytes25_pool_ids = []
                for pool_id in batch_pool_ids:
                    hex_string = pool_id[2:] if pool_id.startswith("0x") else pool_id
                    pool_id_bytes = bytes.fromhex(hex_string)[:25]
                    bytes25_pool_ids.append(pool_id_bytes)

                # Encode constructor arguments
                constructor_args = encode(
                    ["bytes25[]", "address"],
                    [bytes25_pool_ids, self.position_manager_address],
                )

                data = UNISWAP_V4_METADATA_BYTECODE + constructor_args.hex().replace(
                    "0x", ""
                )

                # Make the call
                result = await self.make_eth_call(data)

                if not result:
                    logger.warning(
                        f"Empty response from eth_call for v4 batch of {len(batch_pool_ids)} pool IDs"
                    )
                    if self.progress_tracker:
                        self.progress_tracker.update(len(batch_pool_ids))

                    # Return placeholder data for each pool ID in the batch
                    return [
                        self._create_invalid_v4_pool_metadata(pid)
                        for pid in batch_pool_ids
                    ]

                # Decode the response
                batch_results = decode_metadata_response(result)

                # Update progress
                if self.progress_tracker:
                    self.progress_tracker.update(len(batch_pool_ids))

                return batch_results

            except Exception as e:
                logger.error(f"Error processing Uniswap v4 pool batch: {e}")
                if self.progress_tracker:
                    self.progress_tracker.update(len(batch_pool_ids))

                # Return placeholder data for each pool ID in the batch
                return [
                    self._create_invalid_v4_pool_metadata(pid) for pid in batch_pool_ids
                ]

    def _create_invalid_v4_pool_metadata(self, pool_id: str) -> Dict[str, Any]:
        """Create placeholder metadata for an invalid Uniswap v4 pool."""
        return {
            "identifier": pool_id,  # Unified identifier field
            "token0_address": "",
            "token0_name": "",
            "token0_symbol": "",
            "token0_decimals": 0,
            "token1_address": "",
            "token1_name": "",
            "token1_symbol": "",
            "token1_decimals": 0,
            "protocol": "Uniswap v4",
            "is_uniswap_v4": True,  # Keep this for backward compatibility
            "is_valid": False,
        }
