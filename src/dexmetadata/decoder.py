"""
Module for decoding the response from deployless multicall.
"""

import logging
from typing import Any, Dict, List, Mapping, Optional

from eth_abi import decode

# ABI type for decoding regular pool metadata responses
POOL_METADATA_RESULT_TYPE = (
    "(address,(address,string,string,uint8),(address,string,string,uint8))[]"
)

# ABI type for decoding Uniswap v4 pool metadata responses
UNISWAP_V4_METADATA_RESULT_TYPE = (
    "(bytes32,(address,string,string,uint8),(address,string,string,uint8))[]"
)

logger = logging.getLogger(__name__)

# Global pool ID lookup table to preserve original pool IDs
_original_pool_ids: Dict[str, str] = {}


def register_pool_id(pool_id: str) -> None:
    """
    Register an original pool ID for later lookup.

    Args:
        pool_id: The complete, original pool ID as provided by the user
    """
    # Store only the first 25 bytes as key (what's used for the contract call)
    # Store without 0x prefix for consistency
    clean_pool_id = pool_id.lower()
    if clean_pool_id.startswith("0x"):
        clean_pool_id = clean_pool_id[2:]

    # The key is the first 25 bytes (50 hex chars)
    key = clean_pool_id[:50].lower()
    # The value is the full original pool ID
    _original_pool_ids[key] = "0x" + clean_pool_id


