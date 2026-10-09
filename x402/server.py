#!/usr/bin/env python3
"""arc-pulse paid API (x402, eip3009-client-broadcast on Arc). stdlib HTTP server, SQLite replay store.

  GET /           free: what this is and the price
  GET /metrics    paid: verified Arc network metrics as JSON (402 without payment)
Env: X402_NET (testnet|mainnet, payment network), X402_PAY_TO, X402_PRICE (atomic USDC, 6 dp; default 10000 = $0.01),
     X402_PUBLIC_URL (resource URL in the offer), X402_DB, X402_PORT (default 8402), METRICS_NET (default mainnet).
"""
import base64, json, os, sqlite3, statistics, sys, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from web3 import Web3
sys.path.insert(0, str(Path(__file__).parent))
from x402lib import requirements, derive_nonce, verify

ROOT = Path(os.environ.get("ARC_PULSE_ROOT") or Path(__file__).resolve().parent.parent)
CFG = json.loads((ROOT / "config.json").read_text())
NET = os.environ.get("X402_NET", "testnet")
PAY_TO = os.environ.get("X402_PAY_TO") or Path("/etc/agent/arc.address").read_text().strip()
PRICE = int(os.environ.get("X402_PRICE", "10000"))
PUBLIC = os.environ.get("X402_PUBLIC_URL", "http://127.0.0.1:8402").rstrip("/")
DB = os.environ.get("X402_DB", str(ROOT / "data" / f"x402-{NET}.sqlite"))
MNET = os.environ.get("METRICS_NET", "mainnet")
w3pay = Web3(Web3.HTTPProvider(CFG["networks"][NET]["rpcs"][0]["url"], request_kwargs={"timeout": 15}))
w3m = Web3(Web3.HTTPProvider(CFG["networks"][MNET]["rpcs"][0]["url"], request_kwargs={"timeout": 15}))
lock = threading.Lock()


def db():
    c = sqlite3.connect(DB, timeout=10)
    c.execute("create table if not exists spent(nonce text primary key, tx text unique, payer text, at real, settled int default 0)")
    return c


def req_for(path):
    return requirements(NET, PAY_TO, PRICE, PUBLIC + path, max_age=int(os.environ.get("X402_MAX_AGE", "600")))


def metrics():
    head = w3m.eth.get_block("latest"); W = CFG["window"]
    old = w3m.eth.get_block(head.number - (W - 1))
    txs = sum(len(w3m.eth.get_block(head.number - i).transactions) for i in range(0, W, 5)) * 5
    fin = w3m.eth.get_block("finalized").number   # load-balanced RPC may serve finalized from a fresher node: head ≥ finalized
    out = {"network": MNET, "chainId": CFG["networks"][MNET]["chainId"], "height": max(head.number, fin),
           "finalized": fin, "avgBlockTimeS": (head.timestamp - old.timestamp) / (W - 1),
           "gasPriceWei": w3m.eth.gas_price, "simpleTransferCostUsdc": w3m.eth.gas_price * 21000 / 1e18,
           "txPerBlockApprox": txs / W, "at": int(time.time())}
    pinger = CFG["networks"][MNET].get("pinger")
    if pinger:
        abi = json.loads((ROOT / "contracts" / "Pinger.abi.json").read_text())
        pings, total = w3m.eth.contract(address=pinger, abi=abi).functions.recent().call()
        lat = [p[3] for p in pings[:10] if p[3] > 0]
        out.update(pinger=pinger, pingsTotal=total, pingLatencyMedianMs=statistics.median(lat) if lat else None,
                   lastPings=[{"block": p[1], "ts": p[2], "prevLatencyMs": p[3]} for p in pings[:5]])
    return out


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def send(self, code, body, headers=None):
        raw = json.dumps(body).encode()
        self.send_response(code)
        for k, v in {"content-type": "application/json", "access-control-allow-origin": "*",
                     "access-control-expose-headers": "payment-required, x-payment-response, payment-response", **(headers or {})}.items():
            self.send_header(k, v)
        self.end_headers(); self.wfile.write(raw)

    def challenge(self, path, error):
        body = {"x402Version": 2, "error": error, "resource": {"url": PUBLIC + path, "mimeType": "application/json"}, "accepts": [req_for(path)]}
        self.send(402, body, {"payment-required": base64.b64encode(json.dumps(body).encode()).decode()})

    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/":
            return self.send(200, {"name": "arc-pulse paid API", "paid": ["/metrics"], "price": {"usdc": PRICE / 1e6, "network": req_for("/metrics")["network"]},
                                   "method": "x402 exact / eip3009-client-broadcast (buyer broadcasts USDC transferWithAuthorization)",
                                   "dashboard": "https://eaxgtfcs-glitch.github.io/arc-pulse/"})
        if path != "/metrics":
            return self.send(404, {"error": "not found"})
        hdr = self.headers.get("PAYMENT-SIGNATURE") or self.headers.get("X-PAYMENT")
        if not hdr:
            return self.challenge(path, "payment required")
        try:
            pl = json.loads(base64.b64decode(hdr))["payload"]
        except Exception:
            return self.challenge(path, "malformed payment header")
        req = req_for(path)                                   # OUR requirements, never the echoed ones
        ok, reason, payer = verify(w3pay, req, pl)
        if not ok:
            return self.challenge(path, reason)
        nonce = derive_nonce(req, pl["clientNonce"])
        with lock:                                            # claim BEFORE serving (spec: claim ordering)
            try:
                c = db(); c.execute("insert into spent(nonce, tx, payer, at) values(?,?,?,?)", (nonce, pl["transaction"].lower(), payer, time.time())); c.commit()
            except sqlite3.IntegrityError:
                return self.challenge(path, "payment already used")
        try:
            data = metrics()
        except Exception as e:
            return self.send(502, {"error": f"upstream RPC failed: {e}", "note": "payment claimed; contact for refund"})
        c = db(); c.execute("update spent set settled=1 where nonce=?", (nonce,)); c.commit()
        resp = {"success": True, "transaction": pl["transaction"], "network": req["network"], "payer": payer}
        self.send(200, data, {"x-payment-response": base64.b64encode(json.dumps(resp).encode()).decode()})


if __name__ == "__main__":
    Path(DB).parent.mkdir(parents=True, exist_ok=True); db().close()
    ThreadingHTTPServer(("127.0.0.1", int(os.environ.get("X402_PORT", "8402"))), H).serve_forever()
