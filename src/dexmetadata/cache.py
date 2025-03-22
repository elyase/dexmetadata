"""
Cache module for DEX pool metadata.

This module provides a caching system for DEX pool metadata with:
- Hybrid LRU/LFU eviction policy
- Size limits (by pool count or memory usage)
- SQLite-based persistence
- Thread-safety for concurrent access
"""

import json
import logging
import os
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Default cache settings
DEFAULT_MAX_POOLS = 10000
DEFAULT_CACHE_DIR = Path.home() / ".dexmetadata_cache"
DEFAULT_DB_FILENAME = "pool_cache.db"

# Approximate size of a typical pool object in bytes
# This is a rough estimate to convert between pool count and memory usage
APPROX_POOL_SIZE_BYTES = 2048  # 2KB per pool


class PoolMetadataCache:
    """
    Cache for DEX pool metadata with hybrid LRU/LFU eviction and optional persistence.

    Features:
    - Thread-safe operations
    - Size limits by pool count or memory usage
    - Hybrid LRU/LFU eviction policy
    - SQLite-based persistence (optional)
    """

    def __init__(
        self,
        max_pools: int = DEFAULT_MAX_POOLS,
        max_size_mb: Optional[float] = None,
        persist: bool = False,
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
        self._lock = threading.RLock()

        # Calculate max_pools based on max_size_mb if provided
        if max_size_mb is not None:
            max_size_bytes = max_size_mb * 1024 * 1024
            max_pools = int(max_size_bytes / APPROX_POOL_SIZE_BYTES)
            logger.debug(
                f"Setting max_pools to {max_pools} based on {max_size_mb}MB limit"
            )

        self.max_pools = max_pools
        self.persist = persist
        self.cache_dir = cache_dir

        # Initialize cache and metadata dictionaries
        self._cache = {}  # pool_address -> pool_data
        self._metadata = {}  # pool_address -> (access_count, last_access_time)

        # Initialize SQLite connection if persistence is enabled
        self._conn = None
        if self.persist:
            self._init_persistent_storage()

        # Log initialization
        logger.info(
            f"Cache initialized: max_pools={self.max_pools}, persist={self.persist}"
        )

    def _init_persistent_storage(self):
        """Initialize the SQLite database for persistent storage."""
        try:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            db_path = self.cache_dir / DEFAULT_DB_FILENAME

            self._conn = sqlite3.connect(str(db_path), check_same_thread=False)

            # Create tables if they don't exist
            cursor = self._conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS pools (
                    address TEXT PRIMARY KEY,
                    data TEXT NOT NULL,
                    access_count INTEGER NOT NULL,
                    last_access INTEGER NOT NULL
                )
            """)
            self._conn.commit()

            # Load cached data from SQLite to memory
            self._load_from_db()

            logger.debug(f"Initialized persistent cache at {db_path}")
        except Exception as e:
            logger.error(f"Error initializing persistent cache: {e}")
            self.persist = False

    def _load_from_db(self):
        """Load cached pool data from SQLite to memory."""
        if not self._conn:
            return

        try:
            cursor = self._conn.cursor()
            cursor.execute("SELECT address, data, access_count, last_access FROM pools")
            rows = cursor.fetchall()

            with self._lock:
                for address, data_json, access_count, last_access in rows:
                    try:
                        data = json.loads(data_json)
                        self._cache[address] = data
                        self._metadata[address] = (access_count, last_access)
                    except Exception as e:
                        logger.warning(f"Error loading cached pool {address}: {e}")

            logger.info(f"Loaded {len(rows)} pools from persistent cache")
            self._log_cache_size()
        except Exception as e:
            logger.error(f"Error loading from persistent cache: {e}")

    def _save_to_db(self, address: str, data: dict, metadata: Tuple[int, float]):
        """Save a single pool to the persistent cache."""
        if not self._conn or not self.persist:
            return

        try:
            access_count, last_access = metadata
            data_json = json.dumps(data)

            cursor = self._conn.cursor()
            cursor.execute(
                "INSERT OR REPLACE INTO pools (address, data, access_count, last_access) VALUES (?, ?, ?, ?)",
                (address, data_json, access_count, last_access),
            )
            self._conn.commit()
        except Exception as e:
            logger.warning(f"Error saving pool {address} to persistent cache: {e}")

    def get(self, address: str) -> Optional[dict]:
        """
        Get pool metadata from cache.

        Args:
            address: Pool address

        Returns:
            Pool metadata dict if found, None otherwise
        """
        with self._lock:
            pool_data = self._cache.get(address)
            if pool_data:
                # Update access metadata
                access_count, _ = self._metadata.get(address, (0, 0))
                self._metadata[address] = (access_count + 1, time.time())

                # Update persistent storage if enabled
                if self.persist:
                    self._save_to_db(address, pool_data, self._metadata[address])

                logger.debug(f"Cache hit for pool {address}")
            return pool_data

    def get_many(self, addresses: List[str]) -> Dict[str, dict]:
        """
        Get multiple pool metadata entries from cache.

        Args:
            addresses: List of pool addresses

        Returns:
            Dictionary mapping found addresses to their metadata
        """
        result = {}
        with self._lock:
            for address in addresses:
                pool_data = self._cache.get(address)
                if pool_data:
                    # Update access metadata
                    access_count, _ = self._metadata.get(address, (0, 0))
                    self._metadata[address] = (access_count + 1, time.time())
                    result[address] = pool_data

                    # Update persistent storage if enabled
                    if self.persist:
                        self._save_to_db(address, pool_data, self._metadata[address])

                    logger.debug(f"Cache hit for pool {address}")

        return result

    def put(self, address: str, data: dict):
        """
        Add or update pool metadata in cache.

        Args:
            address: Pool address
            data: Pool metadata dict
        """
        with self._lock:
            # Update or add the cache entry
            self._cache[address] = data

            # Update access metadata
            access_count, _ = self._metadata.get(address, (0, 0))
            self._metadata[address] = (access_count + 1, time.time())

            # Check if we need to evict
            if len(self._cache) > self.max_pools:
                self._evict()

            # Update persistent storage if enabled
            if self.persist:
                self._save_to_db(address, data, self._metadata[address])

        # Log cache size periodically
        if len(self._cache) % 10 == 0:  # Log every 10 entries
            self._log_cache_size()

    def put_many(self, data_dict: Dict[str, dict]):
        """
        Add or update multiple pool metadata entries in cache.

        Args:
            data_dict: Dictionary mapping pool addresses to metadata
        """
        with self._lock:
            for address, data in data_dict.items():
                self.put(address, data)

        # Log cache size after batch update
        self._log_cache_size()

    def _evict(self):
        """
        Evict pool entries based on hybrid LRU/LFU policy.

        This uses a scoring system that considers both frequency and recency:
        - Lower scores are evicted first
        - Score = (access_count * 0.4) + (recency_factor * 0.6)
        """
        if not self._cache:
            return

        # Calculate scores for all entries
        current_time = time.time()
        max_age = 30 * 24 * 60 * 60  # 30 days in seconds

        scores = {}
        for address, (access_count, last_access) in self._metadata.items():
            age = current_time - last_access
            recency_factor = max(0, 1 - (age / max_age))

            # Hybrid score using both frequency and recency
            score = (access_count * 0.4) + (recency_factor * 0.6)
            scores[address] = score

        # Determine how many entries to remove (25% of max, at least 1)
        num_to_remove = max(1, self.max_pools // 4)

        # Sort by score (ascending) and get addresses to remove
        to_remove = sorted(scores.keys(), key=lambda addr: scores[addr])[:num_to_remove]

        # Remove the selected entries
        for address in to_remove:
            self._cache.pop(address, None)
            self._metadata.pop(address, None)

            # Remove from persistent storage if enabled
            if self.persist and self._conn:
                try:
                    cursor = self._conn.cursor()
                    cursor.execute("DELETE FROM pools WHERE address = ?", (address,))
                    self._conn.commit()
                except Exception as e:
                    logger.warning(
                        f"Error removing pool {address} from persistent cache: {e}"
                    )

        logger.info(f"Evicted {len(to_remove)} pools from cache")
        self._log_cache_size()

    def _log_cache_size(self):
        """Log the current size of the cache."""
        cache_size = len(self._cache)
        approx_mb = (cache_size * APPROX_POOL_SIZE_BYTES) / (1024 * 1024)
        logger.info(f"Cache status: {cache_size} pools (~{approx_mb:.2f}MB)")

    def close(self):
        """Close the cache and persistent storage connections."""
        if self._conn:
            try:
                self._conn.close()
            except Exception as e:
                logger.warning(f"Error closing cache connection: {e}")

    def __len__(self):
        """Return the number of entries in the cache."""
        with self._lock:
            return len(self._cache)

    def get_stats(self) -> Dict[str, Any]:
        """
        Get statistics about the cache.

        Returns:
            Dictionary with cache statistics
        """
        with self._lock:
            num_entries = len(self._cache)
            approx_size_bytes = num_entries * APPROX_POOL_SIZE_BYTES
            approx_size_mb = approx_size_bytes / (1024 * 1024)

            # Calculate average access count
            total_access_count = sum(count for count, _ in self._metadata.values())
            avg_access_count = total_access_count / max(1, len(self._metadata))

            # Get most frequently accessed pools (top 5)
            sorted_by_access = sorted(
                self._metadata.items(), key=lambda x: x[1][0], reverse=True
            )[:5]

            top_pools = [
                {"address": addr, "access_count": metadata[0]}
                for addr, metadata in sorted_by_access
            ]

            return {
                "entries": num_entries,
                "max_entries": self.max_pools,
                "usage_percent": (num_entries / max(1, self.max_pools)) * 100,
                "approx_size_mb": approx_size_mb,
                "persist_enabled": self.persist,
                "avg_access_count": avg_access_count,
                "top_accessed_pools": top_pools,
            }

    def clear(self):
        """
        Clear all entries from the cache.

        This removes all entries from both memory and persistent storage (if enabled).
        """
        with self._lock:
            # Clear memory cache
            self._cache = {}
            self._metadata = {}

            # Close existing connection if any
            if self._conn:
                try:
                    self._conn.close()
                except Exception as e:
                    logger.warning(f"Error closing database connection: {e}")
                self._conn = None

            # Clear persistent storage if enabled
            if self.persist:
                try:
                    # Delete the database file
                    db_path = self.cache_dir / DEFAULT_DB_FILENAME
                    if db_path.exists():
                        os.remove(db_path)
                        logger.info(f"Deleted database file: {db_path}")

                    # Reinitialize the database
                    self._init_persistent_storage()
                    logger.info("Reinitialized persistent cache")
                except Exception as e:
                    logger.error(f"Error clearing persistent cache: {e}")

        logger.info("Cache cleared")


class CacheManager:
    """
    Manages the lifecycle of cache instances.
    Implements the singleton pattern for default cache management.
    """

    _instance = None
    _lock = threading.Lock()

    def __init__(self):
        self._default_cache = None
        self._cache_lock = threading.Lock()

    @classmethod
    def get_instance(cls) -> "CacheManager":
        """Get the singleton instance of CacheManager."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def get_default_cache(
        self,
        max_pools: int = DEFAULT_MAX_POOLS,
        max_size_mb: Optional[float] = None,
        persist: bool = False,
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
        with self._cache_lock:
            if self._default_cache is None:
                self._default_cache = PoolMetadataCache(
                    max_pools=max_pools,
                    max_size_mb=max_size_mb,
                    persist=persist,
                    cache_dir=cache_dir or DEFAULT_CACHE_DIR,
                )
                logger.info("Created new default cache instance")
            else:
                logger.info("Using existing default cache instance")
                # Log current cache stats
                stats = self._default_cache.get_stats()
                logger.info(
                    f"Cache stats: {stats['entries']}/{stats['max_entries']} entries ({stats['usage_percent']:.1f}% full, ~{stats['approx_size_mb']:.2f}MB)"
                )

            return self._default_cache

    def delete_default_cache(self) -> bool:
        """
        Delete the default cache database file.

        Returns:
            bool: True if deletion was successful, False otherwise
        """
        try:
            db_path = DEFAULT_CACHE_DIR / DEFAULT_DB_FILENAME
            if db_path.exists():
                # Close the existing cache connection if it exists
                if self._default_cache is not None:
                    self._default_cache.close()
                self._default_cache = None
                db_path.unlink()
                logger.info(f"Deleted default cache at {db_path}")
                return True
            return False
        except Exception as e:
            logger.error(f"Error deleting default cache: {e}")
            return False

    def reset(self):
        """Reset the cache manager state (useful for testing)."""
        with self._cache_lock:
            if self._default_cache is not None:
                self._default_cache.close()
            self._default_cache = None


# Convenience functions that use CacheManager
def get_default_cache(
    max_pools: int = DEFAULT_MAX_POOLS,
    max_size_mb: Optional[float] = None,
    persist: bool = False,
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
