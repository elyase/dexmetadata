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

- No fancy setup ([dbt pipelines](https://github.com/duneanalytics/spellbook/tree/main/dbt_subprojects/dex/models/trades) / datalake infrastructure / [customized nodes](https://github.com/shadow-hq/shadow-reth)) needed, just plug in any standard RPC and you're good to go
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

## Overview of pool metadata retrieval methods

### Metadata origin

DEX **pool metadata** (token addresses) can be retrieved from:

- **Event Logs** (ex `PairCreated`/`PoolCreated` events)
- **Contract Storage** (ex accessed via `.token0()` / `.token1()`)
- **Transaction input data:** (ex `createPair/createPool` tx calldata)

**ERC20 metadata** is stored in **Contract Storage** and can be accessed via the corresponding view functions (`.name()`, `.symbol()`, `.decimals()`)

### Methods to access pool and ERC20 metadata:

- Direct node access (ex reth execution extensions or direct db access)
- RPC calls
- Pre-indexed raw tables (e.g., envio.dev, sqd.ai)

### Processing

We also need processing for:

- Filtering
- Decoding logs
- Combining pool and ERC20 metadata
- Caching

Processing can be performed on-node, off-chain, or hybrid, creating several dimensions in the **solution space**, in summary:

- **Data Origin**: Raw Logs, Transaction Inputs, Contract State
-  **Access Method**: Direct Node, RPC, Indexer
- **Processing Location**: On-Node, Off-Chain, Hybrid

### Solution space

| **solution**       | **Processing** | **Origin**     | **Access Method** |
| ------------------ | --------------- | -------------- | ----------------- |
| **subgraphs**      | Off-Chain       | Raw Logs       | RPC               |
| **dune spellbook** | Off-Chain       | Raw Logs       | Indexer           |
| **shadow-reth**    | On-Node         | Contract State | Direct Node       |
| **ponder**         | Off-Chain       | Hybrid         | RPC               |

Each example approach has a unique complexity, storage, latency profile. Relevant metrics include:

- **DEX Coverage**: Effort needed to add new DEXes
- **Backfill Speed**: Performance of processing a large number of pools
- **Storage**: Ex space required for indexed data
- **Latency**: Delay from transaction inclusion to data availability
- **Cold Start**: Time needed to start serving requests
- **Complexity**: Implementation and maintenance effort
- **Cost**: Operational expenses

This table provides a view on how these approaches compare with each other (higher = better). The scores reflect subjective estimates of each methodology in the context of the task of fetching metadata for a specific set of pools (rather than the actual products themselves)


| **Solution**       | **Backfilling speed** | **Storage** | **Latency** | **Cold start** | **Cost** |
| ------------------ | --------------------- | ----------- | ----------- | -------------- | -------- |
| **subgraphs**      | 1                     | 3           | 3           | 1              | 3        |
| **dune spellbook** | 5                     | 1           | 1           | 2              | 1        |
| **shadow-reth**    | 4                     | 3           | 5           | 3              | 1        |
| **ponder**         | 2                     | 3           | 3           | 2              | 3        |
| dexmetadata        | 3                     | 5           | 3           | 5              | 5        |


### This library's approach

- **Metadata Origin:** Contract State
- **Access Method:** RPC
- **Processing:** mostly on-node with the deployless multicall contract

**Pros:**

- Minimal setup: just a Python library and standard RPC
- Strong DEX coverage (over 95%) without the need for custom logic for each individual DEX
- Storage efficient: eliminates the requirement for maintaining large historical tables for every pool and token, which users are unlikely to query
- More performant than solutions that process events one at a time

**Cons**

- Backfills (more precisely large number of pools) can be slower compared to using event logs and indexers, as it does not take advantage of pre-indexed data, also off-chain processing scales better than on-node solutions
- Slightly higher latency in comparison to direct node access methods

## Roadmap

- [ ] DEX support
    - [ ] uniswap v4
    - [ ] balancer
    - [ ] Maverick
- [ ] Cache with smart eviction policy
- [ ] erpc integration
- [ ] CLI interface
- [ ] benchmarks
- [ ] alternative method to leverage indexed data and off-chain processing for requests involving a higher number of pools