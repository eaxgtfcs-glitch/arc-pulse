#!/usr/bin/env python3
"""Check the checker: serve deliberately broken copies of the dashboard and require check_ui.py to FAIL on each.

  mutate.py [--net testnet]      exit 0 only if every mutant is caught (and the unmodified page passes)

A green check that cannot see these bugs is worthless — this keeps check_ui.py honest.
"""
import http.server, shutil, socket, subprocess, sys, tempfile, threading
from functools import partial
from pathlib import Path

ROOT = Path(__file__).parent
NET = sys.argv[sys.argv.index("--net") + 1] if "--net" in sys.argv else "testnet"
# (name, old, new) — each must change index.html exactly where intended
MUTANTS = [
    ("block time inflated", "return {bt:dt/(W-1),txb:tx/W", "return {bt:dt/(W-1)*1.1,txb:tx/W"),
    ("tx per block off by one block", "txb:tx/W,", "txb:tx/(W-1),"),
    ("ping fee scaled", "BigInt(rc.effectiveGasPrice))/1e18;", "BigInt(rc.effectiveGasPrice))/1e18*0.9;"),
    ("dead provider not shown as down", "if(!r.up)return `<tr", "if(false)return `<tr"),
    ("pings shifted (wrong block)", "block:Number(word(d,b+1))", "block:Number(word(d,b+1))+1"),
    ("gas shown from stale constant", "const g=hex((await rpc(best.url,\"eth_gasPrice\")).v);", "const g=1e9;"),
    ("finalized lag hidden", '$("fin").textContent=f.length?Math.max(...f):"n/a";', '$("fin").textContent="0";$("h").textContent=max-50;'),
]


def serve(d):
    s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
    h = partial(http.server.SimpleHTTPRequestHandler, directory=str(d))
    h.log_message = lambda *a: None
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", port), h)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{port}/"


def run_check(d):
    srv, url = serve(d)
    try:
        p = subprocess.run([sys.executable, str(ROOT / "check_ui.py"), url, "--net", NET], capture_output=True, text=True, timeout=240)
        return p.returncode, [l for l in p.stdout.splitlines() if l.startswith("FAIL")]
    finally:
        srv.shutdown()


def main():
    src = (ROOT / "index.html").read_text()
    ok = True
    with tempfile.TemporaryDirectory() as t:
        d = Path(t); shutil.copy(ROOT / "config.json", d)
        (d / "index.html").write_text(src)
        rc, _ = run_check(d)
        print(("ok   " if rc == 0 else "BAD  ") + "unmodified page passes"); ok &= rc == 0
        for name, old, new in MUTANTS:
            if src.count(old) != 1:
                print(f"BAD  mutant '{name}': anchor not found exactly once — update MUTANTS"); ok = False; continue
            (d / "index.html").write_text(src.replace(old, new))
            rc, fails = run_check(d)
            caught = rc != 0
            how = "; ".join(f[5:60] for f in fails[:2]) or "check crashed/timed out (page never reached a consistent state)"
            print(("ok   " if caught else "MISS ") + f"mutant '{name}' " + ("caught: " + how if caught else "NOT caught"))
            ok &= caught
    print("MUTATION RESULT", "PASS" if ok else "FAIL")
    sys.exit(0 if ok else 1)


main()
