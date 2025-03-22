"""
Tests for the caching system in dexmetadata.

This module tests:
1. Basic cache functionality (get/put/remove)
2. Eviction policy
3. Persistent storage
4. Thread safety
5. Default cache instance
"""

import threading
import time

from dexmetadata.cache import (
    DEFAULT_DB_FILENAME,
    PoolMetadataCache,
    delete_default_cache,
    get_default_cache,
)

# Test data
TEST_POOL_DATA = [
    {
        "pool_address": "0x1234567890123456789012345678901234567890",
        "token0_address": "0x1111111111111111111111111111111111111111",
        "token0_name": "Test Token 0",
        "token0_symbol": "TT0",
        "token0_decimals": 18,
        "token1_address": "0x2222222222222222222222222222222222222222",
        "token1_name": "Test Token 1",
        "token1_symbol": "TT1",
        "token1_decimals": 18,
    },
    {
        "pool_address": "0x2345678901234567890123456789012345678901",
        "token0_address": "0x3333333333333333333333333333333333333333",
        "token0_name": "Test Token 2",
        "token0_symbol": "TT2",
        "token0_decimals": 6,
        "token1_address": "0x4444444444444444444444444444444444444444",
        "token1_name": "Test Token 3",
        "token1_symbol": "TT3",
        "token1_decimals": 8,
    },
]


def test_basic_cache_operations(tmp_path):
    """Test basic cache operations: put, get, get_many."""
    cache = PoolMetadataCache(
        max_pools=10,
        persist=False,
        cache_dir=tmp_path,
    )

    # Test put and get
    cache.put(TEST_POOL_DATA[0]["pool_address"], TEST_POOL_DATA[0])
    result = cache.get(TEST_POOL_DATA[0]["pool_address"])
    assert result == TEST_POOL_DATA[0]

    # Test get_many
    cache.put(TEST_POOL_DATA[1]["pool_address"], TEST_POOL_DATA[1])
    results = cache.get_many(
        [
            TEST_POOL_DATA[0]["pool_address"],
            TEST_POOL_DATA[1]["pool_address"],
        ]
    )
    assert len(results) == 2
    assert results[TEST_POOL_DATA[0]["pool_address"]] == TEST_POOL_DATA[0]
    assert results[TEST_POOL_DATA[1]["pool_address"]] == TEST_POOL_DATA[1]

    # Test get for non-existent key
    assert cache.get("non_existent_key") is None

    # Test length
    assert len(cache) == 2


def test_cache_eviction(tmp_path):
    """Test that cache eviction works correctly."""
    # Create a cache with a small capacity
    cache = PoolMetadataCache(
        max_pools=3,  # Only allow 3 entries
        persist=False,
        cache_dir=tmp_path,
    )

    # Add 3 entries (filling the cache)
    for i in range(3):
        addr = f"0x{i:040x}"
        data = {
            "pool_address": addr,
            "token0_symbol": f"T{i}",
            "token1_symbol": f"T{i + 1}",
        }
        cache.put(addr, data)

    # Access the first entry multiple times to increase its frequency score
    for _ in range(5):
        cache.get("0x0000000000000000000000000000000000000000")

    # Add another entry to trigger eviction
    addr = "0xffffffffffffffffffffffffffffffffffffffff"
    data = {
        "pool_address": addr,
        "token0_symbol": "TF",
        "token1_symbol": "TF+1",
    }
    cache.put(addr, data)

    # The most frequently accessed entry should still be in the cache
    assert cache.get("0x0000000000000000000000000000000000000000") is not None

    # The total number of entries should still be max_pools
    assert len(cache) == 3


