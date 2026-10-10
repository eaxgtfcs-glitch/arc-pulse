// arc-pulse paid API (x402 `exact`, eip3009-client-broadcast on Arc) as a Cloudflare Worker. Replay store: D1 (primary key on nonce).
//   GET /         free: what this is and the price
//   GET /metrics  paid: verified Arc network metrics as JSON (402 without payment)
// Vars (wrangler.toml): NET (testnet|mainnet, payment network), PAY_TO, PRICE (atomic USDC, 6 dp), PUBLIC_URL, MAX_AGE (s),
//                       PAY_RPC, METRICS_RPC, METRICS_NET, METRICS_CHAIN_ID, PINGER.
// Same rules as x402/x402lib.py (spec kaditang/x402-arc): the buyer broadcasts transferWithAuthorization itself; we only decide
// whether that receipt paid THIS request, and claim its nonce before serving.

const USDC = "0x3600000000000000000000000000000000000000";
const METHOD = "eip3009-client-broadcast";
const T_TRANSFER = "ddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef";
const T_AUTH_USED = "98de503528ee59b575ef0c0a2576a82497bfc029a5685b209e9ec333479b10a5";
const SEL_RECENT = "0xbb4db8c0";
const NETWORKS = { mainnet: "eip155:5042", testnet: "eip155:5042002" };
const WINDOW = 50;

function requirements(env, path) {
  return { scheme: "exact", network: NETWORKS[env.NET], amount: String(env.PRICE), asset: USDC, payTo: env.PAY_TO,
           maxTimeoutSeconds: 300,
           extra: { assetTransferMethod: METHOD, name: "USDC", version: "2", resource: env.PUBLIC_URL.replace(/\/$/, "") + path,
                    confirmations: 1, maxReceiptAgeSeconds: Number(env.MAX_AGE || 600) } };
}

async function deriveNonce(req, clientNonce) {
  const binding = JSON.stringify([req.network, req.asset.toLowerCase(), req.payTo.toLowerCase(), req.amount, req.extra.resource || ""]);
  const data = new TextEncoder().encode("x402/exact/eip3009-client-broadcast/v1\x1f" + binding + "\x1f" + clientNonce.toLowerCase().replace(/^0x/, ""));
  const h = new Uint8Array(await crypto.subtle.digest("SHA-256", data));
  return "0x" + [...h].map(b => b.toString(16).padStart(2, "0")).join("");
}

async function rpc(url, method, params = []) {
  const r = await fetch(url, { method: "POST", headers: { "content-type": "application/json" },
                               body: JSON.stringify({ jsonrpc: "2.0", id: 1, method, params }) });
  const j = await r.json();
  if (j.error) throw new Error(`${method}: ${j.error.message}`);
  return j.result;
}

const addr = t => "0x" + t.slice(-40).toLowerCase();
const hex0 = h => h.replace(/^0x/, "");

export async function verify(env, req, pl, now = Date.now() / 1000) {
  const cn = String(pl.clientNonce || "").toLowerCase().replace(/^0x/, "");
  if (cn.length < 8 || cn.length > 64 || !/^[0-9a-f]+$/.test(cn)) return [false, "bad clientNonce", null];
  const nonce = await deriveNonce(req, cn);
  if (pl.nonce && pl.nonce.toLowerCase() !== nonce) return [false, "nonce mismatch", null];
  let rc;
  try { rc = await rpc(env.PAY_RPC, "eth_getTransactionReceipt", [pl.transaction]); } catch (e) { rc = null; }
  if (!rc) return [false, "no receipt (not yet paid)", null];
  if (Number(rc.status) !== 1) return [false, "transaction reverted", null];
  const asset = req.asset.toLowerCase();
  const auth = rc.logs.filter(l => l.address.toLowerCase() === asset && l.topics.length === 3
    && hex0(l.topics[0]) === T_AUTH_USED && l.topics[2].toLowerCase() === nonce);
  if (!auth.length) return [false, "no AuthorizationUsed with the expected nonce", null];
  const payer = addr(auth[0].topics[1]);
  const paid = rc.logs.filter(l => l.address.toLowerCase() === asset && l.topics.length === 3   // only the USDC token's own log
    && hex0(l.topics[0]) === T_TRANSFER
    && addr(l.topics[1]) === payer && addr(l.topics[2]) === req.payTo.toLowerCase()
    && BigInt(l.data === "0x" ? 0 : l.data) >= BigInt(req.amount));
  if (!paid.length) return [false, "no single USDC Transfer to payTo for the amount", payer];
  const bn = Number(rc.blockNumber), head = Number(await rpc(env.PAY_RPC, "eth_blockNumber"));
  if (Math.max(head, bn) - bn + 1 < Number(req.extra.confirmations || 1)) return [false, "not enough confirmations", payer];
  const ts = Number((await rpc(env.PAY_RPC, "eth_getBlockByNumber", [rc.blockNumber, false])).timestamp);
  if (now - ts > Number(req.extra.maxReceiptAgeSeconds || 600) || ts - now > 30) return [false, "receipt too old", payer];
  return [true, "ok", payer];
}

