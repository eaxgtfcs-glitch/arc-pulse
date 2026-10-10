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

## Paid API for agents (x402) — optional add-on
`x402/worker/` (a Cloudflare Worker with a D1 replay store) — the same verified metrics as JSON for bots and AI agents, paid per request in USDC on Arc using x402 `exact` with the
`eip3009-client-broadcast` transfer method (the buyer broadcasts USDC `transferWithAuthorization` itself — on Arc gas is USDC — and the
Worker only verifies the receipt; nonce binding per the [x402-arc spec](https://github.com/kaditang/x402-arc), test vector matches).
Price $0.01 (the buyer's gas is ≈$0.002). The free dashboard stays free.

Status: implemented and checked with **real payments on Arc testnet** — `x402/check_x402.py` (paid → 200 with an on-chain USDC Transfer;
replay, underpay, wrong payee and stale receipt → 402 with the right reason) and `x402/mutate_x402.py` (5 broken Workers, each caught —
including Arc's native mirror `Transfer` ×1e12 trap). Public endpoint: coming next.
