"""
Module for decoding the response from deployless multicall.
"""

import logging
from typing import Any, Dict, List, cast

from eth_abi import decode

# ABI type for decoding pool metadata responses
POOL_METADATA_RESULT_TYPE = (
    "(address,(address,string,string,uint8),(address,string,string,uint8))[]"
)

logger = logging.getLogger(__name__)


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

        # Now try to decode as our expected PoolMetadata struct array
        logger.debug(f"Attempting to decode as {POOL_METADATA_RESULT_TYPE}")
        decoded_data = decode([POOL_METADATA_RESULT_TYPE], response_data)

        # The result should be a tuple with a single item (the array)
        pool_metadata_array = decoded_data[0]
        logger.debug(
            f"Successfully decoded {len(pool_metadata_array)} pool metadata entries"
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
        logger.error(f"Error decoding response data: {e}")
        return []
