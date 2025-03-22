"""
Tests for the CLI tools in dexmetadata.
"""

import json
import sys
from io import StringIO
from unittest.mock import patch

import pytest

from dexmetadata.cache import (
    DEFAULT_DB_FILENAME,
)
from dexmetadata.cli import cache_clear_cli, cache_info_cli, fetch_cli
from dexmetadata.models import Pool, Token


# Fixture for test pool data
@pytest.fixture
def test_pool():
    token0 = Token(
        address="0x833589fcd6edb6e08f4c7c32d4f71b54bda02913",
        name="USD Coin",
        symbol="USDC",
        decimals=6,
    )
    token1 = Token(
        address="0xcbb7c0000ab88b473b1f5afd9ef808440eed33bf",
        name="Coinbase Wrapped BTC",
        symbol="cbBTC",
        decimals=8,
    )
    return Pool(
        address="0xfBB6Eed8e7aa03B138556eeDaF5D271A5E1e43ef",
        token0=token0,
        token1=token1,
    )


def test_fetch_cli_console_output(test_pool, monkeypatch):
    """Test the fetch CLI command with console output."""
    # Mock the fetch function
    with patch("dexmetadata.cli.fetch", return_value=[test_pool]):
        # Capture stdout
        stdout_capture = StringIO()
        monkeypatch.setattr(sys, "stdout", stdout_capture)

        # Call the CLI function
        fetch_cli(
            pool_addresses=["0xfBB6Eed8e7aa03B138556eeDaF5D271A5E1e43ef"],
            network="base",
            rpc_url=None,
            batch_size=30,
            max_concurrent_batches=25,
            show_progress=True,
            output_file=None,
            output_format="text",
            use_cache=True,
            cache_max_pools=10000,
            cache_persist=False,
        )

        # Check output
        output = stdout_capture.getvalue()
        assert "Fetched 1 pools" in output
        assert "USDC" in output
        assert "cbBTC" in output
        assert "0xfBB6Eed8e7aa03B138556eeDaF5D271A5E1e43ef" in output


def test_fetch_cli_json_output(test_pool, monkeypatch, tmp_path):
    """Test the fetch CLI command with JSON file output."""
    # Set up a temporary file
    output_file = tmp_path / "pools.json"

    # Mock the fetch function
    with patch("dexmetadata.cli.fetch", return_value=[test_pool]):
        # Capture stdout
        stdout_capture = StringIO()
        monkeypatch.setattr(sys, "stdout", stdout_capture)

        # Call the CLI function with json output
        fetch_cli(
            pool_addresses=["0xfBB6Eed8e7aa03B138556eeDaF5D271A5E1e43ef"],
            network="base",
            rpc_url=None,
            batch_size=30,
            max_concurrent_batches=25,
            show_progress=True,
            output_file=str(output_file),
            output_format="json",
            use_cache=True,
            cache_max_pools=10000,
            cache_persist=False,
        )

        # Check that the file was created
        assert output_file.exists()

        # Check file content
        with open(output_file) as f:
            data = json.load(f)
            assert len(data) == 1
            assert (
                data[0]["pool_address"] == "0xfBB6Eed8e7aa03B138556eeDaF5D271A5E1e43ef"
            )
            assert data[0]["token0_symbol"] == "USDC"
            assert data[0]["token1_symbol"] == "cbBTC"


def test_fetch_cli_csv_output(test_pool, monkeypatch, tmp_path):
    """Test the fetch CLI command with CSV file output."""
    # Set up a temporary file
    output_file = tmp_path / "pools.csv"

    # Mock the fetch function
    with patch("dexmetadata.cli.fetch", return_value=[test_pool]):
        # Capture stdout
        stdout_capture = StringIO()
        monkeypatch.setattr(sys, "stdout", stdout_capture)

        # Call the CLI function with csv output
        fetch_cli(
            pool_addresses=["0xfBB6Eed8e7aa03B138556eeDaF5D271A5E1e43ef"],
            network="base",
            rpc_url=None,
            batch_size=30,
            max_concurrent_batches=25,
            show_progress=True,
            output_file=str(output_file),
            output_format="csv",
            use_cache=True,
            cache_max_pools=10000,
            cache_persist=False,
        )

        # Check that the file was created
        assert output_file.exists()

        # Check file content
        import csv

        with open(output_file) as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            assert len(rows) == 1
            assert (
                rows[0]["pool_address"] == "0xfBB6Eed8e7aa03B138556eeDaF5D271A5E1e43ef"
            )
            assert rows[0]["token0_symbol"] == "USDC"
            assert rows[0]["token1_symbol"] == "cbBTC"


