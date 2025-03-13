import time
from pprint import pprint

from dexmetadata import fetch

# Example pool addresses from Base network
POOL_ADDRESSES = [
    "0x31f609019d0CC0b8cC865656142d6FeD69853689",  # POPCAT/WETH on uniswap v2
    "0xfBB6Eed8e7aa03B138556eeDaF5D271A5E1e43ef",  # cbBTC/USDC on uniswap v3
    "0x6cDcb1C4A4D1C3C6d054b27AC5B77e89eAFb971d",  # AERO/USDC on Aerodrome
    "0x323b43332F97B1852D8567a08B1E8ed67d25A8d5",  # msETH/WETH on Pancake Swap
] * 250


def main():
    start_time = time.time()
    pools = fetch(
        POOL_ADDRESSES,
        network="base",
        batch_size=30,
        max_concurrent_batches=25,
        show_progress=True,
    )
    duration = time.time() - start_time

    valid_pools = sum(1 for pool in pools if pool.get("token0_name"))
    print(
        f"\nFetched {valid_pools} pools in {duration:.2f}s ({len(pools) / duration:.2f} pools/s)"
    )
    print("\nSample output:")
    pprint(pools[0] if pools else "No pools found")


if __name__ == "__main__":
    main()
