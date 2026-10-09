# arc-pulse

Public, backend-free monitor for **Arc** (Circle's stablecoin-gas L1): block height and time, finality, gas and the cost of a simple
transfer, activity, and consistency across four public RPC providers — all read **directly from your browser**.

A server-side pinger sends one tiny transaction every 10 minutes to the `Pinger` contract. Each ping stores the confirmation latency
of the previous one on-chain, and the dashboard shows its fee straight from the transaction receipt — so every number is verifiable on-chain.

**Live:** https://eaxgtfcs-glitch.github.io/arc-pulse/ (network selector: mainnet / testnet)

| | Testnet (5042002) | Mainnet (5042) |
|---|---|---|
| Pinger | `0x99451d6ad09a203D9E6e1e4A329bC5ea98356088` | `0x9762faf3e1875F73f436CEB4e9A006d01b3eb1b1` |

## How it is verified
`check_ui.py` opens the live page in a real browser, injects a dead RPC, and re-computes every number from the chain:
provider heights, finalized lag, average block time and tx/block from the same 50 blocks, gas price against recent base fee + tips,
pings against the contract, fees against receipts, latency against the pinger log, owner-only pinging. `make check` runs it all.
