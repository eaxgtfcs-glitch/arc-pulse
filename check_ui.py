#!/usr/bin/env python3
"""Black-box check of the live dashboard against the Arc network itself.

  check_ui.py [URL] [--net testnet|mainnet]     (default URL: GitHub Pages)

Opens the page in a real browser (with an extra dead RPC injected via ?addrpc=), reads what it shows
(window.__arcpulse + visible cards) and independently re-queries the RPCs to compare every number:
  P-1 heights / finalized lag, P-2 provider table incl. a dead provider, P-3 gas & simple-tx cost,
  P-4 block time and tx/block recomputed from the same 50 blocks, P-6 pings (seq, block, prev latency)
  against the contract and the pinger journal, fee against the tx receipt, P-9 page reachable.
Exit code 0 only if everything matches.
"""
import math
import asyncio, json, math, statistics, sys, time
from pathlib import Path
from web3 import Web3
from playwright.async_api import async_playwright

ROOT = Path(__file__).parent
CFG = json.loads((ROOT / "config.json").read_text())
_skip = {sys.argv.index("--net") + 1} if "--net" in sys.argv else set()
args = [a for i, a in enumerate(sys.argv) if i and i not in _skip and not a.startswith("--")]
URL = args[0] if args else "https://eaxgtfcs-glitch.github.io/arc-pulse/"
NET = sys.argv[sys.argv.index("--net") + 1] if "--net" in sys.argv else CFG["default"]
N = CFG["networks"][NET]
DEAD = "http://127.0.0.1:9"
fails, passes = [], []


def check(name, ok, info=""):
    (passes if ok else fails).append(name)
    print(("PASS " if ok else "FAIL ") + name + (f" — {info}" if info else ""))


async def read_page():
    async with async_playwright() as p:
        b = await p.chromium.launch(channel="chromium")
        pg = await b.new_page()
        sep = "&" if "?" in URL else "?"
        t0 = time.time()
        resp = await pg.goto(f"{URL}{sep}net={NET}&addrpc={DEAD}", timeout=60000)
        check("P-9 page reachable", resp is not None and resp.ok, f"HTTP {resp.status if resp else '?'}")
        await pg.wait_for_function("window.__arcpulse && __arcpulse.updated>0 && __arcpulse.stats", timeout=60000)
        if N.get("pinger"):
            await pg.wait_for_function("__arcpulse.pings.length>0 && __arcpulse.pings.every(p=>p.fee!=null)", timeout=60000)
        st = json.loads(await pg.evaluate("JSON.stringify(window.__arcpulse,(k,v)=>k==='blocks'?undefined:v)"))
        cards = {i: await pg.inner_text(f"#{i}") for i in ["h", "bt", "fin", "gas", "cost", "act", "plat", "pfee"]}
        cards["rows"] = await pg.evaluate("[...document.querySelectorAll('#rows tr')].map(r=>[r.dataset.name,r.dataset.status,r.cells[1].innerText])")
        await b.close()
        return st, cards, time.time() - t0


