#!/usr/bin/env python3
"""Temporary mailbox (mail.tm API) for service sign-ups: mailbox.py create | code [--wait 120]. Credentials: /etc/agent/dorahacks.env."""
import json, os, re, secrets, sys, time, urllib.request
ENV = "/etc/agent/dorahacks.env"
def api(method, path, body=None, token=None):
    h = {"content-type": "application/json", "accept": "application/json"}
    if token: h["authorization"] = "Bearer " + token
    req = urllib.request.Request("https://api.mail.tm" + path, data=json.dumps(body).encode() if body else None, headers=h, method=method)
    with urllib.request.urlopen(req, timeout=20) as r:
        d = json.load(r)
    return d["hydra:member"] if isinstance(d, dict) and "hydra:member" in d else d
def creds():
    return dict(l.split("=", 1) for l in open(ENV).read().split())
if sys.argv[1] == "create":
    if os.path.exists(ENV): print(creds()["MAIL_ADDRESS"]); sys.exit()
    d = api("GET", "/domains")[0]["domain"]; addr = f"arcpulse{secrets.token_hex(3)}@{d}"; pw = "Ap" + secrets.token_hex(8)  # точка в адресе и спецсимволы ломают вход mail.tm
    api("POST", "/accounts", {"address": addr, "password": pw})
    os.umask(0o077); open(ENV, "w").write(f"MAIL_ADDRESS={addr}\nMAIL_PASSWORD={pw}\n"); print(addr)
elif sys.argv[1] == "code":
    c = creds(); tok = api("POST", "/token", {"address": c["MAIL_ADDRESS"], "password": c["MAIL_PASSWORD"]})["token"]
    wait = int(sys.argv[sys.argv.index("--wait") + 1]) if "--wait" in sys.argv else 120
    since = time.time() - int(os.environ.get("SINCE", "600"))
    for _ in range(wait // 5):
        for m in api("GET", "/messages", token=tok):
            full = api("GET", "/messages/" + m["id"], token=tok)
            text = (full.get("text") or "") + " " + " ".join(full.get("html") or [])
            if "dora" in (m.get("from", {}).get("address", "") + m.get("subject", "")).lower():
                codes = re.findall(r"\b(\d{6})\b", text)
                if codes: print(codes[0]); sys.exit()
        time.sleep(5)
    sys.exit("код не пришёл")
