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
    "0xe6195a1f1c8f5d0bcf0a880db26738a1df4f6863017700a8f6377a72d45366f2",  # cbBTC/ETH on Uniswap v4
    "0x123456789abcdef0123456789abcdef012345678",  # non-existent pool
]


def main():
    pools = fetch(
        POOL_ADDRESSES,
        rpc_url="https://base-rpc.publicnode.com",
        chain_id=8453,  # Base chain ID (required for Uniswap v4 pools)
        batch_size=30,
        max_concurrent_batches=25,
        use_cache=False,
    )

    assert pools[0].token0.symbol == "USDC"
    assert pools[0].token1.name == "Coinbase Wrapped BTC"
    assert pools[0].token1.symbol == "cbBTC"
    assert pools[0].token1.address == "0xcbb7c0000ab88b473b1f5afd9ef808440eed33bf"
    assert pools[0].token1.decimals == 8

    print(f"Fetched {len(pools)} pools:")
    for i, pool in enumerate(pools):
        print(pool)


if __name__ == "__main__":
    main()