def main():
    st, cards, took = asyncio.run(read_page())
    w = {r["name"]: Web3(Web3.HTTPProvider(r["url"], request_kwargs={"timeout": 10})) for r in N["rpcs"]}
    ref = next(iter(w.values()))
    now_h = {k: c.eth.block_number for k, c in w.items()}
    shown = {p["name"]: p for p in st["providers"]}
    # P-2: every configured provider shown and up, injected dead one shown down
    check("P-2 all real providers up on page", all(shown.get(k, {}).get("up") for k in w), str({k: shown.get(k, {}).get("up") for k in w}))
    seen_rows = {n: (st_, txt) for n, st_, txt in cards["rows"]}
    check("P-2 dead provider marked down (state and screen)", shown.get("extra", {}).get("up") is False
          and seen_rows.get("extra", ("", ""))[1] == "down", str(seen_rows.get("extra")))
    check("P-2 real providers 'ok' on screen", all(seen_rows.get(k, ("", ""))[1] == "ok" for k in w), str(seen_rows))
    check("P-2 chainId shown = config", all(shown[k]["chain"] == N["chainId"] for k in w if k in shown and shown[k].get("up")))
    # P-1: heights on page are not ahead of the chain and not stale (≤ 2 blocks/s × age + lag)
    slack = int(took * 2) + CFG["maxLag"] + 4
    bad = {k: (shown[k]["height"], now_h[k]) for k in w if not (now_h[k] - slack <= shown[k]["height"] <= now_h[k])}
    check("P-1 heights match chain", not bad, f"slack {slack}, off: {bad}" if bad else f"slack {slack}")
    up_h = [shown[k]["height"] for k in w if shown.get(k, {}).get("up")]
    check("P-1 height card = max provider height on page and ≈ chain", cards["h"].isdigit() and up_h
          and max(up_h) <= int(cards["h"]) <= max(now_h.values()) and int(cards["h"]) >= max(now_h.values()) - slack,
          f"card {cards['h']}, providers max {max(up_h) if up_h else None}, chain {max(now_h.values())}")
    check("P-1 finalized lag ≤ maxLag", cards["fin"].isdigit() and int(cards["fin"]) <= CFG["maxLag"], cards["fin"])
    # verify: finalized on the page must equal the chain's own finalized block (live), and the card must be the max lag of the shown providers
    now_fin = {}
    for k, c in w.items():
        try: now_fin[k] = c.eth.get_block("finalized").number
        except Exception: pass
    bad_f = {k: (shown[k].get("fin"), now_fin[k]) for k in now_fin
             if shown.get(k, {}).get("up") and shown[k].get("fin") is not None
             and not (now_fin[k] - slack <= shown[k]["fin"] <= now_fin[k])}
    lags = [shown[k]["height"] - shown[k]["fin"] for k in w if shown.get(k, {}).get("up") and shown[k].get("fin") is not None]
    check("P-1 finalized on page = chain finalized; card = max lag of providers",
          bool(now_fin) and not bad_f and bool(lags) and cards["fin"].isdigit() and int(cards["fin"]) == max(lags),
          f"card {cards['fin']}, page lags {lags}, off: {bad_f}")
    check("P-1 no provider shows finalized ahead of its height", bool(lags) and min(lags) >= 0, f"page lags {lags}")
    # P-4: recompute block time and tx/block from the same 50 blocks
    head, W = st["stats"]["head"], CFG["window"]
    blocks = [ref.eth.get_block(head - i) for i in range(W)]
    dt = blocks[0].timestamp - blocks[-1].timestamp
    bt, txb = dt / (W - 1), sum(len(b.transactions) for b in blocks) / W
    check("P-4 block time = recomputed", abs(st["stats"]["bt"] - bt) < 1e-9, f"{st['stats']['bt']:.4f} vs {bt:.4f}")
    check("P-4 tx/block = recomputed", abs(st["stats"]["txb"] - txb) < 1e-9, f"{st['stats']['txb']:.3f} vs {txb:.3f}")
    check("P-4 card shows the same", cards["bt"] == f"{bt:.2f}", f"{cards['bt']} vs {bt:.2f}")
    # P-3: gas price and simple transfer cost
    # node-suggested price = base fee + a varying tip; check it lies within what the chain actually charged recently
    fh = ref.eth.fee_history(100, "latest", [99])
    lo = min(fh["baseFeePerGas"]); hi = max(fh["baseFeePerGas"]) + max(max(r[0] for r in fh["reward"]), ref.eth.gas_price - lo)
    check("P-3 gas price within chain base fee … base + max tip", lo <= st["gasPrice"] <= hi * 1.05,
          f"{st['gasPrice'] / 1e9:.2f} in [{lo / 1e9:.2f}, {hi / 1e9:.2f}] gwei")
    check("P-3 cost card = 21000 × gas", cards["cost"] == f"{st['gasPrice'] * 21000 / 1e18:.6f}", cards["cost"])
    # P-6: pings against the contract, the receipts and the pinger journal
    if N.get("pinger"):
        abi = json.loads((ROOT / "contracts" / "Pinger.abi.json").read_text())
        ct = ref.eth.contract(address=N["pinger"], abi=abi)
        out, total = ct.functions.recent().call()
        chain_pings = [{"seq": total - i, "block": o[1], "prevLatMs": o[3]} for i, o in enumerate(out[:10])]
        page_pings = [{"seq": p["seq"], "block": p["block"], "prevLatMs": p["prevLatMs"]} for p in st["pings"]]
        check("P-6 pings = contract (seq, block, prev latency)", page_pings == chain_pings[:len(page_pings)] and page_pings,
              f"{len(page_pings)} shown, total {total}")
        fee_ok = True
        for p in st["pings"]:
            rc = ref.eth.get_transaction_receipt(p["tx"])
            fee_ok &= rc.blockNumber == p["block"] and abs(rc.gasUsed * rc.effectiveGasPrice / 1e18 - p["fee"]) < 1e-12
        check("P-6 fee = receipt gasUsed × effectiveGasPrice", fee_ok)
        jf = ROOT / "data" / f"pings-{NET}.jsonl"
        if jf.exists():
            j = [json.loads(l) for l in jf.read_text().splitlines()]
            j = [r for r in j if r.get("pinger", "").lower() == N["pinger"].lower()]
            by_block = {r["block"]: r for r in j}
            lat_ok = all(by_block[p["block"]]["prev_latency_ms"] == p["prevLatMs"] for p in st["pings"] if p["block"] in by_block)
            check("P-6 prev latency on-chain = pinger journal", lat_ok)
            lat = sorted(p["prevLatMs"] for p in st["pings"] if p["prevLatMs"] > 0)
            if lat:
                check("P-6 median card", cards["plat"] == str(math.floor(statistics.median(lat) + 0.5)), f"{cards['plat']} vs {statistics.median(lat)}")
        # only the owner can ping
        try:
            ct.functions.ping(0, 0).call({"from": "0x000000000000000000000000000000000000dEaD"})
            check("P-5 non-owner ping reverts", False)
        except Exception:
            check("P-5 non-owner ping reverts", True)
    print(f"RESULT {'PASS' if not fails else 'FAIL'}: {len(passes)} passed, {len(fails)} failed" + (f" — {fails}" if fails else ""))
    sys.exit(1 if fails else 0)


main()
