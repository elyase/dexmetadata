"""
Constants and helper functions for network identification and general utilities.
"""

from typing import Dict, Optional

# Network name to chain ID mapping for commonly used networks
NETWORK_TO_CHAIN_ID: Dict[str, int] = {
    "ethereum": 1,
    "mainnet": 1,
    "optimism": 10,
    "base": 8453,
    "arbitrum": 42161,
    "polygon": 137,
    "blast": 81457,
    "zora": 7777777,
    "avalanche": 43114,
    "bsc": 56,
    "sepolia": 11155111,
    "base-sepolia": 84532,
    "arbitrum-sepolia": 421614,
    "unichain": 130,
    "worldchain": 480,
    "unichain-sepolia": 1301,
    "soneium": 1868,
    "ink": 57073,
}


def get_chain_id_from_network(
    network: str, rpc_url: Optional[str] = None
) -> Optional[int]:
    """
    Get chain ID from a network name or RPC URL.

    Args:
        network: The network name (e.g., 'ethereum', 'base')
        rpc_url: Optional RPC URL to extract chain ID from

    Returns:
        The corresponding chain ID or None if not found
    """
    # For known rpc providers, try to get the chain id from the rpc url
    if rpc_url:
        # Check if RPC URL matches known publicnode.com pattern
        if "publicnode.com" in rpc_url:
            # Extract network name from RPC URL
            network_from_url = rpc_url.split("//")[1].split("-")[0]
            return NETWORK_TO_CHAIN_ID.get(network_from_url.lower())
        if "thirdweb.com" in rpc_url:
            # Extract chain ID from thirdweb RPC URL pattern
            # Example: https://8453.rpc.thirdweb.com/${THIRDWEB_API_KEY}
            chain_id_str = rpc_url.split("//")[1].split(".")[0]
            try:
                return int(chain_id_str)
            except (ValueError, IndexError):
                pass
        if "alchemy.com" in rpc_url:
            # Extract network name from Alchemy RPC URL pattern
            # Example: https://eth-mainnet.g.alchemy.com/v2/...
            network_from_url = rpc_url.split("//")[1].split(".")[0]
            # Handle special cases and normalize network names
            if network_from_url.startswith("eth"):
                return NETWORK_TO_CHAIN_ID.get("ethereum")
            if network_from_url.startswith("opt"):
                return NETWORK_TO_CHAIN_ID.get("optimism")
            if network_from_url.startswith("arb"):
                return NETWORK_TO_CHAIN_ID.get("arbitrum")
            if network_from_url.startswith("polygonzkevm"):
                return NETWORK_TO_CHAIN_ID.get("polygon-zkevm")
            # For other cases, try to match directly
            return NETWORK_TO_CHAIN_ID.get(network_from_url.split("-")[0].lower())
    return NETWORK_TO_CHAIN_ID.get(network.lower())
