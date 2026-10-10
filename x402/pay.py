#!/usr/bin/env python3
"""x402 buyer for Arc (eip3009-client-broadcast): GET url → 402 → sign + broadcast USDC transferWithAuthorization → retry with header.

  pay.py <url> [--net testnet] [--key /etc/agent/arc-buyer.key] [--amount-override N] [--pay-to-override 0x..] [--replay <header-file>]
The overrides exist only so the checker can produce deliberately wrong payments (underpay, wrong payee) on testnet.
"""
import base64, json, os, secrets, sys, time, urllib.request, urllib.error
from pathlib import Path
from eth_account import Account
from web3 import Web3
sys.path.insert(0, str(Path(__file__).parent))
from x402lib import USDC, NETWORKS, derive_nonce

RPC = {"testnet": "https://rpc.testnet.arc.io", "mainnet": "https://rpc.mainnet.arc.io"}
ABI = [{"name": "transferWithAuthorization", "type": "function", "stateMutability": "nonpayable", "outputs": [],
        "inputs": [{"name": "from", "type": "address"}, {"name": "to", "type": "address"}, {"name": "value", "type": "uint256"},
                   {"name": "validAfter", "type": "uint256"}, {"name": "validBefore", "type": "uint256"},
                   {"name": "nonce", "type": "bytes32"}, {"name": "v", "type": "uint8"}, {"name": "r", "type": "bytes32"},
                   {"name": "s", "type": "bytes32"}]}]


def arg(name, default=None):
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else default


def http(url, header=None):
    ua = {"User-Agent": "arc-pulse-x402-client/1.0"}   # Cloudflare answers bare Python-urllib with 403 / error 1010
    req = urllib.request.Request(url, headers={**ua, "X-PAYMENT": header, "PAYMENT-SIGNATURE": header} if header else ua)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, json.loads(r.read() or b"{}"), dict(r.headers)
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}"), dict(e.headers)


def pay(w3, acct, req, amount=None, pay_to=None):
    """Broadcast transferWithAuthorization for req (optionally wrong amount/payee) → (tx hash, clientNonce)."""
    cn = secrets.token_hex(16)
    nonce = derive_nonce(req, cn)
    to, value = Web3.to_checksum_address(pay_to or req["payTo"]), int(amount if amount is not None else req["amount"])
    now = int(time.time())
    msg = {"from": acct.address, "to": to, "value": value, "validAfter": 0, "validBefore": now + 600, "nonce": bytes.fromhex(nonce[2:])}
    sig = Account.sign_typed_data(acct.key, domain_data={"name": req["extra"]["name"], "version": req["extra"]["version"],
                                                         "chainId": w3.eth.chain_id, "verifyingContract": USDC},
                                  message_types={"TransferWithAuthorization": [
                                      {"name": "from", "type": "address"}, {"name": "to", "type": "address"},
                                      {"name": "value", "type": "uint256"}, {"name": "validAfter", "type": "uint256"},
                                      {"name": "validBefore", "type": "uint256"}, {"name": "nonce", "type": "bytes32"}]},
                                  message_data=msg)
    c = w3.eth.contract(address=USDC, abi=ABI)
    tx = c.functions.transferWithAuthorization(acct.address, to, value, 0, now + 600, msg["nonce"], sig.v,
                                               sig.r.to_bytes(32, "big"), sig.s.to_bytes(32, "big")).build_transaction(
        {"from": acct.address, "nonce": w3.eth.get_transaction_count(acct.address), "gasPrice": w3.eth.gas_price, "chainId": w3.eth.chain_id})
    tx["gas"] = int(w3.eth.estimate_gas(tx) * 1.2)
    h = w3.eth.send_raw_transaction(acct.sign_transaction(tx).raw_transaction)
    w3.eth.wait_for_transaction_receipt(h, timeout=60)
    return "0x" + h.hex().removeprefix("0x"), cn


def header_for(req, tx, cn):
    body = {"x402Version": 2, "accepted": req, "payload": {"transaction": tx, "clientNonce": cn}}
    return base64.b64encode(json.dumps(body).encode()).decode()


def main():
    url, net = sys.argv[1], arg("--net", "testnet")
    if net == "mainnet" and os.environ.get("ALLOW_MAINNET") != "1":
        sys.exit("mainnet payments need ALLOW_MAINNET=1")
    w3 = Web3(Web3.HTTPProvider(RPC[net], request_kwargs={"timeout": 20}))
    acct = Account.from_key(Path(arg("--key", "/etc/agent/arc-buyer.key")).read_text().strip())
    if arg("--replay"):
        st, body, _ = http(url, Path(arg("--replay")).read_text().strip()); print(json.dumps({"status": st, "body": body})); return
    st, body, _ = http(url)
    if st != 402:
        sys.exit(f"expected 402, got {st}")
    req = next(a for a in body["accepts"] if a["network"] == NETWORKS[net][0] and a["extra"].get("assetTransferMethod"))
    tx, cn = pay(w3, acct, req, arg("--amount-override"), arg("--pay-to-override"))
    hdr = header_for(req, tx, cn)
    Path(os.environ.get("X402_HEADER_FILE", "/tmp/x402-last-header")).write_text(hdr)
    st, body, headers = http(url, hdr)
    print(json.dumps({"status": st, "tx": tx, "payer": acct.address, "body": body,
                      "payment_response": next((v for k, v in headers.items() if k.lower() in ("x-payment-response", "payment-response")), None)}))


if __name__ == "__main__":
    main()
