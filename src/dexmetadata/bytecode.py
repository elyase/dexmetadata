"""
Module for loading and managing contract bytecode.

This module provides functions to load bytecode from Solidity contracts,
with automatic compilation and binary caching for efficient loading.
"""

import hashlib
import logging
import subprocess
from pathlib import Path
from typing import Dict, Optional

logger = logging.getLogger(__name__)

_bytecode_cache: Dict[str, str] = {}


def load_bytecode(contract_path: Path) -> Optional[str]:
    """
    Load bytecode from a Solidity contract, with automatic compilation and caching.

    This function:
    1. Calculates a hash of the contract source
    2. Looks for a corresponding hash-named .bin file
    3. If found, loads from the .bin file
    4. If not found, compiles the contract and saves to hash-named .bin

    Args:
        contract_path: Path to the Solidity .sol file

    Returns:
        The bytecode prefixed with '0x' or None if loading failed
    """
    # Check if contract exists
    if not contract_path.exists():
        print(f"Error: Contract file not found: {contract_path}")
        return None

    # Check memory cache first (fastest)
    contract_path_str = str(contract_path)
    if contract_path_str in _bytecode_cache:
        print(f"Using memory-cached bytecode for {contract_path.name}")
        return _bytecode_cache[contract_path_str]

    # Calculate source hash
    with open(contract_path, "rb") as f:
        source_hash = hashlib.sha256(f.read()).hexdigest()

    # Use the first 8 characters of the hash in the bin filename
    hash_prefix = source_hash[:8]
    bin_path = contract_path.parent / f"{contract_path.stem}.{hash_prefix}.bin"

    # Check if the hash-specific binary file exists
    if bin_path.exists():
        try:
            with open(bin_path, "r") as f:
                bytecode = f.read().strip()
                logger.debug(f"Loaded bytecode from {bin_path}")

                # Cache in memory
                _bytecode_cache[contract_path_str] = bytecode
                return bytecode
        except Exception as e:
            print(f"Error loading .bin file: {e}")
            # Fall through to compilation

    # If we get here, we need to compile
    bytecode = _compile_contract(contract_path)

    if bytecode:
        # Save to hash-based .bin file
        with open(bin_path, "w") as f:
            f.write(bytecode)

        print(f"Compiled and saved bytecode to {bin_path}")

        # Cache in memory
        _bytecode_cache[contract_path_str] = bytecode

    return bytecode


def _compile_contract(contract_path: Path) -> Optional[str]:
    """
    Compile a Solidity contract and return its bytecode.

    Args:
        contract_path: Path to the Solidity contract file

    Returns:
        The bytecode prefixed with '0x' or None if compilation failed
    """
    try:
        # Compile the contract
        result = subprocess.run(
            ["solc", "--bin", str(contract_path)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
            text=True,
        )

        # Parse the output to extract bytecode
        output_lines = result.stdout.strip().split("\n")
        bytecode = None
        main_contract = f"{contract_path.stem}.sol:{contract_path.stem}Fixed"

        # Look for the main contract's bytecode
        for i, line in enumerate(output_lines):
            if main_contract in line and i + 2 < len(output_lines):
                # Get the line after "Binary:"
                if output_lines[i + 1].strip() == "Binary:":
                    bytecode = output_lines[i + 2].strip()
                    break

        if not bytecode:
            print(f"Failed to find bytecode for {main_contract} in compiler output")
            print("Compiler output:")
            for line in output_lines:
                print(f"  {line}")
            return None

        # Prefix with 0x and return
        return f"0x{bytecode}"

    except subprocess.CalledProcessError as e:
        print(f"Error compiling Solidity contract: {e}")
        print(f"stderr: {e.stderr}")
        return None
    except Exception as e:
        print(f"Unexpected error compiling contract: {e}")
        return None


# Load the pool metadata fetcher bytecode
POOL_dexmetadata_BYTECODE = load_bytecode(
    Path(__file__).parent / "contracts" / "PoolMetadataFetcher.sol"
)

if not POOL_dexmetadata_BYTECODE:
    raise RuntimeError("Failed to load PoolMetadataFetcher bytecode")
