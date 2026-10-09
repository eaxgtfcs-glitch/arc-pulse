#!/usr/bin/env python3
"""Check the x402 checker: run check_x402.py against deliberately broken copies of the server; every mutant must FAIL.
Each mutant costs a few testnet payments (≈$0.01 of faucet USDC). Exit 0 only if all are caught."""
import shutil, subprocess, sys, tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
PY = str(HERE.parent / ".venv/bin/python")
MUTANTS = [  # (name, file, old, new)
    ("Transfer matched by topic only (Arc native mirror ×1e12 accepted)", "x402lib.py",
     "if l.address.lower() == asset and len(l.topics) == 3      # only the USDC token's own log", "if len(l.topics) == 3"),
    ("payment not claimed before serving (replay works)", "server.py",
     'c = db(); c.execute("insert into spent(nonce, tx, payer, at) values(?,?,?,?)", (nonce, pl["transaction"].lower(), payer, time.time())); c.commit()',
     "pass"),
    ("payee not checked", "x402lib.py", 'and _topic_addr(l.topics[2]) == req["payTo"].lower()', ""),
    ("amount not checked", "x402lib.py", 'and int(l.data.hex() or "0", 16) >= int(req["amount"])]', "]"),
    ("receipt age not checked", "x402lib.py", 'if now - ts > int(req["extra"].get("maxReceiptAgeSeconds", 600)) or ts - now > 30:', "if False:"),
]


def main():
    ok = True
    for name, f, old, new in MUTANTS:
        with tempfile.TemporaryDirectory() as t:
            d = Path(t) / "x402"; shutil.copytree(HERE, d, ignore=shutil.ignore_patterns("__pycache__"))
            src = (d / f).read_text()
            if src.count(old) != 1:
                print(f"BAD  mutant '{name}': anchor not found exactly once"); ok = False; continue
            (d / f).write_text(src.replace(old, new))
            p = subprocess.run([PY, str(HERE / "check_x402.py"), "--srcdir", str(d)], capture_output=True, text=True, timeout=900)
            fails = [l[5:70] for l in p.stdout.splitlines() if l.startswith("FAIL")]
            caught = p.returncode != 0 and bool(fails)          # a crash is not a catch: a specific check must fail
            print(("ok   " if caught else "MISS ") + f"mutant '{name}' " + ("caught: " + "; ".join(fails[:2]) if caught else "NOT caught" + (" (check crashed: " + (p.stdout + p.stderr)[-200:] + ")" if p.returncode else "")), flush=True)
            ok &= caught
    print("MUTATION RESULT", "PASS" if ok else "FAIL")
    sys.exit(0 if ok else 1)


main()