def decode_metadata_response(response_data: bytes) -> List[Dict[str, Any]]:
    """
    Decodes the response data from a deployless multicall that fetches DEX pool metadata.

    Args:
        response_data: Raw bytes response from eth_call

    Returns:
        A list of dictionaries containing the metadata for each pool
    """
    if not response_data:
        logger.warning("Empty response data received")
        return []

    # Log the response data for debugging
    logger.debug(f"Response data length: {len(response_data)} bytes")
    if len(response_data) > 0:
        logger.debug(f"First few bytes: {response_data[:20].hex()}")

    try:
        # First try to decode as a simple address[] to check if we got any data back
        # This is useful for debugging
        try:
            addresses = decode(["address[]"], response_data)[0]
            logger.debug(
                f"Successfully decoded response as address array with {len(addresses)} addresses"
            )
            for i, addr in enumerate(addresses):
                logger.debug(f"  Address {i}: {addr}")
        except Exception as e:
            logger.debug(f"Response is not a simple address array: {e}")

        # Try to decode as regular pool metadata
        try:
            logger.debug(f"Attempting to decode as {POOL_METADATA_RESULT_TYPE}")
            decoded_data = decode([POOL_METADATA_RESULT_TYPE], response_data)

            # The result should be a tuple with a single item (the array)
            pool_metadata_array = decoded_data[0]
            logger.debug(
                f"Successfully decoded {len(pool_metadata_array)} regular pool metadata entries"
            )

            # Convert the decoded data into our standard dictionary format
            result = []
            for pool_data in pool_metadata_array:
                # Each pool_data is a tuple: (poolAddress, token0, token1)
                # where token0 and token1 are tuples: (tokenAddress, name, symbol, decimals)
                pool_address = pool_data[0]
                token0 = pool_data[1]
                token1 = pool_data[2]

                logger.debug(f"Processing pool: {pool_address}")
                logger.debug(f"  Token0: {token0[0]} ({token0[1]}/{token0[2]})")
                logger.debug(f"  Token1: {token1[0]} ({token1[1]}/{token1[2]})")

                metadata = {
                    "pool_address": pool_address,
                    "token0_address": token0[0],
                    "token0_name": token0[1],
                    "token0_symbol": token0[2],
                    "token0_decimals": token0[3],
                    "token1_address": token1[0],
                    "token1_name": token1[1],
                    "token1_symbol": token1[2],
                    "token1_decimals": token1[3],
                }

                result.append(metadata)

            return result
        except Exception as e:
            logger.debug(f"Failed to decode as regular pool metadata: {e}")

        # Try to decode as Uniswap v4 pool metadata
        try:
            logger.debug(f"Attempting to decode as {UNISWAP_V4_METADATA_RESULT_TYPE}")
            decoded_data = decode([UNISWAP_V4_METADATA_RESULT_TYPE], response_data)

            # The result should be a tuple with a single item (the array)
            pool_metadata_array = decoded_data[0]
            logger.debug(
                f"Successfully decoded {len(pool_metadata_array)} Uniswap v4 pool metadata entries"
            )

            # Convert the decoded data into our standard dictionary format
            result = []
            for pool_data in pool_metadata_array:
                # Each pool_data is a tuple: (poolId, token0, token1)
                # where token0 and token1 are tuples: (tokenAddress, name, symbol, decimals)
                pool_id_bytes = pool_data[0]
                token0 = pool_data[1]
                token1 = pool_data[2]

                # Convert bytes32 pool ID to hex string
                partial_pool_id_hex = "0x" + pool_id_bytes.hex()

                # Look up the original pool ID
                # First extract the key (50 chars, 25 bytes) from the returned bytes
                key = pool_id_bytes.hex()[:50].lower()

                # Use the original pool ID if available, otherwise use the truncated/padded version
                pool_id_hex = _original_pool_ids.get(key, partial_pool_id_hex)

                # Handle tokens
                # Check for native token (handle 0x0000...2710 special case for eth)
                token0_address = token0[0]
                token0_name = token0[1]
                token0_symbol = token0[2]
                token0_decimals = token0[3]

                # Handle native token (ETH) for token0
                if token0_address == "0x0000000000000000000000000000000000000000":
                    # If we received a zero address but no name/symbol, add ETH metadata
                    if not token0_name and not token0_symbol:
                        token0_name = "Ether"
                        token0_symbol = "ETH"
                        token0_decimals = 18
                # Legacy special case for ETH
                elif token0_address and int(token0_address, 16) == 10000:  # 0x2710
                    token0_address = "0x0000000000000000000000000000000000000000"
                    token0_name = "Ether"
                    token0_symbol = "ETH"
                    token0_decimals = 18

                token1_address = token1[0]
                token1_name = token1[1]
                token1_symbol = token1[2]
                token1_decimals = token1[3]

                # Handle native token (ETH) for token1
                if token1_address == "0x0000000000000000000000000000000000000000":
                    # If we received a zero address but no name/symbol, add ETH metadata
                    if not token1_name and not token1_symbol:
                        token1_name = "Ether"
                        token1_symbol = "ETH"
                        token1_decimals = 18
                # Legacy special case for ETH
                elif token1_address and int(token1_address, 16) == 10000:  # 0x2710
                    token1_address = "0x0000000000000000000000000000000000000000"
                    token1_name = "Ether"
                    token1_symbol = "ETH"
                    token1_decimals = 18

                logger.debug(f"Processing Uniswap v4 pool ID: {pool_id_hex}")
                logger.debug(
                    f"  Token0: {token0_address} ({token0_name}/{token0_symbol})"
                )
                logger.debug(
                    f"  Token1: {token1_address} ({token1_name}/{token1_symbol})"
                )

                pool_data = {
                    "pool_address": pool_id_hex,  # For consistent format with regular pools
                    "pool_id": pool_id_hex,  # Store the original pool ID
                    "is_uniswap_v4": True,  # Flag to identify Uniswap v4 pools
                    "token0_address": token0_address,
                    "token0_name": token0_name,
                    "token0_symbol": token0_symbol,
                    "token0_decimals": token0_decimals,
                    "token1_address": token1_address,
                    "token1_name": token1_name,
                    "token1_symbol": token1_symbol,
                    "token1_decimals": token1_decimals,
                }
                result.append(pool_data)

            return result
        except Exception as e:
            logger.debug(f"Failed to decode as Uniswap v4 pool metadata: {e}")

        # If we got here, both decodings failed
        logger.error("Failed to decode response data with any known format")
        return []

    except Exception as e:
        logger.error(f"Error decoding response data: {e}")
        return []
