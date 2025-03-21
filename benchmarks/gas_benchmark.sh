#!/bin/bash
# gas_benchmark.sh - Compare gas usage between contract versions
# This script measures gas and bytecode size differences between contract versions
# Located in benchmarks/ for development and optimization purposes

# Set RPC URL to match fetch.py
export ETH_RPC_URL="https://base-rpc.publicnode.com"

# Use just one pool address for testing
ADDRESS="0xfBB6Eed8e7aa03B138556eeDaF5D271A5E1e43ef"

# Create build directory if it doesn't exist
mkdir -p build

echo "Retrieving previous version from git..."
git show HEAD~1:src/dexmetadata/contracts/PoolMetadataFetcher.sol > build/PoolMetadataFetcher_original.sol

echo "Compiling contracts..."
# Compile original version
solc --bin --optimize build/PoolMetadataFetcher_original.sol -o build/ --overwrite
mv build/PoolMetadataFetcherFixed.bin build/PoolMetadataFetcher_original.bin

# Compile new version
solc --bin --optimize src/dexmetadata/contracts/PoolMetadataFetcher.sol -o build/ --overwrite

# Get the bytecode
echo "Extracting bytecode..."
OLD_BYTECODE=$(cat build/PoolMetadataFetcher_original.bin || echo "Error: Failed to read original bytecode")
NEW_BYTECODE=$(cat build/PoolMetadataFetcherFixed.bin || echo "Error: Failed to read new bytecode")

# Encode constructor arguments
echo "Encoding constructor arguments..."
CONSTRUCTOR_ARGS=$(cast abi-encode "constructor(address[])" "[$ADDRESS]")

# Estimate gas for deployments
echo "Estimating gas for previous version..."
OLD_GAS=$(cast estimate --create "0x${OLD_BYTECODE}${CONSTRUCTOR_ARGS#0x}")

echo "Estimating gas for new version..."
NEW_GAS=$(cast estimate --create "0x${NEW_BYTECODE}${CONSTRUCTOR_ARGS#0x}")

# Calculate savings
if [[ -n "$OLD_GAS" && -n "$NEW_GAS" ]]; then
    SAVED=$((OLD_GAS - NEW_GAS))
    PERCENT=$(echo "scale=2; $SAVED * 100 / $OLD_GAS" | bc)
else
    echo "Error: Failed to get gas estimates"
    exit 1
fi

# Print bytecode size comparison
OLD_SIZE=${#OLD_BYTECODE}
NEW_SIZE=${#NEW_BYTECODE}
SIZE_DIFF=$((OLD_SIZE - NEW_SIZE))
SIZE_PERCENT=$(echo "scale=2; $SIZE_DIFF * 100 / $OLD_SIZE" | bc)

echo "========================================="
echo "RESULTS"
echo "========================================="
echo "Original contract gas: $OLD_GAS"
echo "Optimized contract gas: $NEW_GAS"
echo "Gas saved: $SAVED ($PERCENT%)"
echo ""
echo "Original bytecode size: $OLD_SIZE"
echo "Optimized bytecode size: $NEW_SIZE"
echo "Size reduction: $SIZE_DIFF ($SIZE_PERCENT%)"
echo "=========================================" 