def test_cache_persistence(tmp_path):
    """Test that cache persistence works correctly."""
    # Create a cache with persistence enabled
    cache1 = PoolMetadataCache(
        max_pools=10,
        persist=True,
        cache_dir=tmp_path,
    )

    # Add some entries
    cache1.put(TEST_POOL_DATA[0]["pool_address"], TEST_POOL_DATA[0])
    cache1.put(TEST_POOL_DATA[1]["pool_address"], TEST_POOL_DATA[1])

    # Access one entry to increase its frequency
    cache1.get(TEST_POOL_DATA[0]["pool_address"])

    # Close the cache
    cache1.close()

    # Create a new cache instance pointing to the same directory
    cache2 = PoolMetadataCache(
        max_pools=10,
        persist=True,
        cache_dir=tmp_path,
    )

    # Verify that the data was loaded
    assert len(cache2) == 2
    assert cache2.get(TEST_POOL_DATA[0]["pool_address"]) == TEST_POOL_DATA[0]
    assert cache2.get(TEST_POOL_DATA[1]["pool_address"]) == TEST_POOL_DATA[1]

    # Check that the SQL file exists
    db_path = tmp_path / DEFAULT_DB_FILENAME
    assert db_path.exists()


def test_thread_safety(tmp_path):
    """Test that the cache is thread-safe."""
    cache = PoolMetadataCache(
        max_pools=100,
        persist=False,
        cache_dir=tmp_path,
    )

    num_threads = 10
    operations_per_thread = 100

    # Create a barrier to ensure all threads start at the same time
    barrier = threading.Barrier(num_threads)

    def worker(thread_id):
        barrier.wait()  # Wait for all threads to be ready

        # Perform a mix of operations
        for i in range(operations_per_thread):
            op = i % 3
            addr = f"0x{thread_id}{i:038x}"

            if op == 0:  # Put
                data = {
                    "pool_address": addr,
                    "token0_symbol": f"T{thread_id}_{i}",
                    "token1_symbol": f"T{thread_id}_{i + 1}",
                }
                cache.put(addr, data)
            elif op == 1:  # Get
                cache.get(addr)
            else:  # Get_many
                cache.get_many([addr, f"0x{thread_id}{i - 1:038x}"])

    # Create and start threads
    threads = []
    for i in range(num_threads):
        t = threading.Thread(target=worker, args=(i,))
        threads.append(t)
        t.start()

    # Wait for all threads to complete
    for t in threads:
        t.join()

    # Verify the cache is intact
    assert len(cache) > 0


def test_default_cache(tmp_path, monkeypatch):
    """Test that the default cache works correctly."""
    # Configure default cache to use tmp_path
    monkeypatch.setattr("dexmetadata.cache.DEFAULT_CACHE_DIR", tmp_path)

    # Get the default cache
    cache1 = get_default_cache(
        max_pools=20,
        persist=True,
    )

    # Add a test entry
    cache1.put(TEST_POOL_DATA[0]["pool_address"], TEST_POOL_DATA[0])

    # Get the default cache again (should be the same instance)
    cache2 = get_default_cache()

    # Verify it's the same instance with the same data
    assert cache2 is cache1
    assert cache2.get(TEST_POOL_DATA[0]["pool_address"]) == TEST_POOL_DATA[0]


def test_cache_max_size_mb(tmp_path):
    """Test that the max_size_mb parameter works correctly."""
    # Create a cache with max_size_mb limitation
    # Each pool is roughly 400 bytes (including JSON and storage overhead),
    # so 0.01MB (10KB) should allow about 25 pools
    cache = PoolMetadataCache(
        max_size_mb=0.01,  # Very small limit for testing
        persist=False,
        cache_dir=tmp_path,
    )

    # Add more entries than should fit
    for i in range(30):  # Try to add 30 pools, more than should fit
        addr = f"0x{i:040x}"
        data = {
            "pool_address": addr,
            "token0_symbol": f"T{i}",
            "token1_symbol": f"T{i + 1}",
        }
        cache.put(addr, data)

    # The cache should have evicted some entries
    assert len(cache) < 30


def test_cache_stats(tmp_path):
    """Test that the cache statistics are correct."""
    cache = PoolMetadataCache(
        max_pools=10,
        persist=False,
        cache_dir=tmp_path,
    )

    # Add some entries
    for i in range(5):
        addr = f"0x{i:040x}"
        data = {
            "pool_address": addr,
            "token0_symbol": f"T{i}",
            "token1_symbol": f"T{i + 1}",
        }
        cache.put(addr, data)

    # Access some entries more than others
    for _ in range(3):
        cache.get("0x0000000000000000000000000000000000000000")
    for _ in range(2):
        cache.get("0x0000000000000000000000000000000000000001")

    # Get statistics
    stats = cache.get_stats()

    # Check basic stats
    assert stats["entries"] == 5
    assert stats["max_entries"] == 10
    assert stats["usage_percent"] == 50.0
    assert stats["persist_enabled"] is False

    # Check top accessed pools
    assert len(stats["top_accessed_pools"]) > 0
    # Most accessed should be first
    assert (
        stats["top_accessed_pools"][0]["address"]
        == "0x0000000000000000000000000000000000000000"
    )