def test_fetch_cli_empty_results(monkeypatch):
    """Test the fetch CLI command with no results."""
    # Mock the fetch function to return empty list
    with patch("dexmetadata.cli.fetch", return_value=[]):
        # Capture stdout
        stdout_capture = StringIO()
        monkeypatch.setattr(sys, "stdout", stdout_capture)

        # Call the CLI function
        fetch_cli(
            pool_addresses=["0x1234567890123456789012345678901234567890"],
            network="base",
            rpc_url=None,
            batch_size=30,
            max_concurrent_batches=25,
            show_progress=True,
            output_file=None,
            output_format="text",
            use_cache=True,
            cache_max_pools=10000,
            cache_persist=False,
        )

        # Check output
        output = stdout_capture.getvalue()
        assert "Fetched 0 pools" in output
        assert "No pools found" in output


def test_cli_info(tmp_path, monkeypatch):
    """Test the 'cache-info' command of the CLI."""
    # Configure default cache to use tmp_path in both modules
    monkeypatch.setattr("dexmetadata.cache.DEFAULT_CACHE_DIR", tmp_path)
    monkeypatch.setattr("dexmetadata.cli.DEFAULT_CACHE_DIR", tmp_path)

    # Create db directory if it doesn't exist
    tmp_path.mkdir(exist_ok=True, parents=True)

    # Create a test cache instance and add data
    test_data = {
        "pool_address": "0x1234567890123456789012345678901234567890",
        "token0_symbol": "TEST",
        "token1_symbol": "USDC",
    }

    # Get a cache instance and add the test data
    from dexmetadata.cache import CacheManager, get_default_cache

    # Reset any existing cache manager state
    CacheManager.get_instance().reset()

    # Create a new cache with persistence enabled
    cache = get_default_cache(persist=True)
    cache.put("0x1234567890123456789012345678901234567890", test_data)

    # Force a database write by closing the cache
    cache.close()

    # Verify the database file exists
    db_path = tmp_path / DEFAULT_DB_FILENAME
    assert db_path.exists(), f"Database file {db_path} doesn't exist"

    # Capture stdout
    stdout_capture = StringIO()
    monkeypatch.setattr(sys, "stdout", stdout_capture)

    # Call the CLI function
    cache_info_cli()

    # Check output
    output = stdout_capture.getvalue()
    assert "DexMetadata Cache Information" in output
    assert str(tmp_path) in output  # Check that our tmp_path is shown
    assert "Database File:" in output
    assert "Entries: 1" in output  # Check that we have exactly one entry
    assert "0x1234567890123456789012345678901234567890" in output


def test_cli_clear(tmp_path, monkeypatch):
    """Test the 'cache-clear' command of the CLI."""
    # Configure default cache to use tmp_path
    monkeypatch.setattr("dexmetadata.cache.DEFAULT_CACHE_DIR", tmp_path)

    # Create a test cache instance and add data
    test_data = {
        "pool_address": "0x1234567890123456789012345678901234567890",
        "token0_symbol": "TEST",
        "token1_symbol": "USDC",
    }

    # Get a cache instance and add the test data
    from dexmetadata.cache import CacheManager, get_default_cache

    cache = get_default_cache(persist=True, cache_dir=tmp_path)
    cache.put("0x1234567890123456789012345678901234567890", test_data)

    # Verify data was added
    assert len(cache) == 1

    # Reset the CacheManager instance for clean test
    CacheManager.get_instance().reset()

    # Capture stdout
    stdout_capture = StringIO()
    monkeypatch.setattr(sys, "stdout", stdout_capture)

    # Call the CLI function
    cache_clear_cli()

    # Get a new cache instance and verify it's empty
    new_cache = get_default_cache(persist=True, cache_dir=tmp_path)
    assert len(new_cache) == 0

    # Check output
    output = stdout_capture.getvalue()
    assert "Cache cleared successfully" in output
