#!/usr/bin/env python3
"""Cheap health watch for arc-pulse + the DoraHacks mailbox (no Claude). Agent script task `arc-watch`, hourly.

Checks: dashboard 200; x402 /metrics → 402 with our payTo; last on-chain ping < 40 min old; project wallet ≥ 0.5 USDC (ping fuel);
new mail in the DoraHacks mailbox (results, messages from organisers). Problems (on change) and new mail → comment in Linear CRO-104.
Exit 1 while any check fails (visible in `agent history` and to the watchdog).
"""
import json, subprocess, time, urllib.request
from pathlib import Path
from web3 import Web3

ROOT = Path(__file__).resolve().parent.parent
STATE = Path("/opt/agent/state/arc-watch.json")
ISSUE = "CRO-104"
DASH = "https://eaxgtfcs-glitch.github.io/arc-pulse/"
X402 = "https://arc-pulse-x402.arc-pulse.workers.dev/metrics"
UA = {"User-Agent": "arc-pulse-watch/1.0"}
cfg = json.loads((ROOT / "config.json").read_text())["networks"]["mainnet"]
addr = Path("/etc/agent/arc.address").read_text().strip()


def http(url):
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()
    except Exception as e:
        return None, str(e).encode()


def checks():
    bad = []
    st, _ = http(DASH)
    if st != 200:
        bad.append(f"дашборд: HTTP {st}")
    st, body = http(X402)
    try:
        ok = st == 402 and json.loads(body)["accepts"][0]["payTo"].lower() == addr.lower()
    except Exception:
        ok = False
    if not ok:
        bad.append(f"x402: HTTP {st}, ожидался 402 с нашим payTo")
    w3 = next((w for w in (Web3(Web3.HTTPProvider(r["url"], request_kwargs={"timeout": 20})) for r in cfg["rpcs"]) if _alive(w)), None)
    if not w3:
        return bad + ["ни один RPC мейннета не отвечает"]
    abi = json.loads((ROOT / "contracts" / "Pinger.abi.json").read_text())
    pings, _ = w3.eth.contract(address=cfg["pinger"], abi=abi).functions.recent().call()
    age = time.time() - pings[0][2] if pings else 1e9
    if age > 40 * 60:
        bad.append(f"пинги: последний {age / 60:.0f} мин назад (норма 10)")
    bal = w3.eth.get_balance(addr) / 1e18
    if bal < 0.5:
        bad.append(f"баланс кошелька {bal:.3f} USDC — пополнить (пинги ≈ $0,15/сут)")
    return bad


def _alive(w):
    try:
        return w.eth.block_number > 0
    except Exception:
        return False


def mail(seen):
    out = subprocess.run([str(ROOT / ".venv/bin/python"), str(ROOT / "tools/mailbox.py"), "list"], capture_output=True, text=True, timeout=120)
    new = []
    for line in out.stdout.splitlines():
        m = json.loads(line)
        if m["id"] not in seen:
            seen.append(m["id"]); new.append(m)
    return new


def comment(text):
    subprocess.run(["agent", "linear", "comment", ISSUE, text], capture_output=True, timeout=60)


def main():
    if not STATE.exists():   # first run: mail already in the box (login codes) is old news
        s = {"bad": [], "seen": []}; mail(s["seen"])
    else:
        s = json.loads(STATE.read_text())
    bad = checks()
    if bad != s["bad"]:
        comment("**Сторож arc-pulse:** " + ("; ".join(bad) if bad else "всё снова работает (дашборд, x402, пинги, баланс)"))
    for m in mail(s["seen"]):
        body = "" if "code" in m["subject"].lower() else f"\n\n{m['intro']}"   # login codes stay out of Linear
        comment(f"**Новое письмо (DoraHacks-ящик):** от {m['from']} — «{m['subject']}»{body}")
    s["bad"] = bad
    STATE.write_text(json.dumps(s, ensure_ascii=False))
    print("; ".join(bad) or "ok")
    raise SystemExit(1 if bad else 0)


main()
