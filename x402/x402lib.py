"""x402 'exact' scheme with the eip3009-client-broadcast transfer method on Arc (spec: kaditang/x402-arc).

The buyer broadcasts USDC transferWithAuthorization itself (on Arc, gas is USDC) and presents the tx hash + clientNonce;
the server only decides whether that transaction paid THIS request, by inspecting the receipt.
"""
import hashlib, json, time
from web3 import Web3

USDC = "0x3600000000000000000000000000000000000000"
NATIVE_MIRROR = "0xfffffffffffffffffffffffffffffffffffffffe"   # emits a second Transfer with value ×1e12 — must be ignored
METHOD = "eip3009-client-broadcast"
T_TRANSFER = Web3.keccak(text="Transfer(address,address,uint256)").hex().removeprefix("0x")
T_AUTH_USED = Web3.keccak(text="AuthorizationUsed(address,bytes32)").hex().removeprefix("0x")
NETWORKS = {"mainnet": ("eip155:5042", 5042), "testnet": ("eip155:5042002", 5042002)}


def requirements(net, pay_to, amount, resource, max_age=600, confirmations=1):
    network, _ = NETWORKS[net]
    return {"scheme": "exact", "network": network, "amount": str(amount), "asset": USDC, "payTo": pay_to,
            "maxTimeoutSeconds": 300,
            "extra": {"assetTransferMethod": METHOD, "name": "USDC", "version": "2", "resource": resource,
                      "confirmations": confirmations, "maxReceiptAgeSeconds": max_age}}


def derive_nonce(req, client_nonce):
    """nonce = SHA-256("x402/exact/eip3009-client-broadcast/v1" ‖ 0x1f ‖ binding ‖ 0x1f ‖ clientNonce) — from OUR requirements."""
    binding = json.dumps([req["network"], req["asset"].lower(), req["payTo"].lower(), req["amount"],
                          req["extra"].get("resource", "")], separators=(",", ":"))
    data = b"x402/exact/eip3009-client-broadcast/v1" + b"\x1f" + binding.encode() + b"\x1f" + client_nonce.lower().removeprefix("0x").encode()
    return "0x" + hashlib.sha256(data).hexdigest()


def _topic_addr(t):
    return "0x" + t.hex().removeprefix("0x")[-40:]


def verify(w3, req, payload, now=None):
    """-> (ok, reason, payer). Receipt inspection per the spec; does NOT claim the nonce (caller must, before serving)."""
    now = now or time.time()
    cn = str(payload.get("clientNonce", "")).lower().removeprefix("0x")
    if not (8 <= len(cn) <= 64) or any(c not in "0123456789abcdef" for c in cn):
        return False, "bad clientNonce", None
    nonce = derive_nonce(req, cn)
    if payload.get("nonce") and payload["nonce"].lower() != nonce:
        return False, "nonce mismatch", None
    try:
        rc = w3.eth.get_transaction_receipt(payload["transaction"])
    except Exception:
        return False, "no receipt (not yet paid)", None
    if rc.status != 1:
        return False, "transaction reverted", None
    asset = req["asset"].lower()
    auth = [l for l in rc.logs if l.address.lower() == asset and len(l.topics) == 3
            and l.topics[0].hex().removeprefix("0x") == T_AUTH_USED and "0x" + l.topics[2].hex().removeprefix("0x") == nonce]
    if not auth:
        return False, "no AuthorizationUsed with the expected nonce", None
    payer = _topic_addr(auth[0].topics[1])
    paid = [l for l in rc.logs if l.address.lower() == asset and len(l.topics) == 3      # only the USDC token's own log
            and l.topics[0].hex().removeprefix("0x") == T_TRANSFER
            and _topic_addr(l.topics[1]) == payer and _topic_addr(l.topics[2]) == req["payTo"].lower()
            and int(l.data.hex() or "0", 16) >= int(req["amount"])]
    if not paid:
        return False, "no single USDC Transfer to payTo for the amount", payer
    # load-balanced RPCs can answer block_number from a node behind the one that served the receipt: a receipt = ≥1 confirmation
    if max(w3.eth.block_number, rc.blockNumber) - rc.blockNumber + 1 < int(req["extra"].get("confirmations", 1)):
        return False, "not enough confirmations", payer
    ts = w3.eth.get_block(rc.blockNumber).timestamp
    if now - ts > int(req["extra"].get("maxReceiptAgeSeconds", 600)) or ts - now > 30:
        return False, "receipt too old", payer
    return True, "ok", payer
