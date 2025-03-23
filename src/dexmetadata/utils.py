"""
Utility functions for DEX metadata handling.
"""

import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)


def is_valid_metadata(metadata: Dict[str, Any]) -> bool:
    """
    Validate if pool metadata contains useful information.

    Args:
        metadata: The pool metadata dictionary

    Returns:
        True if the metadata is valid, False otherwise
    """
    if not metadata:
        return False

    # If the metadata already has is_valid field, use it
    if "is_valid" in metadata:
        return metadata["is_valid"]

    # Get basic token info
    zero_addr = "0x0000000000000000000000000000000000000000"

    # Check if this is a Uniswap v4 pool
    is_v4 = (
        metadata.get("is_uniswap_v4", False) or metadata.get("protocol") == "Uniswap v4"
    )

    # Special handling for Uniswap v4 pools
    if is_v4:
        # Just do a basic check that the pool has some token information
        for token_num in [0, 1]:
            addr = metadata.get(f"token{token_num}_address", "")
            name = metadata.get(f"token{token_num}_name", "")
            symbol = metadata.get(f"token{token_num}_symbol", "")

            # For Uniswap v4, either the token has a non-zero address
            # or it has a null address with at least some token info (name or symbol)
            if not ((addr and addr != zero_addr) or (name or symbol)):
                logger.debug(
                    f"Invalid metadata for Uniswap v4 pool {metadata.get('pool_id', 'unknown')}: token{token_num} has no identity"
                )
                return False

        # If we got here, the Uniswap v4 pool is valid
        return True

    # For non-Uniswap v4 pools, apply the standard validation
    for token_num in [0, 1]:
        addr = metadata.get(f"token{token_num}_address", "")
        name = metadata.get(f"token{token_num}_name", "")
        symbol = metadata.get(f"token{token_num}_symbol", "")

        # Regular pools must have a non-zero address
        has_identity = addr and addr != zero_addr and (name or symbol)

        if not has_identity:
            logger.debug(
                f"Invalid metadata for pool {metadata.get('pool_address', 'unknown')}: insufficient token{token_num} information"
            )
            return False

    return True
