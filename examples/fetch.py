#!/usr/bin/env python
"""
Example script demonstrating how to fetch DEX pool metadata.
"""

from dexmetadata import fetch

# Example pool addresses from different DEXes on Base
POOL_ADDRESSES = [
    "0xfBB6Eed8e7aa03B138556eeDaF5D271A5E1e43ef",  # cbBTC/USDC on uniswap v3
    "0x31f609019d0CC0b8cC865656142d6FeD69853689",  # POPCAT/WETH on uniswap v2
    "0x6cDcb1C4A4D1C3C6d054b27AC5B77e89eAFb971d",  # AERO/USDC on Aerodrome
    "0x323b43332F97B1852D8567a08B1E8ed67d25A8d5",  # msETH/WETH on Pancake Swap
] * 250


def main():
    pools = fetch(
        POOL_ADDRESSES,
        rpc_url="https://base-rpc.publicnode.com",
        batch_size=30,
        max_concurrent_batches=25,
    )

    assert pools[0].token0.symbol == "USDC"

    assert pools[0].token1.name == "Coinbase Wrapped BTC"
    assert pools[0].token1.symbol == "cbBTC"
    assert pools[0].token1.address == "0xcbb7c0000ab88b473b1f5afd9ef808440eed33bf"
    assert pools[0].token1.decimals == 8

    print(pools[0])
    # USDC/cbBTC (0xfbb6eed8e7aa03b138556eedaf5d271a5e1e43ef)
    # ├─ USD Coin
    # │    ├ USDC
    # │    ├ 0x833589fcd6edb6e08f4c7c32d4f71b54bda02913
    # │    └ 6
    # └─ Coinbase Wrapped BTC
    #      ├ cbBTC
    #      ├ 0xcbb7c0000ab88b473b1f5afd9ef808440eed33bf
    #      └ 8


if __name__ == "__main__":
    main()