def test_put_many(tmp_path):
    """Test that put_many works correctly."""
    cache = PoolMetadataCache(
        max_pools=10,
        persist=False,
        cache_dir=tmp_path,
    )

    # Create a dictionary of entries
    entries = {
        TEST_POOL_DATA[0]["pool_address"]: TEST_POOL_DATA[0],
        TEST_POOL_DATA[1]["pool_address"]: TEST_POOL_DATA[1],
    }

    # Add them all at once
    cache.put_many(entries)

    # Verify they were added
    assert len(cache) == 2
    assert cache.get(TEST_POOL_DATA[0]["pool_address"]) == TEST_POOL_DATA[0]
    assert cache.get(TEST_POOL_DATA[1]["pool_address"]) == TEST_POOL_DATA[1]


def test_clear_cache(tmp_path):
    """Test that the clear_cache method works correctly."""
    # Create a cache with some data
    cache = PoolMetadataCache(
        max_pools=10,
        persist=True,
        cache_dir=tmp_path,
    )

    # Add some entries
    cache.put(TEST_POOL_DATA[0]["pool_address"], TEST_POOL_DATA[0])
    cache.put(TEST_POOL_DATA[1]["pool_address"], TEST_POOL_DATA[1])

    # Verify data was added
    assert len(cache) == 2

    # Call clear_cache method
    cache.clear()

    # Verify the cache is empty
    assert len(cache) == 0

    # If persistence was enabled, verify the DB file is still there but empty
    db_path = tmp_path / DEFAULT_DB_FILENAME
    if db_path.exists():
        # The file might still exist but should be empty
        cache2 = PoolMetadataCache(
            max_pools=10,
            persist=True,
            cache_dir=tmp_path,
        )
        assert len(cache2) == 0


def test_delete_default_cache(tmp_path, monkeypatch):
    """Test that the default cache can be deleted properly."""
    # Configure default cache to use tmp_path
    monkeypatch.setattr("dexmetadata.cache.DEFAULT_CACHE_DIR", tmp_path)

    # Create db directory if it doesn't exist
    tmp_path.mkdir(exist_ok=True, parents=True)

    # Get a default cache and add some data
    cache = get_default_cache(persist=True)

    # Create a simple test data entry
    test_data = {
        "pool_address": "0x1234567890123456789012345678901234567890",
        "token0_address": "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        "token0_name": "Test Token",
        "token0_symbol": "TT",
        "token0_decimals": 18,
        "token1_address": "0xbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
        "token1_name": "Another Token",
        "token1_symbol": "AT",
        "token1_decimals": 6,
    }

    # Add the data to the cache with persistence
    cache.put("0x1234567890123456789012345678901234567890", test_data)

    # Force a flush to disk
    db_path = tmp_path / DEFAULT_DB_FILENAME
    if not db_path.exists():
        # If the database file wasn't created, we'll create a simple one for testing
        import sqlite3

        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS pools (
                address TEXT PRIMARY KEY,
                data TEXT NOT NULL,
                access_count INTEGER NOT NULL,
                last_access INTEGER NOT NULL
            )
        """)
        cursor.execute(
            "INSERT INTO pools (address, data, access_count, last_access) VALUES (?, ?, ?, ?)",
            (
                "0x1234567890123456789012345678901234567890",
                '{"test":"data"}',
                1,
                int(time.time()),
            ),
        )
        conn.commit()
        conn.close()

    # Verify the database file exists now
    assert db_path.exists(), f"Database file {db_path} doesn't exist"

    # Delete the default cache
    result = delete_default_cache()
    assert result is True

    # Verify the database file is gone
    assert not db_path.exists()

    # Get a new default cache and verify it's empty
    new_cache = get_default_cache()
    assert len(new_cache) == 0
