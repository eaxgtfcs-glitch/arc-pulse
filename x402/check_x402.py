#!/usr/bin/env python3
"""Check the paid API with REAL payments on Arc testnet (P-10). Starts its own server instance from a given dir.

  check_x402.py [--srcdir x402] [--net testnet]       exit 0 only if every case behaves

Cases: unpaid → 402 with a valid offer; correct payment → 200, payment-response, and an on-chain USDC Transfer
(from the buyer, to payTo, ≥ price) independently confirmed from the receipt by THIS script; replay of the same
header → 402; underpay (1 atomic unit — on Arc its native mirror Transfer is ×1e12, the classic trap) → 402;
payment to the wrong payee → 402; receipt older than maxReceiptAgeSeconds → 402; metrics ≈ chain.
"""
import base64, json, os, socket, subprocess, sys, time, urllib.request, urllib.error
from pathlib import Path
from web3 import Web3

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
SRC = Path(sys.argv[sys.argv.index("--srcdir") + 1]).resolve() if "--srcdir" in sys.argv else HERE
NET = sys.argv[sys.argv.index("--net") + 1] if "--net" in sys.argv else "testnet"
PY = str(ROOT / ".venv/bin/python")
CFG = json.loads((ROOT / "config.json").read_text())
w3 = Web3(Web3.HTTPProvider(CFG["networks"][NET]["rpcs"][0]["url"], request_kwargs={"timeout": 20}))
wm = Web3(Web3.HTTPProvider(CFG["networks"]["mainnet"]["rpcs"][0]["url"], request_kwargs={"timeout": 20}))
BUYER = Path("/etc/agent/arc-buyer.address").read_text().strip()
HDR = f"/tmp/x402-last-header-{os.getpid()}"          # per-run: a shared fixed path was overwritten by concurrent runs ('too old' check replayed a foreign payment)
os.environ["X402_HEADER_FILE"] = HDR
fails, passes = [], []
T_TRANSFER = Web3.keccak(text="Transfer(address,address,uint256)").hex().removeprefix("0x")


def check(name, ok, info=""):
    (passes if ok else fails).append(name)
    print(("PASS " if ok else "FAIL ") + name + (f" — {info}" if info else ""), flush=True)


def server(max_age=600):
    s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
    db = f"/tmp/x402-check-{port}.sqlite"
    env = {**os.environ, "ARC_PULSE_ROOT": str(ROOT), "X402_NET": NET, "X402_PORT": str(port), "X402_DB": db, "X402_MAX_AGE": str(max_age),
           "X402_PUBLIC_URL": "http://x402-check.local"}   # same resource for every instance → same nonce binding
    p = subprocess.Popen([PY, str(SRC / "server.py")], env=env, cwd=str(ROOT), stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    for _ in range(50):
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=2); break
        except Exception:
            time.sleep(0.2)
    else:
        sys.exit("SERVER DID NOT START: " + p.stderr.read().decode()[-500:] if p.poll() is not None else "SERVER DID NOT START")
    return p, f"http://127.0.0.1:{port}/metrics"


def buy(url, *extra):
    out = subprocess.run([PY, str(HERE / "pay.py"), url, "--net", NET, *extra], capture_output=True, text=True, timeout=180)
    try:
        return json.loads(out.stdout.strip().splitlines()[-1])
    except Exception:
        return {"status": None, "err": (out.stdout + out.stderr)[-400:]}


def main():
    p, url = server()
    try:
        try:
            urllib.request.urlopen(url, timeout=20); st = 200; body = {}
        except urllib.error.HTTPError as e:
            st, body = e.code, json.loads(e.read())
        acc = (body.get("accepts") or [{}])[0]
        check("unpaid → 402 with offer", st == 402 and acc.get("extra", {}).get("assetTransferMethod") == "eip3009-client-broadcast"
              and acc.get("asset", "").lower() == "0x3600000000000000000000000000000000000000", f"{st}")
        price, pay_to = int(acc["amount"]), acc["payTo"].lower()
        check("offer payTo = our wallet (independent of the server's own config)", pay_to == Path("/etc/agent/arc.address").read_text().strip().lower(), pay_to)
        r = buy(url)
        check("correct payment → 200", r.get("status") == 200, str(r.get("status")) + " " + str(r.get("err", ""))[:200])
        if r.get("status") == 200:
            rc = w3.eth.get_transaction_receipt(r["tx"])
            ok = any(l.address.lower() == "0x3600000000000000000000000000000000000000" and l.topics[0].hex().removeprefix("0x") == T_TRANSFER
                     and "0x" + l.topics[1].hex()[-40:] == BUYER.lower() and "0x" + l.topics[2].hex()[-40:] == pay_to
                     and int(l.data.hex(), 16) >= price for l in rc.logs)
            check("payment is a real USDC Transfer buyer → payTo ≥ price (receipt)", ok, r["tx"][:14])
            pr = json.loads(base64.b64decode(r["payment_response"])) if r.get("payment_response") else {}
            check("payment-response names tx and payer", pr.get("transaction", "").lower() == r["tx"].lower()
                  and pr.get("payer", "").lower() == BUYER.lower(), str(pr)[:120])
            m = r["body"]; head = wm.eth.block_number
            check("metrics ≈ mainnet chain", head - 40 <= m.get("height", 0) <= head + 2 and m.get("chainId") == 5042, f"{m.get('height')} vs {head}")
            rep = subprocess.run([PY, str(HERE / "pay.py"), url, "--net", NET, "--replay", HDR], capture_output=True, text=True, timeout=60)
            rs = json.loads(rep.stdout.strip().splitlines()[-1]) if rep.stdout.strip() else {}
            check("replay of the same payment → 402 (already used)", rs.get("status") == 402 and "already used" in str(rs), str(rs)[:160])
        r = buy(url, "--amount-override", "1")
        check("underpay (1 unit; mirror Transfer is ×1e12) → 402 (no USDC Transfer for amount)", r.get("status") == 402 and "no single USDC Transfer" in str(r.get("body")), str(r.get("body", r))[:160])
        r = buy(url, "--pay-to-override", BUYER)
        check("payment to wrong payee → 402 (no USDC Transfer to payTo)", r.get("status") == 402 and "no single USDC Transfer" in str(r.get("body")), str(r.get("body", r))[:160])
    finally:
        p.terminate()
    p, url = server(max_age=5)
    try:
        hdr_run = buy(url)  # pays, served (fresh), then the header is presented again after the age window from a NEW server db
    finally:
        p.terminate()
    p2, url2 = server(max_age=5)
    try:
        time.sleep(12)
        rep = subprocess.run([PY, str(HERE / "pay.py"), url2, "--net", NET, "--replay", HDR], capture_output=True, text=True, timeout=60)
        rs = json.loads(rep.stdout.strip().splitlines()[-1]) if rep.stdout.strip() else {}
        check("receipt older than maxReceiptAgeSeconds → 402 (too old; fresh server, empty replay store)", rs.get("status") == 402 and "too old" in str(rs), str(rs)[:160])
    finally:
        p2.terminate()
    print(f"RESULT {'PASS' if not fails else 'FAIL'}: {len(passes)} passed, {len(fails)} failed" + (f" — {fails}" if fails else ""))
    sys.exit(1 if fails else 0)


main()
