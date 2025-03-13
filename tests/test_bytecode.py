"""
Simple test for the bytecode module using pytest.

This test showcases the core functionality of the bytecode module:
1. Loading bytecode from a contract file
2. Caching mechanism
3. Hash-based file naming
4. Basic error handling
5. Auto-compilation on code changes
"""

import hashlib

import pytest

from dexmetadata import bytecode
from dexmetadata.bytecode import load_bytecode


@pytest.fixture
def contract_setup(tmp_path):
    """Create a minimal contract and its corresponding bytecode file."""
    # Simple contract that just returns a constant
    contract_content = """
    // SPDX-License-Identifier: MIT
    pragma solidity ^0.8.0;
    
    contract MinimalContract {
        function get() public pure returns (uint256) {
            return 42;
        }
    }
    """

    # Create contract file
    contract_path = tmp_path / "MinimalContract.sol"
    contract_path.write_text(contract_content)

    # Create bytecode file with hash-based name
    contract_hash = hashlib.sha256(contract_content.encode()).hexdigest()[:8]
    bytecode = "0x608060405234801561001057600080fd5b50610150808203905b610000"  # Minimal example bytecode
    bin_path = tmp_path / f"MinimalContract.{contract_hash}.bin"
    bin_path.write_text(bytecode)

    return {
        "contract_path": contract_path,
        "bin_path": bin_path,
        "bytecode": bytecode,
        "hash": contract_hash,
        "content": contract_content,
    }


@pytest.fixture
def auto_compilation_setup(tmp_path):
    """Create a separate contract for testing auto-compilation."""
    # Simple contract that just returns a constant
    contract_content = """
    // SPDX-License-Identifier: MIT
    pragma solidity ^0.8.0;
    
    contract AutoCompileTest {
        function get() public pure returns (uint256) {
            return 42;
        }
    }
    """

    # Create contract file
    contract_path = tmp_path / "AutoCompileTest.sol"
    contract_path.write_text(contract_content)

    # Create bytecode file with hash-based name
    contract_hash = hashlib.sha256(contract_content.encode()).hexdigest()[:8]
    bytecode = "0x608060405234801561001057600080fd5b50610150808203905b610000"  # Minimal example bytecode
    bin_path = tmp_path / f"AutoCompileTest.{contract_hash}.bin"
    bin_path.write_text(bytecode)

    return {
        "contract_path": contract_path,
        "bin_path": bin_path,
        "bytecode": bytecode,
        "hash": contract_hash,
        "content": contract_content,
    }


def test_bytecode_core_functionality(contract_setup):
    """Test the core functionality of the bytecode module."""
    # 1. Test basic loading
    bytecode = load_bytecode(contract_setup["contract_path"])
    assert bytecode == contract_setup["bytecode"], "Should load correct bytecode"

    # 2. Test caching (second load should use cache)
    cached_bytecode = load_bytecode(contract_setup["contract_path"])
    assert cached_bytecode == bytecode, "Cached bytecode should match"

    # 3. Test hash-based file naming
    bin_files = list(contract_setup["contract_path"].parent.glob("*.bin"))
    assert len(bin_files) == 1, "Should have exactly one bin file"
    assert bin_files[0].name == f"MinimalContract.{contract_setup['hash']}.bin"

    # 4. Test error handling
    non_existent = contract_setup["contract_path"].parent / "NonExistent.sol"
    assert load_bytecode(non_existent) is None, "Should handle missing files gracefully"


def test_bytecode_auto_compilation(auto_compilation_setup, monkeypatch):
    """Test that bytecode is automatically recompiled when contract changes."""
    # First load the original bytecode
    original_bytecode = load_bytecode(auto_compilation_setup["contract_path"])
    assert original_bytecode == auto_compilation_setup["bytecode"]

    # Modify the contract - change return value from 42 to 1337
    modified_content = auto_compilation_setup["content"].replace(
        "return 42", "return 1337"
    )
    auto_compilation_setup["contract_path"].write_text(modified_content)

    # Clear the bytecode cache for this contract
    contract_path_str = str(auto_compilation_setup["contract_path"])
    if contract_path_str in bytecode._bytecode_cache:
        del bytecode._bytecode_cache[contract_path_str]

    # Mock the compilation using monkeypatch
    mock_bytecode = "0x608060405234801561001057600080fd5b50610150808203905b610001"  # Slightly different
    monkeypatch.setattr(bytecode, "_compile_contract", lambda _: mock_bytecode)

    # Load bytecode again - should trigger recompilation
    new_bytecode = load_bytecode(auto_compilation_setup["contract_path"])

    # Should get the new bytecode
    assert new_bytecode == mock_bytecode, "Should get recompiled bytecode"
    assert new_bytecode != original_bytecode, "New bytecode should be different"

    # Check that a new bin file was created with correct hash
    new_hash = hashlib.sha256(modified_content.encode()).hexdigest()[:8]
    new_bin_path = (
        auto_compilation_setup["contract_path"].parent
        / f"AutoCompileTest.{new_hash}.bin"
    )
    assert new_bin_path.exists(), "New bin file should be created"
    assert new_bin_path.read_text() == mock_bytecode, (
        "New bin file should contain new bytecode"
    )
