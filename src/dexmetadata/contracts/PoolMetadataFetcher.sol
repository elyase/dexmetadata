// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/**
 * @title PoolMetadataFetcherFixed
 * @dev A deployless multicall contract for fetching DEX pool metadata.
 * @dev Optimized version inspired by Multicall3 techniques
 */
contract PoolMetadataFetcherFixed {
    // Structure to hold token metadata (kept simple to avoid bytecode variation)
    struct TokenMetadata {
        address tokenAddress;
        string name;
        string symbol;
        uint8 decimals;
    }
    
    // Structure to hold pool metadata
    struct PoolMetadata {
        address poolAddress;
        TokenMetadata token0;
        TokenMetadata token1;
    }
    
    // Using payable to save gas by removing msg.value check
    constructor(address[] memory poolAddresses) payable {
        // Create result array
        uint256 poolCount = poolAddresses.length;
        if (poolCount == 0) poolCount = 1;
        
        PoolMetadata[] memory results = new PoolMetadata[](poolCount);
        
        // Process each pool
        // Cache the length to avoid reading it on each iteration
        uint256 length = poolAddresses.length;
        
        for (uint256 i = 0; i < length;) {
            address poolAddress = poolAddresses[i];
            results[i].poolAddress = poolAddress;
            
            if (poolAddress == address(0)) {
                unchecked { ++i; } // Use prefix increment in unchecked block for gas optimization
                continue;
            }
            
            // Get token addresses
            address token0Address;
            address token1Address;
            
            // Call token0() and token1() with try/catch
            try IUniswapV2Pair(poolAddress).token0() returns (address _token0) {
                token0Address = _token0;
            } catch {
                token0Address = address(0);
            }
            
            try IUniswapV2Pair(poolAddress).token1() returns (address _token1) {
                token1Address = _token1;
            } catch {
                token1Address = address(0);
            }
            
            // Store token addresses and fetch metadata in a single pass
            results[i].token0.tokenAddress = token0Address;
            results[i].token1.tokenAddress = token1Address;
            
            unchecked {
                // Fetch metadata for both tokens if they exist
                if (token0Address != address(0)) {
                    _fetchTokenMetadata(token0Address, results[i].token0);
                }
                if (token1Address != address(0)) {
                    _fetchTokenMetadata(token1Address, results[i].token1);
                }
                ++i; // Use unchecked increment
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
    function _fetchTokenMetadata(address tokenAddress, TokenMetadata memory tokenMetadata) internal {
        // Default values
        string memory name = "";
        string memory symbol = "";
        uint8 decimals = 0;
        
        // Function selectors
        bytes4 nameSelector = 0x06fdde03;     // bytes4(keccak256("name()"))
        bytes4 symbolSelector = 0x95d89b41;   // bytes4(keccak256("symbol()"))
        bytes4 decimalsSelector = 0x313ce567; // bytes4(keccak256("decimals()"))
        
        // Low-level optimized call using assembly
        assembly {
            // Allocate memory for the call
            let ptr := mload(0x40) // Free memory pointer
            
            // --- Fetch name ---
            // Prepare function selector
            mstore(ptr, nameSelector)
            
            // Make the call
            let success := staticcall(
                gas(),          // Forward all gas
                tokenAddress,   // Target contract
                ptr,            // Input pointer (function selector)
                0x04,           // Input size (4 bytes)
                0x00,           // Output position (temporary)
                0x00            // Output size (unknown yet)
            )
            
            // Process name result
            if success {
                // Get return data
                let returnDataSize := returndatasize()
                if gt(returnDataSize, 0) {
                    // Copy return data to memory
                    returndatacopy(ptr, 0, returnDataSize)
                    
                    // Check if the ABI-encoded string is valid
                    if gt(returnDataSize, 0x40) { // At least 64 bytes
                        // Get string length - for a string, the first word is the data position (0x20)
                        // and the second word is the length
                        let stringLength := mload(add(ptr, 0x20))
                        
                        // Only process if the string length is reasonable
                        if and(gt(stringLength, 0), lt(stringLength, 0x1000)) { // 4KB max for safety
                            // Calculate the string data size (rounded up to 32 bytes)
                            let stringDataSize := mul(div(add(stringLength, 0x1F), 0x20), 0x20)
                            
                            // Allocate memory for our string
                            let namePtr := mload(0x40) // Get free memory pointer
                            
                            // Store the length
                            mstore(namePtr, stringLength)
                            
                            // Copy the string data
                            let stringDataOffset := add(ptr, 0x40) // Skip the two length words
                            let nameDataPtr := add(namePtr, 0x20)  // Skip the length word
                            
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
            success := staticcall(
                gas(),          // Forward all gas
                tokenAddress,   // Target contract
                ptr,            // Input pointer
                0x04,           // Input size
                0x00,           // Output position
                0x00            // Output size
            )
            
            // Process symbol result (similar approach to name)
            if success {
                let returnDataSize := returndatasize()
                if gt(returnDataSize, 0) {
                    returndatacopy(ptr, 0, returnDataSize)
                    
                    if gt(returnDataSize, 0x40) {
                        let stringLength := mload(add(ptr, 0x20))
                        
                        if and(gt(stringLength, 0), lt(stringLength, 0x1000)) {
                            let stringDataSize := mul(div(add(stringLength, 0x1F), 0x20), 0x20)
                            
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
            success := staticcall(
                gas(),          // Forward all gas
                tokenAddress,   // Target contract
                ptr,            // Input pointer
                0x04,           // Input size
                ptr,            // Output position (reuse the same memory)
                0x20            // Output size (uint8 takes 32 bytes when encoded)
            )
            
            // Process decimals result
            if success {
                let returnDataSize := returndatasize()
                if eq(returnDataSize, 0x20) {
                    decimals := mload(ptr)
                }
            }
        }
        
        // Set the values
        tokenMetadata.name = name;
        tokenMetadata.symbol = symbol;
        tokenMetadata.decimals = decimals;
    }
}

// Interface for Uniswap V2-style pools
interface IUniswapV2Pair {
    function token0() external view returns (address);
    function token1() external view returns (address);
}

// Interface for ERC20 tokens
interface IERC20Metadata {
    function name() external view returns (string memory);
    function symbol() external view returns (string memory);
    function decimals() external view returns (uint8);
}