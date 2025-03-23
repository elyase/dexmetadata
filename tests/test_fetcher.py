"""
Tests for the fetcher module.
"""

import pytest

from dexmetadata.fetcher import is_valid_metadata


class TestMetadataValidation:
    """Tests for the metadata validation function."""

    def test_invalid_balancer_pool(self):
        """Test that a Balancer pool with null addresses and no token info is invalid."""
        balancer_metadata = {
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

        # The metadata should be invalid because both tokens have null addresses
        # and no names/symbols
        assert not is_valid_metadata(balancer_metadata)

    def test_valid_uniswap_v4_pool(self):
        """Test that a Uniswap v4 pool with null addresses but ETH token info is valid."""
        uniswap_v4_metadata = {
            "pool_address": "0x9c5edc768b5db73bf71856dc7d79bcc8368d7a4d3ded2091a20010f089cb0e74",
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

        # The metadata should be valid because even though both tokens have null addresses,
        # it's a Uniswap v4 pool and they have proper ETH names/symbols
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

        # The metadata should be valid because both tokens have real addresses and token info
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

        # The metadata should be invalid because token0 has a null address and it's not a v4 pool
        assert not is_valid_metadata(invalid_metadata)

    def test_mixed_v4_pool(self):
        """Test a Uniswap v4 pool with one null address and one regular address."""
        mixed_v4_metadata = {
            "pool_address": "0x9c5edc768b5db73bf71856dc7d79bcc8368d7a4d3ded2091a20010f089cb0e74",
            "pool_id": "0x9c5edc768b5db73bf71856dc7d79bcc8368d7a4d3ded2091a20010f089cb0e74",
            "is_uniswap_v4": True,
            "token0_address": "0x0000000000000000000000000000000000000000",
            "token0_name": "Ether",
            "token0_symbol": "ETH",
            "token0_decimals": 18,
            "token1_address": "0x1111111111111111111111111111111111111111",
            "token1_name": "USD Coin",
            "token1_symbol": "USDC",
            "token1_decimals": 6,
        }

        # The metadata should be valid because token0 has a null address but has ETH info,
        # and token1 has a valid address
        assert is_valid_metadata(mixed_v4_metadata)

    def test_none_metadata(self):
        """Test that None metadata is invalid."""
        assert not is_valid_metadata(None)

    def test_empty_metadata(self):
        """Test that empty metadata is invalid."""
        assert not is_valid_metadata({})
