"""
Core functionality tests for dexmetadata library.

This file contains essential tests that verify the core functionality:
1. Data model conversion
2. Pool type handling (v3, v4, invalid)
3. Metadata validation
"""

import pytest
from dexmetadata.models import Pool, Token
from dexmetadata.utils import is_valid_metadata


def test_model_conversion():
    """
    Test the basic functionality of converting raw data to Pool objects.
    
    This is the fundamental operation of the library - taking raw metadata
    and converting it to structured Pool objects.
    """
    # Sample pool data (Uniswap v3 pool)
    pool_data = {
        "identifier": "0xfBB6Eed8e7aa03B138556eeDaF5D271A5E1e43ef",
        "pool_address": "0xfBB6Eed8e7aa03B138556eeDaF5D271A5E1e43ef",
        "token0_address": "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913",
        "token0_name": "USD Coin",
        "token0_symbol": "USDC",
        "token0_decimals": 6,
        "token1_address": "0xcbb7c0000ab88b473b1f5afd9ef808440eed33bf",
        "token1_name": "Coinbase Wrapped BTC",
        "token1_symbol": "cbBTC",
        "token1_decimals": 8,
        "protocol": "Uniswap v3"
    }
    
    # Convert to Pool object
    pool = Pool.from_dict(pool_data)
    
    # Verify core structure
    assert isinstance(pool, Pool)
    assert isinstance(pool.token0, Token)
    assert isinstance(pool.token1, Token)
    
    # Verify data was correctly transferred
    assert pool.identifier == pool_data["pool_address"]
    assert pool.protocol == "Uniswap v3"
    assert pool.is_valid == True
    
    # Verify token0 data
    assert pool.token0.address == pool_data["token0_address"]
    assert pool.token0.name == pool_data["token0_name"]
    assert pool.token0.symbol == pool_data["token0_symbol"]
    assert pool.token0.decimals == pool_data["token0_decimals"]
    
    # Verify token1 data
    assert pool.token1.address == pool_data["token1_address"]
    assert pool.token1.name == pool_data["token1_name"]
    assert pool.token1.symbol == pool_data["token1_symbol"]
    assert pool.token1.decimals == pool_data["token1_decimals"]


def test_invalid_pool_handling():
    """
    Test how the library handles invalid pools.
    
    This is important as the library needs to gracefully handle pools
    that don't exist or have invalid data.
    """
    # Invalid pool data
    invalid_pool_data = {
        "identifier": "0x123456789abcdef0123456789abcdef012345678",
        "pool_address": "0x123456789abcdef0123456789abcdef012345678",
        "is_valid": False
    }
    
    # Convert to Pool object
    invalid_pool = Pool.from_dict(invalid_pool_data)
    
    # Verify it's marked as invalid
    assert not invalid_pool.is_valid
    
    # Verify token placeholders are empty
    assert invalid_pool.token0.address == ""
    assert invalid_pool.token0.name == ""
    assert invalid_pool.token0.symbol == ""
    assert invalid_pool.token0.decimals == 0
    
    assert invalid_pool.token1.address == ""
    assert invalid_pool.token1.name == ""
    assert invalid_pool.token1.symbol == ""
    assert invalid_pool.token1.decimals == 0


def test_uniswap_v4_pool():
    """
    Test handling of Uniswap v4 pools, which use a different identifier format.
    
    This tests the library's ability to handle different types of DEX pools.
    """
    # Uniswap v4 pool data
    v4_pool_data = {
        "identifier": "0xe6195a1f1c8f5d0bcf0a880db26738a1df4f6863017700a8f6377a72d45366f2",
        "pool_id": "0xe6195a1f1c8f5d0bcf0a880db26738a1df4f6863017700a8f6377a72d45366f2", 
        "is_uniswap_v4": True,
        "token0_address": "0xcbb7c0000ab88b473b1f5afd9ef808440eed33bf",
        "token0_name": "Coinbase Wrapped BTC",
        "token0_symbol": "cbBTC",
        "token0_decimals": 8,
        "token1_address": "0x4200000000000000000000000000000000000006",
        "token1_name": "Ethereum",
        "token1_symbol": "ETH",
        "token1_decimals": 18,
        "protocol": "Uniswap v4"
    }
    
    # Convert to Pool object
    v4_pool = Pool.from_dict(v4_pool_data)
    
    # Verify core v4-specific data
    assert v4_pool.identifier == v4_pool_data["pool_id"]
    assert v4_pool.protocol == "Uniswap v4"
    assert v4_pool.is_valid == True
    
    # Verify token data
    assert v4_pool.token0.symbol == "cbBTC"
    assert v4_pool.token1.symbol == "ETH"


# Metadata validation tests from test_fetcher.py
class TestMetadataValidation:
    """Tests for the metadata validation function."""

    def test_invalid_with_null_addresses(self):
        """Test that pools with null token addresses are invalid."""
        metadata = {
            "pool_address": "0x2dbc9ab0160087ae59474fb7bed95b9e808fa6bc",
            "token0_address": "0x0000000000000000000000000000000000000000",
            "token0_name": "",
            "token0_symbol": "",
            "token0_decimals": 0,
            "token1_address": "0x0000000000000000000000000000000000000000",
            "token1_name": "",
            "token1_symbol": "",
            "token1_decimals": 0,
        }
        assert not is_valid_metadata(metadata)

    def test_valid_uniswap_v4_pool(self):
        """Test that a Uniswap v4 pool with null addresses but token info is valid."""
        uniswap_v4_metadata = {
            "pool_id": "0x9c5edc768b5db73bf71856dc7d79bcc8368d7a4d3ded2091a20010f089cb0e74",
            "is_uniswap_v4": True,
            "token0_address": "0x0000000000000000000000000000000000000000",
            "token0_name": "Ether",
            "token0_symbol": "ETH",
            "token0_decimals": 18,
            "token1_address": "0x0000000000000000000000000000000000000000",
            "token1_name": "Ether",
            "token1_symbol": "ETH",
            "token1_decimals": 18,
        }
        assert is_valid_metadata(uniswap_v4_metadata)

    def test_valid_normal_pool(self):
        """Test that a normal pool with real token addresses is valid."""
        normal_metadata = {
            "pool_address": "0xabcdef1234567890abcdef1234567890abcdef12",
            "token0_address": "0x1111111111111111111111111111111111111111",
            "token0_name": "Token A",
            "token0_symbol": "TKNA",
            "token0_decimals": 18,
            "token1_address": "0x2222222222222222222222222222222222222222",
            "token1_name": "Token B",
            "token1_symbol": "TKNB",
            "token1_decimals": 18,
        }
        assert is_valid_metadata(normal_metadata)

    def test_invalid_regular_pool_null_address(self):
        """Test that a non-v4 pool with a null address token is invalid."""
        invalid_metadata = {
            "pool_address": "0xabcdef1234567890abcdef1234567890abcdef12",
            "token0_address": "0x0000000000000000000000000000000000000000",  # null address
            "token0_name": "Some Name",
            "token0_symbol": "SYM",
            "token0_decimals": 18,
            "token1_address": "0x2222222222222222222222222222222222222222",
            "token1_name": "Token B",
            "token1_symbol": "TKNB",
            "token1_decimals": 18,
        }
        assert not is_valid_metadata(invalid_metadata)

    def test_empty_metadata(self):
        """Test that empty metadata is invalid."""
        assert not is_valid_metadata({})
        assert not is_valid_metadata(None)