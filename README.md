# DexMetadata 🦄 

Python library for fetching metadata from DEX pools

![](demo.gif)

## Usage 🚀

```python
from dexmetadata import fetch

POOL_ADDRESSES = [
    "0xfBB6Eed8e7aa03B138556eeDaF5D271A5E1e43ef",  # cbBTC/USDC on uniswap v3
    "0x31f609019d0CC0b8cC865656142d6FeD69853689",  # POPCAT/WETH on uniswap v2
    "0x6cDcb1C4A4D1C3C6d054b27AC5B77e89eAFb971d",  # AERO/USDC on Aerodrome
    "0x323b43332F97B1852D8567a08B1E8ed67d25A8d5",  # msETH/WETH on Pancake Swap
    # Add hundreds more without worry!
]

pools = fetch(
    POOL_ADDRESSES, 
    rpc_url="https://base-rpc.publicnode.com",
    batch_size=30,
    max_concurrent_batches=25,
)

assert pools[0].token0.symbol == 'USDC'

assert pools[0].token1.name == 'Coinbase Wrapped BTC'
assert pools[0].token1.symbol == 'cbBTC'
assert pools[0].token1.address == '0xcbb7c0000ab88b473b1f5afd9ef808440eed33bf'
assert pools[0].token1.decimals == 8
```

## Features 🌟

- No fancy setup ([dbt pipelines](https://github.com/duneanalytics/spellbook/tree/main/dbt_subprojects/dex/models/trades) / datalake infrastructure / customized nodes) needed, just plug in any standard RPC and you're good to go
- Uses some clever EVM tricks (assembly optimized [deployless multicall](https://destiner.io/blog/post/deployless-multicall/)) to get the job done quickly and cheaply
- Covers [95%+ of swaps out there](examples/coverage.py) without DEX-specific custom transform logic
- Processes multiple pools at once to keep things fast and efficient
- [Handy tool](examples/optimize.py) to automatically find good settings for your RPC


## Installation 📥

```bash
$ uv add dexmetadata
```


## How It Works 🔍

1. On each eth_call we "deploy" a [special contract](src/dexmetadata/contracts/PoolMetadataFetcher.sol) using the [deployless multicall](https://destiner.io/blog/post/deployless-multicall/) trick 
2. Contract executes with a batch of pool addresses in the EVM and fetches both tokens in each pool
3. Then for each token we get token name, symbol, and decimals using optimized assembly calls
4. The result is decoded in Python and returned as a list of dictionaries
5. For async execution, multiple batches are processed concurrently using asyncio

<details>
  <summary>Diagram</summary>
  
  ```mermaid
  graph TD
      A["Pools"]:::python --> B{{"🔍 Validate<br> addresses"}}:::python
      B -->|"✅"| C["📦 Batches"]:::python
      B -->|"❌"| D["⚠ Log Warning"]:::python
      C -->|"⚡ Concurrent"| EVM1
      EVM1["🌐 RPC eth_call"]:::python
      EVM1 -->|"batch"| F

      subgraph EVM ["Node"]
          F["📄 Deployless multicall <br>contract constructor"]:::python
          G["Process Pool"]:::python
          H{{" Has <br> token0/token1?"}}:::python
          I["⚙ Assembly Calls"]:::python
          J["🔄 Null Data"]:::python
          K["Encode Metadata"]:::python
          L["Return ABI Data"]:::python

          %% Internal flow inside EVM subgraph
          F -->|"loop"| G
          G --> H
          H -->|"✅ Yes (97.5%)"| I
          H -->|"❌ ex Uniswap v4 (2.5%)"| J
          I --> K
          K --> L
      end
      L --> M
      M["Decoder"]:::python
      M --> N
      N["Pool Objects"]:::python

      %% Observed error paths from logs
      EVM1 -.->|"404 Not Found"| D
      I -.->|"ex Uniswap v4"| J

      %% Class definitions for styling (minimalistic palette)
      classDef python fill:#f5f5f5,stroke:#ccc,color:#333,stroke-width:1px;
      classDef validation fill:#f5f5f5,stroke:#ccc,color:#333,stroke-width:1px;
      classDef batch fill:#f5f5f5,stroke:#ccc,color:#333,stroke-width:1px;
      classDef rpc fill:#f5f5f5,stroke:#ccc,color:#333,stroke-width:1px;
      classDef contract fill:#f5f5f5,stroke:#ccc,color:#333,stroke-width:1px;
      classDef assembly fill:#f5f5f5,stroke:#ccc,color:#333,stroke-width:1px;
      classDef error fill:#ffcccc,stroke:#e57373,color:#333,stroke-width:1px;
      classDef success fill:#ccffcc,stroke:#81c784,color:#333,stroke-width:1px;
  ```
</details>




## Performance

The parameter optimizer finds good settings for your RPC provider:
```bash
$ uv run examples/optimize.py --rpm 1800 --rpc https://base-rpc.publicnode.com

Measuring response time with optimal batch size...
Average response time: 2.51s

Optimal parameters:
  batch_size: 30
  max_concurrent_batches: 25
```
In real-world testing, the fetch script processed 1000 pools in ~6s (~160 pools/s).

The default parameters (`batch_size=30`, `max_concurrent_batches=25`) are optimized for publicnodes.com RPC endpoints and deliver good performance while staying within rate limits.

## Alternative Approaches

In the end it's all about deciding the main trade offs regarding where and when to process the data, at a node, off-chain in a data lake, on the client, during the query or in advance, etc ...

### Event cache
Build a cache for all pools and tokens metadata (ex [Dune spellbook](https://github.com/duneanalytics/spellbook/tree/main/dbt_subprojects/dex/models/trades))

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

## Roadmap

- [ ] Support the remaining 5% of swaps
    - [ ] uniswap v4
    - [ ] balancer
    - [ ] Maverick

- [ ] Cache with custom eviction policy