"""
DEX pool metadata handler implementations.

This module contains the implementation of various pool metadata handlers
for different DEX protocols.
"""

# Registry of pool handlers
from ..registry import pool_handler_registry
from .base import PoolFetcher
from .default import DefaultPoolFetcher
from .uniswap_v4 import UniswapV4PoolFetcher

# Register built-in handlers
pool_handler_registry.register(DefaultPoolFetcher)
pool_handler_registry.register(UniswapV4PoolFetcher)

__all__ = [
    "PoolFetcher",
    "DefaultPoolFetcher",
    "UniswapV4PoolFetcher",
    "pool_handler_registry",
]
