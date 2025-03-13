from unittest.mock import patch

import pytest
from dexmetadata.decoder import decode_metadata_response
from eth_abi import encode


def test_decode_metadata_response_empty():
    """Test decoding with empty response."""
    # Test with empty bytes
    result = decode_metadata_response(b"")
    assert isinstance(result, list)
    assert len(result) == 0


def test_decode_metadata_response_invalid():
    """Test decoding with invalid response."""
    # Test with some random bytes that aren't valid ABI-encoded data
    result = decode_metadata_response(b"\x01\x02\x03")
    assert isinstance(result, list)
    assert len(result) == 0


def test_decode_metadata_response_valid():
    """Test decoding with valid response data."""
    # Create a sample encoded response that matches our expected format
    # Prepare structured data that matches our contract's output format

    # Define token0 data (address, name, symbol, decimals)
    token0 = (
        "0x1111111111111111111111111111111111111111",  # address
        "Token A",  # name
        "TKA",  # symbol
        18,  # decimals
    )

    # Define token1 data
    token1 = ("0x2222222222222222222222222222222222222222", "Token B", "TKB", 6)

    # Pool metadata (poolAddress, token0, token1)
    pool_data = ("0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", token0, token1)

    # Create an array with one pool entry
    pool_array = [pool_data]

    # Encode the data using the exact type string from bytecode.py
    encoded_data = encode(
        ["(address,(address,string,string,uint8),(address,string,string,uint8))[]"],
        [pool_array],
    )

    # Decode the response
    result = decode_metadata_response(encoded_data)

    # Verify the decoded result
    assert len(result) == 1
    pool_metadata = result[0]

    assert pool_metadata["pool_address"] == "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    assert (
        pool_metadata["token0_address"] == "0x1111111111111111111111111111111111111111"
    )
    assert pool_metadata["token0_name"] == "Token A"
    assert pool_metadata["token0_symbol"] == "TKA"
    assert pool_metadata["token0_decimals"] == 18
    assert (
        pool_metadata["token1_address"] == "0x2222222222222222222222222222222222222222"
    )
    assert pool_metadata["token1_name"] == "Token B"
    assert pool_metadata["token1_symbol"] == "TKB"
    assert pool_metadata["token1_decimals"] == 6