async function metrics(env) {
  const u = env.METRICS_RPC, q = n => "0x" + n.toString(16);
  const head = await rpc(u, "eth_getBlockByNumber", ["latest", false]), h = Number(head.number);
  const old = await rpc(u, "eth_getBlockByNumber", [q(h - (WINDOW - 1)), false]);
  const sample = await Promise.all(Array.from({ length: WINDOW / 5 }, (_, i) => rpc(u, "eth_getBlockByNumber", [q(h - i * 5), false])));
  const txs = sample.reduce((s, b) => s + b.transactions.length, 0) * 5;
  const fin = Number((await rpc(u, "eth_getBlockByNumber", ["finalized", false])).number);
  const gas = Number(BigInt(await rpc(u, "eth_gasPrice")));
  const out = { network: env.METRICS_NET, chainId: Number(env.METRICS_CHAIN_ID), height: Math.max(h, fin), finalized: fin,
                avgBlockTimeS: (Number(head.timestamp) - Number(old.timestamp)) / (WINDOW - 1), gasPriceWei: gas,
                simpleTransferCostUsdc: gas * 21000 / 1e18, txPerBlockApprox: txs / WINDOW, at: Math.floor(Date.now() / 1000) };
  if (env.PINGER) {
    const d = await rpc(u, "eth_call", [{ to: env.PINGER, data: SEL_RECENT }, "latest"]);
    const word = i => BigInt("0x" + d.slice(2 + 64 * i, 66 + 64 * i));
    const total = Number(word(1)), off = Number(word(0)) / 32, n = Number(word(off)), pings = [];
    for (let i = 0; i < n; i++) { const b = off + 1 + i * 4;
      pings.push({ block: Number(word(b + 1)), ts: Number(word(b + 2)), prevLatencyMs: Number(word(b + 3)) }); }
    const lat = pings.slice(0, 10).map(p => p.prevLatencyMs).filter(x => x > 0).sort((a, b) => a - b);
    const median = !lat.length ? null : lat.length % 2 ? lat[(lat.length - 1) / 2] : (lat[lat.length / 2 - 1] + lat[lat.length / 2]) / 2;
    Object.assign(out, { pinger: env.PINGER, pingsTotal: total, pingLatencyMedianMs: median, lastPings: pings.slice(0, 5) });
  }
  return out;
}

const b64 = s => btoa(String.fromCharCode(...new TextEncoder().encode(s)));
function send(code, body, headers = {}) {
  return new Response(JSON.stringify(body), { status: code, headers: { "content-type": "application/json", "access-control-allow-origin": "*",
    "access-control-expose-headers": "payment-required, x-payment-response, payment-response", ...headers } });
}
function challenge(env, path, error) {
  const body = { x402Version: 2, error, resource: { url: env.PUBLIC_URL.replace(/\/$/, "") + path, mimeType: "application/json" },
                 accepts: [requirements(env, path)] };
  return send(402, body, { "payment-required": b64(JSON.stringify(body)) });
}

export default {
  async fetch(request, env) {
    const path = new URL(request.url).pathname;
    if (request.method === "OPTIONS") return send(204, {}, { "access-control-allow-headers": "payment-signature, x-payment" });
    if (path === "/") return send(200, { name: "arc-pulse paid API", paid: ["/metrics"],
      price: { usdc: Number(env.PRICE) / 1e6, network: NETWORKS[env.NET] },
      method: "x402 exact / eip3009-client-broadcast (buyer broadcasts USDC transferWithAuthorization)",
      dashboard: "https://eaxgtfcs-glitch.github.io/arc-pulse/", source: "https://github.com/eaxgtfcs-glitch/arc-pulse/tree/main/x402" });
    if (path !== "/metrics") return send(404, { error: "not found" });
    const hdr = request.headers.get("PAYMENT-SIGNATURE") || request.headers.get("X-PAYMENT");
    if (!hdr) return challenge(env, path, "payment required");
    let pl;
    try { pl = JSON.parse(new TextDecoder().decode(Uint8Array.from(atob(hdr), c => c.charCodeAt(0)))).payload; if (!pl) throw 0; }
    catch (e) { return challenge(env, path, "malformed payment header"); }
    const req = requirements(env, path);                       // OUR requirements, never the echoed ones
    const [ok, reason, payer] = await verify(env, req, pl);
    if (!ok) return challenge(env, path, reason);
    const nonce = await deriveNonce(req, String(pl.clientNonce));
    try {                                                      // claim BEFORE serving: the primary key makes a replay fail here
      await env.DB.prepare("insert into spent(nonce, tx, payer, at) values(?,?,?,?)")
        .bind(nonce, String(pl.transaction).toLowerCase(), payer, Date.now() / 1000).run();
    } catch (e) { return challenge(env, path, "payment already used"); }
    let data;
    try { data = await metrics(env); }
    catch (e) { return send(502, { error: `upstream RPC failed: ${e.message}`, note: "payment claimed; contact for refund" }); }
    await env.DB.prepare("update spent set settled=1 where nonce=?").bind(nonce).run();
    const resp = { success: true, transaction: pl.transaction, network: req.network, payer };
    return send(200, data, { "x-payment-response": b64(JSON.stringify(resp)) });
  },
};
