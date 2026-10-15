#!/usr/bin/env python3
"""arc-pulse: деплой Pinger и пинг-транзакции. Использование:
  ping.py balance|deploy|ping|recent [--net testnet]
Мейннет заблокирован без ALLOW_MAINNET=1. Ключ — /etc/agent/arc.key."""
import json, os, sys, time
from pathlib import Path
from web3 import Web3
from eth_account import Account

ROOT = Path(__file__).parent
KEY_FILE = "/etc/agent/arc.key"
MAX_DAILY_USD = 0.20  # потолок трат в сутки (USDC ≈ $1)

def load(net):
    cfg = json.loads((ROOT / "config.json").read_text())
    if net == "mainnet" and os.environ.get("ALLOW_MAINNET") != "1":
        sys.exit("мейннет заблокирован (нужен ALLOW_MAINNET=1)")
    n = cfg["networks"][net]
    w3 = Web3(Web3.HTTPProvider(n["rpcs"][0]["url"], request_kwargs={"timeout": 15}))
    assert w3.eth.chain_id == n["chainId"], "chainId не совпал"
    return cfg, n, w3, Account.from_key(Path(KEY_FILE).read_text().strip())

def build():
    import solcx
    out = solcx.compile_files([str(ROOT / "contracts/Pinger.sol")], solc_version="0.8.24",
                              output_values=["abi", "bin"])
    return next(iter(out.values()))

def spent_today(net):
    f = ROOT / "data" / f"pings-{net}.jsonl"
    if not f.exists():
        return 0.0
    since = time.time() - 86400
    return sum(r["fee_usdc"] for r in map(json.loads, f.read_text().splitlines()) if r["sent_at"] > since)

def send(w3, acct, tx):
    tx.setdefault("chainId", w3.eth.chain_id)
    tx["nonce"] = w3.eth.get_transaction_count(acct.address)
    for k in ("maxFeePerGas", "maxPriorityFeePerGas"):
        tx.pop(k, None)
    tx["gasPrice"] = w3.eth.gas_price
    tx.pop("gas", None)
    tx["gas"] = int(w3.eth.estimate_gas({**tx, "from": acct.address}) * 1.2)
    t0 = time.time()
    h = w3.eth.send_raw_transaction(acct.sign_transaction(tx).raw_transaction)
    r = w3.eth.wait_for_transaction_receipt(h, timeout=60)
    return r, time.time() - t0

def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "balance"
    net = sys.argv[sys.argv.index("--net") + 1] if "--net" in sys.argv else "testnet"
    cfg, n, w3, acct = load(net)
    # нативный баланс Arc — USDC с 18 знаками
    bal = w3.eth.get_balance(acct.address) / 1e18
    if cmd == "balance":
        print(f"{net} {acct.address} {bal:.6f} USDC"); return
    if bal < 0.01:
        sys.exit(f"баланс {bal} слишком мал — кран faucet.circle.com")
    c = build()
    if cmd == "recent":
        ct = w3.eth.contract(address=n["pinger"], abi=c["abi"])
        out, total = ct.functions.recent().call()
        print("total", total)
        for sent_ms, block, ts, prev_ms in out[:5]:
            print(f"  block {block} ts {ts} sent {sent_ms} prevLatency {prev_ms} ms")
        return
    if cmd == "deploy":
        r, _ = send(w3, acct, w3.eth.contract(abi=c["abi"], bytecode=c["bin"]).constructor().build_transaction(
            {"from": acct.address, "nonce": 0, "gas": 0}))
        print("Pinger:", r.contractAddress); return
    if cmd == "ping":
        if not n["pinger"]:
            sys.exit("pinger не задан в config.json")
        if spent_today(net) >= MAX_DAILY_USD:
            sys.exit("потолок трат за сутки")
        ct = w3.eth.contract(address=n["pinger"], abi=c["abi"])
        sent = time.time()
        prev = [json.loads(l) for l in (ROOT / "data" / f"pings-{net}.jsonl").read_text().splitlines()] if (ROOT / "data" / f"pings-{net}.jsonl").exists() else []
        prev = [p for p in prev if p.get("pinger") == n["pinger"]]
        prev_ms = int(prev[-1]["latency_s"] * 1000) if prev else 0
        tx = ct.functions.ping(int(sent * 1000), prev_ms).build_transaction({"from": acct.address, "nonce": 0, "gas": 0})
        r, lat = send(w3, acct, tx)
        blk = w3.eth.get_block(r.blockNumber)
        rec = {"net": net, "pinger": n["pinger"], "hash": "0x" + r.transactionHash.hex().removeprefix("0x"), "block": r.blockNumber, "block_ts": blk.timestamp,
               "sent_at": sent, "sent_ms": int(sent * 1000), "prev_latency_ms": prev_ms, "latency_s": round(lat, 3), "gas_used": r.gasUsed,
               "gas_price": r.effectiveGasPrice, "fee_usdc": r.gasUsed * r.effectiveGasPrice / 1e18}
        with open(ROOT / "data" / f"pings-{net}.jsonl", "a") as f:
            f.write(json.dumps(rec) + "\n")
        print(rec)

main()
