# Arc Microgrants — submission draft (arc-pulse)

**Project name:** arc-pulse — a verifiable, backend-free monitor for Arc mainnet

**One-liner:** A public dashboard that reads Arc straight from your browser and proves its numbers on-chain: block time, finality,
gas and the real cost of a transaction, activity, and consistency across Arc's four public RPC providers — plus a mainnet `Pinger`
contract that records measured confirmation latency every 10 minutes.

**Live deployment:** https://eaxgtfcs-glitch.github.io/arc-pulse/  (mainnet by default; testnet selectable)
**Mainnet contract (Pinger):** `0x9762faf3e1875F73f436CEB4e9A006d01b3eb1b1` — https://explorer.arc.io/address/0x9762faf3e1875F73f436CEB4e9A006d01b3eb1b1
**Repo:** https://github.com/eaxgtfcs-glitch/arc-pulse
**Builder profile:** https://github.com/eaxgtfcs-glitch

## What it does
- Queries Circle, Blockdaemon, dRPC and QuickNode Arc endpoints **directly from the browser** (all four allow CORS) — no backend to trust or to go down.
- Shows height and finalized lag per provider (Arc finalizes instantly — the page shows it), average block time and tx/s over the last 50 blocks,
  gas price and the USDC cost of a simple transfer, and flags providers that lag, return the wrong chain, or are down.
- A small server-side pinger sends one transaction every 10 minutes to the `Pinger` contract on mainnet. Each ping stores
  `(sentAtMs, blockNumber, blockTimestamp, prevLatencyMs)` in a ring buffer read with a single `eth_call`; the page shows confirmation
  latency and each ping's **actual fee from its receipt** (gasUsed × effectiveGasPrice), so builders see what a transaction on Arc really costs and how fast it lands.

## What it uses Arc for
- Native USDC gas: every ping is paid in USDC; the dashboard reports fees in USDC from receipts.
- Deterministic finality: finalized == latest is measured continuously across providers.
- A mainnet contract (`Pinger`, owner-only writes) as a public, tamper-evident latency/fee log.

## Why it's credible
Every number is checked against the chain by an automated browser test (`check_ui.py`): it opens the live page, injects a dead RPC,
and recomputes heights, block time, tx/block, gas bounds, pings and fees from Arc itself. `mutate.py` serves deliberately broken copies
of the page and requires the test to fail on each — so the check itself is tested.

## Optional add-on: paid API for agents (x402)
The monitor is complete and works on its own — everything above is live on mainnet today.
On top of it we are adding an **optional** x402 endpoint: AI agents and bots can fetch the same verified metrics as JSON and pay per request
in USDC on Arc ($0.001, EIP-3009 `transferWithAuthorization`, settled on-chain — no facilitator, no API keys). The free dashboard stays free;
the paid API is an extra for machine clients. Status is tracked in the repo README.

## Where it goes next
Alerts when a provider degrades; historical latency/fee charts for builders choosing an RPC; more networks' views for agents via the x402 API.
