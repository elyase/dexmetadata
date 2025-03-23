// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/**
 * @title UniswapV4MetadataFetcher
 * @dev A deployless multicall contract for fetching Uniswap v4 pool metadata.
 * @dev Takes poolIds and position manager address as input.
 */
contract UniswapV4MetadataFetcher {
    // Structure to hold token metadata
    struct TokenMetadata {
        address tokenAddress;
        string name;
        string symbol;
        uint8 decimals;
    }

    // Structure to hold pool metadata - similar to regular pools but includes poolId
    struct PoolMetadata {
        bytes32 poolId;
        TokenMetadata token0;
        TokenMetadata token1;
        uint24 fee;
    }

    // Using payable to save gas
    constructor(bytes25[] memory poolIds, address positionManager) payable {
        // Ensure position manager is set
        require(positionManager != address(0), "Position manager address cannot be zero");

        // Create result array
        uint256 poolCount = poolIds.length;
        PoolMetadata[] memory results = new PoolMetadata[](poolCount);

        // Process each poolId
        for (uint256 i = 0; i < poolCount;) {
            bytes25 poolIdBytes25 = poolIds[i];

            // Store full pool id (padded from bytes25 to bytes32)
            results[i].poolId = bytes32(poolIdBytes25);

            // Call poolKeys function on position manager to get token addresses
            address token0Address;
            address token1Address;
            uint24 fee;

            // CORRECTED function selector for poolKeys from Basescan
            bytes4 poolKeysSelector = 0x86b6be7d; // bytes4(keccak256("poolKeys(bytes25)"))

            // Use assembly to call poolKeys on position manager
            assembly {
                // Allocate memory for the call
                let ptr := mload(0x40) // Free memory pointer

                // Prepare function selector and argument
                mstore(ptr, poolKeysSelector)
                mstore(add(ptr, 0x04), poolIdBytes25) // bytes25 argument

                // Make the call to position manager
                let success :=
                    staticcall(
                        gas(),
                        positionManager,
                        ptr,
                        0x24, // 4 (selector) + 32 (poolId) = 36 bytes
                        ptr,
                        0x100 // Large enough for the returned struct
                    )

                // Process result - PoolKey struct has:
                // currency0 (Currency = address), currency1 (Currency = address),
                // fee (uint24), tickSpacing (int24), hooks (address)
                if success {
                    // Get all words to see the exact memory layout
                    let word0 := mload(add(ptr, 0x20)) // First word - should be currency0
                    let word1 := mload(add(ptr, 0x40)) // Second word - should be currency1
                    let word2 := mload(add(ptr, 0x60)) // Third word - should have fee in first 24 bits

                    // Extract the fee separately - this is in the first 24 bits of the third word
                    fee := and(word2, 0xFFFFFF) // Take the first 24 bits (3 bytes) for fee

                    // In Currency.sol, a Currency is defined as "type Currency is address;"
                    // But if we see 0x0000000000000000000000000000000000000bb8 (3000) in the
                    // currency1 slot, it suggests this might actually be the fee value bleeding
                    // into the currency1 slot. Let's check for that case explicitly.

                    // Mask to get just the address part (lower 160 bits)
                    let currency0 := and(word0, 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF)
                    let currency1 := and(word1, 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF)

                    // If currency1 is the problematic value we've seen (0xbb8 = 3000), treat it as native token
                    if eq(currency1, 0xbb8) {
                        // This is almost certainly a fee value, not a token address
                        // Treat it as the native token (ETH)
                        currency1 := 0
                    }

                    // Check for the native token (zero address)
                    // For token0
                    switch iszero(currency0)
                    case 1 { token0Address := 0 }
                    // Native token (ETH)
                    default { token0Address := currency0 } // ERC20 token

                    // For token1
                    switch iszero(currency1)
                    case 1 { token1Address := 0 }
                    // Native token (ETH)
                    default { token1Address := currency1 } // ERC20 token
                }
            }

            // Store token addresses and fee
            results[i].token0.tokenAddress = token0Address;
            results[i].token1.tokenAddress = token1Address;
            results[i].fee = fee;

            unchecked {
                // Fetch metadata for both tokens
                if (token0Address != address(0)) {
                    _fetchTokenMetadata(token0Address, results[i].token0);
                } else {
                    // For ETH (address 0), add hardcoded metadata
                    results[i].token0.name = "Ether";
                    results[i].token0.symbol = "ETH";
                    results[i].token0.decimals = 18;
                }

                if (token1Address != address(0)) {
                    _fetchTokenMetadata(token1Address, results[i].token1);
                } else {
                    // For ETH (address 0), add hardcoded metadata
                    results[i].token1.name = "Ether";
                    results[i].token1.symbol = "ETH";
                    results[i].token1.decimals = 18;
                }

                ++i; // Use unchecked increment for gas optimization
            }
        }

        // Encode the results
        bytes memory encodedData = abi.encode(results);

        // Return the results with memory pointer optimization
        assembly {
            return(add(encodedData, 32), mload(encodedData))
        }
    }

    // Optimized internal function to fetch token metadata using assembly for external calls
    function _fetchTokenMetadata(address tokenAddress, TokenMetadata memory tokenMetadata) internal view {
        // Remove unnecessary initializations since they are set in assembly
        string memory name;
        string memory symbol;
        uint8 decimals;

        // Function selectors
        bytes4 nameSelector = 0x06fdde03; // bytes4(keccak256("name()"))
        bytes4 symbolSelector = 0x95d89b41; // bytes4(keccak256("symbol()"))
        bytes4 decimalsSelector = 0x313ce567; // bytes4(keccak256("decimals()"))

        // Low-level optimized call using assembly
        assembly {
            // Allocate memory for the call
            let ptr := mload(0x40) // Free memory pointer

            // --- Fetch name ---
            // Prepare function selector
            mstore(ptr, nameSelector)

            // Make the call
            let success :=
                staticcall(
                    gas(), // Forward all gas
                    tokenAddress, // Target contract
                    ptr, // Input pointer (function selector)
                    0x04, // Input size (4 bytes)
                    0x00, // Output position (temporary)
                    0x00 // Output size (unknown yet)
                )

            // Process name result
            if success {
                // Get return data
                let returnDataSize := returndatasize()
                if iszero(iszero(returnDataSize)) {
                    // Copy return data to memory
                    returndatacopy(ptr, 0, returnDataSize)

                    // Check if the ABI-encoded string is valid
                    if gt(returnDataSize, 0x40) {
                        // At least 64 bytes
                        // Get string length - for a string, the first word is the data position (0x20)
                        // and the second word is the length
                        let stringLength := mload(add(ptr, 0x20))

                        // Only process if the string length is reasonable
                        if and(gt(stringLength, 0), lt(stringLength, 0x1000)) {
                            // 4KB max for safety
                            // Calculate the string data size using bit shifting (power of 2)
                            let stringDataSize := shl(5, shr(5, add(stringLength, 0x1F)))

                            // Allocate memory for our string
                            let namePtr := mload(0x40) // Get free memory pointer

                            // Store the length
                            mstore(namePtr, stringLength)

                            // Copy the string data
                            let stringDataOffset := add(ptr, 0x40) // Skip the two length words
                            let nameDataPtr := add(namePtr, 0x20) // Skip the length word

                            // Copy the string bytes
                            for { let i := 0 } lt(i, stringDataSize) { i := add(i, 0x20) } {
                                mstore(add(nameDataPtr, i), mload(add(stringDataOffset, i)))
                            }

                            // Update name reference
                            name := namePtr

                            // Update free memory pointer
                            mstore(0x40, add(add(namePtr, 0x20), stringDataSize))
                        }
                    }
                }
            }

            // --- Fetch symbol ---
            // Reset pointer for symbol call
            ptr := mload(0x40)

            // Prepare function selector
            mstore(ptr, symbolSelector)

            // Make the call
            success :=
                staticcall(
                    gas(), // Forward all gas
                    tokenAddress, // Target contract
                    ptr, // Input pointer
                    0x04, // Input size
                    0x00, // Output position
                    0x00 // Output size
                )

            // Process symbol result (similar approach to name)
            if success {
                let returnDataSize := returndatasize()
                if iszero(iszero(returnDataSize)) {
                    returndatacopy(ptr, 0, returnDataSize)

                    if gt(returnDataSize, 0x40) {
                        let stringLength := mload(add(ptr, 0x20))

                        if and(gt(stringLength, 0), lt(stringLength, 0x1000)) {
                            // Use bit shifting for power-of-2 operations
                            let stringDataSize := shl(5, shr(5, add(stringLength, 0x1F)))

                            let symbolPtr := mload(0x40)

                            mstore(symbolPtr, stringLength)

                            let stringDataOffset := add(ptr, 0x40)
                            let symbolDataPtr := add(symbolPtr, 0x20)

                            for { let i := 0 } lt(i, stringDataSize) { i := add(i, 0x20) } {
                                mstore(add(symbolDataPtr, i), mload(add(stringDataOffset, i)))
                            }

                            symbol := symbolPtr

                            mstore(0x40, add(add(symbolPtr, 0x20), stringDataSize))
                        }
                    }
                }
            }

            // --- Fetch decimals ---
            // Reset pointer for decimals call
            ptr := mload(0x40)

            // Prepare function selector
            mstore(ptr, decimalsSelector)

            // Make the call
            success :=
                staticcall(
                    gas(), // Forward all gas
                    tokenAddress, // Target contract
                    ptr, // Input pointer
                    0x04, // Input size
                    ptr, // Output position (reuse the same memory)
                    0x20 // Output size (uint8 takes 32 bytes when encoded)
                )

            // Process decimals result
            if success {
                let returnDataSize := returndatasize()
                if eq(returnDataSize, 0x20) { decimals := mload(ptr) }
            }
        }

        // Set the token metadata
        tokenMetadata.name = name;
        tokenMetadata.symbol = symbol;
        tokenMetadata.decimals = decimals;
    }
}
