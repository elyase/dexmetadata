from eth_abi import encode

from dexmetadata.decoder import decode_metadata_response


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


def test_decode_uniswap_v4_metadata_native_token():
    """Test decoding Uniswap v4 pool data with native token (ETH) using real values."""
    # Register a test pool ID - use a real example from our testing
    from dexmetadata.decoder import register_pool_id

    # Real pool ID from Base chain
    full_pool_id = "0xe6195a1f1c8f5d0bcf0a880db26738a1df4f6863017700a8f6377a72d45366f2"
    register_pool_id(full_pool_id)

    # Create the first 25 bytes of the pool_id
    truncated_pool_id_bytes = bytes.fromhex(
        "e6195a1f1c8f5d0bcf0a880db26738a1df4f6863017700a8f6"
    )
    # Pad to 32 bytes for the ABI encoding
    pool_id_bytes = truncated_pool_id_bytes.ljust(32, b"\0")

    # Real cbBTC token data
    token0 = (
        "0xcbb7c0000ab88b473b1f5afd9ef808440eed33bf",  # address
        "Coinbase Wrapped BTC",  # name
        "cbBTC",  # symbol
        8,  # decimals
    )

    # Native token (ETH) - already properly encoded from the contract as zero address
    token1 = (
        "0x0000000000000000000000000000000000000000",  # address (zero address for native token)
        "Ether",  # name
        "ETH",  # symbol
        18,  # decimals
    )

    # Pool metadata (poolId, token0, token1)
    pool_data = (pool_id_bytes, token0, token1)

    # Create an array with one pool entry
    pool_array = [pool_data]

    # Encode the data using the Uniswap v4 type string
    encoded_data = encode(
        ["(bytes32,(address,string,string,uint8),(address,string,string,uint8))[]"],
        [pool_array],
    )

    # Decode the response
    result = decode_metadata_response(encoded_data)

    # Verify the decoded result
    assert len(result) == 1
    pool_metadata = result[0]

    assert pool_metadata["pool_id"] == full_pool_id
    assert pool_metadata["is_uniswap_v4"] is True
    assert (
        pool_metadata["token0_address"] == "0xcbb7c0000ab88b473b1f5afd9ef808440eed33bf"
    )
    assert pool_metadata["token0_name"] == "Coinbase Wrapped BTC"
    assert pool_metadata["token0_symbol"] == "cbBTC"
    assert pool_metadata["token0_decimals"] == 8

    # Check that token1 is correctly identified as a native token (zero address)
    assert (
        pool_metadata["token1_address"] == "0x0000000000000000000000000000000000000000"
    )
    assert pool_metadata["token1_name"] == "Ether"
    assert pool_metadata["token1_symbol"] == "ETH"
    assert pool_metadata["token1_decimals"] == 18
