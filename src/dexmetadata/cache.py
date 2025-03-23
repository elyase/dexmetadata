"""
Cache module for DEX pool metadata.

This module provides a caching system for DEX pool metadata with:
- Efficient caching using the diskcache library
- Size limits by memory usage
- SQLite-based persistence
- Thread-safety and process-safety for concurrent access
"""

import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from diskcache import FanoutCache as Cache

logger = logging.getLogger(__name__)

# Default cache settings
DEFAULT_MAX_POOLS = 10000000
DEFAULT_CACHE_DIR = Path.home() / ".dexmetadata_cache"

# Approximate size of a typical pool object in bytes
# This is a rough estimate to convert between pool count and memory usage
APPROX_POOL_SIZE_BYTES = 2048  # 2KB per pool


class PoolMetadataCache:
    """
    Cache for DEX pool metadata using the diskcache library.

    Features:
    - Thread-safe and process-safe operations
    - Size limits by memory usage
    - Efficient eviction policy
    - SQLite-based persistence
    - Case-insensitive keys
    """

    def __init__(
        self,
        max_pools: int = DEFAULT_MAX_POOLS,
        max_size_mb: Optional[float] = None,
        persist: bool = True,
        cache_dir: Path = DEFAULT_CACHE_DIR,
    ):
        """
        Initialize the cache with the specified parameters.

        Args:
            max_pools: Maximum number of pools to cache
            max_size_mb: Maximum cache size in MB (overrides max_pools if provided)
            persist: Whether to persist cache to disk
            cache_dir: Directory for cache persistence
        """
        # Calculate size limit based on max_pools or max_size_mb
        if max_size_mb is not None:
            size_limit = int(max_size_mb * 1024 * 1024)
            logger.debug(f"Setting size_limit to {size_limit} bytes ({max_size_mb}MB)")
        else:
            size_limit = max_pools * APPROX_POOL_SIZE_BYTES
            logger.debug(
                f"Setting size_limit to {size_limit} bytes based on max_pools={max_pools}"
            )

        # Create directory if it doesn't exist
        os.makedirs(cache_dir, exist_ok=True)

        # Initialize the cache
        # Using regular Cache instead of FanoutCache for simplicity and compatibility
        self._cache = Cache(
            directory=str(cache_dir),
            size_limit=size_limit,
            eviction_policy="least-recently-used",
            cull_limit=10,  # Cull 10 items at a time when size limit is reached
            statistics=True,  # Enable statistics for monitoring
            sqlite_pragma_synchronous=1,  # Normal sync mode for better performance
            sqlite_cache_size=8192,  # 8MB page cache
        )

        self.max_pools = max_pools
        self.persist = persist
        self.cache_dir = cache_dir

        # Log initialization
        logger.info(
            f"Cache initialized: max_pools={max_pools}, "
            f"size_limit={size_limit} bytes, persist={persist}"
        )

    def get(self, key: str) -> Optional[dict]:
        """
        Get pool metadata from cache.

        Args:
            key: Pool identifier (address or poolId)

        Returns:
            Pool metadata dict if found, None otherwise
        """
        normalized_key = self._normalize_key(key)
        try:
            result = self._cache.get(normalized_key)
            if result is not None:
                logger.debug(f"Cache hit for pool {key}")
            return result
        except Exception as e:
            logger.warning(f"Error retrieving from cache: {e}")
            return None

    def get_many(self, keys: List[str]) -> Dict[str, dict]:
        """
        Get multiple pool metadata entries from cache.

        Args:
            keys: List of pool identifiers

        Returns:
            Dictionary mapping found keys to their metadata
        """
        normalized_keys = [self._normalize_key(key) for key in keys]
        result = {}

        # Use a transaction for better performance
        try:
            with self._cache.transact():
                for key in normalized_keys:
                    value = self._cache.get(key)
                    if value is not None:
                        result[key] = value

            logger.debug(f"Cache lookup: {len(result)}/{len(keys)} hits")
            return result
        except Exception as e:
            logger.warning(f"Error in get_many: {e}")
            # If transaction fails, fall back to individual gets
            for key in normalized_keys:
                try:
                    value = self._cache.get(key)
                    if value is not None:
                        result[key] = value
                except Exception:
                    pass
            return result

    def put(self, key: str, data: dict):
        """
        Add or update pool metadata in cache.

        Args:
            key: Pool identifier (address or poolId)
            data: Pool metadata dict
        """
        normalized_key = self._normalize_key(key)
        try:
            self._cache.set(normalized_key, data)
            logger.debug(f"Added/updated pool {key} in cache")
        except Exception as e:
            logger.warning(f"Error adding to cache: {e}")

    def put_many(self, data_dict: Dict[str, dict]):
        """
        Add or update multiple pool metadata entries in cache.

        Args:
            data_dict: Dictionary mapping pool identifiers to metadata
        """
        try:
            # Normalize all keys
            normalized_data = {
                self._normalize_key(key): value for key, value in data_dict.items()
            }

            # Use a transaction for better performance
            with self._cache.transact():
                for key, value in normalized_data.items():
                    self._cache.set(key, value)

            logger.debug(f"Added {len(data_dict)} entries to cache")
        except Exception as e:
            logger.warning(f"Error in put_many: {e}")
            # If transaction fails, fall back to individual sets
            for key, value in normalized_data.items():
                try:
                    self._cache.set(key, value)
                except Exception:
                    pass

    def clear(self):
        """
        Clear all entries from the cache and reset statistics.
        """
        try:
            self._cache.clear()
            # Reset statistics by getting them with reset=True
            self._cache.stats(reset=True)
            logger.info("Cache cleared and statistics reset")
        except Exception as e:
            logger.warning(f"Error clearing cache: {e}")

    def close(self):
        """
        Close the cache connection.
        """
        try:
            self._cache.close()
            logger.debug("Cache closed")
        except Exception as e:
            logger.warning(f"Error closing cache: {e}")

    def __len__(self):
        """Return the number of entries in the cache."""
        try:
            return len(self._cache)
        except Exception as e:
            logger.warning(f"Error getting cache length: {e}")
            return 0

    def get_stats(self) -> Dict[str, Any]:
        """
        Get statistics about the cache.

        Returns:
            Dictionary with cache statistics
        """
        try:
            hits, misses = self._cache.stats()

            stats = {
                "entries": len(self._cache),
                "max_entries": self.max_pools,
                "usage_percent": (len(self._cache) / max(1, self.max_pools)) * 100,
                "approx_size_mb": self._cache.volume() / (1024 * 1024),
                "persist_enabled": self.persist,
                "hits": hits,
                "misses": misses,
                "hit_rate": (hits / max(1, hits + misses)) * 100
                if (hits + misses) > 0
                else 0,
            }
            return stats
        except Exception as e:
            logger.warning(f"Error getting cache stats: {e}")
            return {"entries": 0, "max_entries": self.max_pools, "error": str(e)}

    def _normalize_key(self, key: str) -> str:
        """Normalize cache key to avoid case sensitivity issues."""
        return key.lower() if key else key
        
    def chain_specific_key(self, key: str, chain_id: int) -> str:
        """Create a chain-specific cache key."""
        normalized = self._normalize_key(key)
        return f"{chain_id}:{normalized}"


