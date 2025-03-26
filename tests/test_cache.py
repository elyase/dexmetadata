"""
Test specifically for the cache fix for dual key lookups.
This tests only the fixed behavior without requiring the full validation.
"""

import pytest
import tempfile
from pathlib import Path

from dexmetadata.fetcher import MetadataFetcher


class MockCache:
    """Mock cache that simulates the dual key issue."""
    
    def __init__(self):
        self.store = {}
        
    def get(self, key):
        return self.store.get(key)
        
    def get_many(self, keys):
        return {k: self.store[k] for k in keys if k in self.store}
        
    def put(self, key, value):
        self.store[key] = value
        
    def put_many(self, data_dict):
        self.store.update(data_dict)
        
    def chain_specific_key(self, key, chain_id):
        return f"{chain_id}:{key}"


def test_dual_key_lookup():
    """Test that the fetcher can find data with both standard and chain-specific keys."""
    # Setup test data
    pool_ids = ["0xabc123", "0xdef456", "0xghi789"]
    
    # Create a mock cache with data stored under different key formats
    mock_cache = MockCache()
    
    # Store data with standard key
    mock_cache.put("0xabc123", {"id": "0xabc123", "data": "standard key"})
    
    # Store data with chain-specific key
    mock_cache.put("1:0xdef456", {"id": "0xdef456", "data": "chain key"})
    
    # Create fetcher with this cache
    fetcher = MetadataFetcher(
        pool_identifiers=pool_ids,
        rpc_url="dummy_url",
        chain_id=1,
        use_cache=True
    )
    fetcher.cache = mock_cache
    
    # Get results using our fixed implementation
    results = fetcher.get_cached_results(pool_ids)
    
    # Verify findings
    assert len(results) == 2  # Should find both items
    assert "0xabc123" in results
    assert "0xdef456" in results
    assert results["0xabc123"]["data"] == "standard key"
    assert results["0xdef456"]["data"] == "chain key"
    assert "0xghi789" not in results  # Not in cache at all


def test_priority_order():
    """Test that standard keys take priority over chain-specific keys."""
    # Create a mock cache with duplicate data under different key formats
    mock_cache = MockCache()
    
    # Add the same pool under both key formats with different data
    mock_cache.put("0xabc123", {"id": "0xabc123", "source": "standard"})
    mock_cache.put("1:0xabc123", {"id": "0xabc123", "source": "chain"})
    
    # Create fetcher
    fetcher = MetadataFetcher(
        pool_identifiers=["0xabc123"],
        rpc_url="dummy_url",
        chain_id=1,
        use_cache=True
    )
    fetcher.cache = mock_cache
    
    # Get results using our fixed implementation
    results = fetcher.get_cached_results(["0xabc123"])
    
    # Verify the standard key takes priority (this is by design in our fix)
    assert len(results) == 1
    assert results["0xabc123"]["source"] == "standard"


def test_chain_id_isolation():
    """Test that chain IDs isolate cache entries properly."""
    # Create a mock cache with entries for different chains
    mock_cache = MockCache()
    
    # Add data for chain 1
    mock_cache.put("1:0xabc123", {"id": "0xabc123", "chain": 1})
    
    # Add data for chain 8453 (Base)
    mock_cache.put("8453:0xabc123", {"id": "0xabc123", "chain": 8453})
    
    # Create fetcher for chain 1
    fetcher1 = MetadataFetcher(
        pool_identifiers=["0xabc123"],
        rpc_url="dummy_url",
        chain_id=1,
        use_cache=True
    )
    fetcher1.cache = mock_cache
    
    # Create fetcher for chain 8453
    fetcher8453 = MetadataFetcher(
        pool_identifiers=["0xabc123"],
        rpc_url="dummy_url",
        chain_id=8453,
        use_cache=True
    )
    fetcher8453.cache = mock_cache
    
    # Get results for each chain
    results1 = fetcher1.get_cached_results(["0xabc123"])
    results8453 = fetcher8453.get_cached_results(["0xabc123"])
    
    # Verify chain isolation works
    assert len(results1) == 1
    assert len(results8453) == 1
    assert results1["0xabc123"]["chain"] == 1
    assert results8453["0xabc123"]["chain"] == 8453