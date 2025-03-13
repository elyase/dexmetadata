# DexMetadata 🦄 

Quickly fetch metadata for DEX pools with a single function call!

## Usage 🚀

```python
from dexmetadata import fetch

POOL_ADDRESSES = [
    "0x31f609019d0CC0b8cC865656142d6FeD69853689",  # POPCAT/WETH on uniswap v2
    "0xfBB6Eed8e7aa03B138556eeDaF5D271A5E1e43ef",  # cbBTC/USDC on uniswap v3
    "0x6cDcb1C4A4D1C3C6d054b27AC5B77e89eAFb971d",  # AERO/USDC on Aerodrome
    "0x323b43332F97B1852D8567a08B1E8ed67d25A8d5",  # msETH/WETH on Pancake Swap
    # Add hundreds more without worry!
]

# Fetch metadata with automatic batching and progress bars
metadata = fetch(
    POOL_ADDRESSES, 
    network="base", 
    batch_size=30,
    max_concurrent_batches=25,
    show_progress=True,
)

# [
#   {
#     'pool_address': '0x31f609019d0cc0b8cc865656142d6fed69853689',
#     'token0_address': '0x4200000000000000000000000000000000000006',
#     'token0_decimals': 18,
#     'token0_name': 'Wrapped Ether',
#     'token0_symbol': 'WETH',
#     'token1_address': '0x64fcfe0b4430b878cfd00d6539ac244f2e1e9d29',
#     'token1_decimals': 18,
#     'token1_name': 'Popcat',
#     'token1_symbol': 'POPCAT'
#   },
#   # ...more pools
# ]
```

![](demo.gif)


## Installation 📥

```bash
uv add dexmetadata
```

## How It Works 🔍

1. On each eth_call we "deploy" a [special contract](src/contracts/PoolMetadataFetcher.sol) using the [deployless multicall](https://destiner.io/blog/post/deployless-multicall/) trick 
2. Contract executes with a batch of pool addresses in the EVM and fetches both tokens in each pool
3. Then for each token we get token name, symbol, and decimals using optimized assembly calls
4. The result is decoded in Python and returned as a list of dictionaries
5. For async execution, multiple batches are processed concurrently using asyncio


## Performance

The parameter optimizer finds good settings for your RPC provider:
```bash
$ uv run examples/optimize.py --rpm 1800 --rpc https://rpc.ankr.com/base

Measuring response time with optimal batch size...
Average response time: 2.51s

Optimal parameters:
  batch_size: 30
  max_concurrent_batches: 25
```
In real-world testing, the fetch script processed 1000 pools in ~6s (~160 pools/s).

The default parameters (`batch_size=30`, `max_concurrent_batches=25`) are optimized for ankr and deliver good performance while staying within rate limits.

## Alternative Approaches

In the end it's all about deciding the main trade offs regarding where and when to process the data, at a node, off-chain in a data lake, on the client, during the query or in advance, etc ...

### Event cache
Build a cache for all pools and tokens metadata.

  * ❌ Requires custom decoding logic for each DEX
  * ❌ Needs historical data access
  * ❌ Need to maintain potentially large metadata cache
  * ❌ Inneficient processing of large numbers of pools / block ranges that wont be queried
  * ✅ Fast offchain lookups once cached

### Naive web3.py
  * ❌ Requires ABI setup for each DEX
  * ❌ Slow for large numbers of pools (1 RPC call per operation)
  * ✅ Simple implementation, no event scanning
  * ✅ Works on any EVM chain with basic RPC support