class CacheManager:
    """
    Manages the lifecycle of cache instances.
    Implements the singleton pattern for default cache management.
    """

    _instance = None
    _default_cache = None

    @classmethod
    def get_instance(cls) -> "CacheManager":
        """Get the singleton instance of CacheManager."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def get_default_cache(
        self,
        max_pools: int = DEFAULT_MAX_POOLS,
        max_size_mb: Optional[float] = None,
        persist: bool = True,
        cache_dir: Optional[Path] = None,
    ) -> PoolMetadataCache:
        """
        Get or create the default cache instance.

        Args:
            max_pools: Maximum number of pools to cache
            max_size_mb: Maximum cache size in MB (overrides max_pools if provided)
            persist: Whether to persist cache to disk
            cache_dir: Directory for cache persistence

        Returns:
            The default cache instance
        """
        if CacheManager._default_cache is None:
            logger.info("Creating new default cache instance")
            CacheManager._default_cache = PoolMetadataCache(
                max_pools=max_pools,
                max_size_mb=max_size_mb,
                persist=persist,
                cache_dir=cache_dir or DEFAULT_CACHE_DIR,
            )
        else:
            logger.info("Using existing default cache instance")

        return CacheManager._default_cache

    def delete_default_cache(self) -> bool:
        """
        Delete the default cache.

        Returns:
            bool: True if deletion was successful, False otherwise
        """
        try:
            if CacheManager._default_cache is not None:
                cache_dir = CacheManager._default_cache.cache_dir
                CacheManager._default_cache.close()
                CacheManager._default_cache = None

                # Remove the cache directory
                import shutil

                if Path(cache_dir).exists():
                    shutil.rmtree(cache_dir)
                logger.info(f"Deleted default cache at {cache_dir}")
                return True
            return False
        except Exception as e:
            logger.error(f"Error deleting default cache: {e}")
            return False

    def reset(self):
        """Reset the cache manager state (useful for testing)."""
        if CacheManager._default_cache is not None:
            CacheManager._default_cache.close()
        CacheManager._default_cache = None


# Convenience functions that use CacheManager
def get_default_cache(
    max_pools: int = DEFAULT_MAX_POOLS,
    max_size_mb: Optional[float] = None,
    persist: bool = True,
    cache_dir: Optional[Path] = None,
) -> PoolMetadataCache:
    """Convenience function to get the default cache using CacheManager."""
    return CacheManager.get_instance().get_default_cache(
        max_pools=max_pools,
        max_size_mb=max_size_mb,
        persist=persist,
        cache_dir=cache_dir,
    )


def delete_default_cache() -> bool:
    """Convenience function to delete the default cache using CacheManager."""
    return CacheManager.get_instance().delete_default_cache()
