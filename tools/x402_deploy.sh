#!/usr/bin/env bash
# Deploy the x402 Worker (x402/worker) to Cloudflare: D1 replay store + Worker + its public URL in PUBLIC_URL.
# Needs an API token with "Edit Cloudflare Workers" + D1 edit in /etc/agent/cloudflare.token. Idempotent.
set -euo pipefail
cd "$(dirname "$0")/../x402/worker"
export CLOUDFLARE_API_TOKEN="$(cat /etc/agent/cloudflare.token)" WRANGLER_SEND_METRICS=false CI=1
W=node_modules/.bin/wrangler
[ -x "$W" ] || npm i --no-audit --no-fund -D wrangler@4 >/dev/null
dbid() { $W d1 list --json | python3 -c 'import json,sys; print(next((d["uuid"] for d in json.load(sys.stdin) if d["name"]=="arc-pulse-x402"), ""))'; }
id=$(dbid)
[ -n "$id" ] || { $W d1 create arc-pulse-x402 >/dev/null; id=$(dbid); }
[ -n "$id" ] || { echo "D1 arc-pulse-x402 not found/created" >&2; exit 1; }
sed -i "s/^database_id = .*/database_id = \"$id\"/" wrangler.toml
$W d1 execute DB --remote --file schema.sql -y >/dev/null
url=$($W deploy 2>&1 | tee /dev/stderr | grep -oE 'https://[a-z0-9.-]+\.workers\.dev' | tail -1)
[ -n "$url" ] || { echo "no workers.dev URL in deploy output" >&2; exit 1; }
if ! grep -q "^PUBLIC_URL = \"$url\"" wrangler.toml; then
  sed -i "s|^PUBLIC_URL = .*|PUBLIC_URL = \"$url\"|" wrangler.toml
  $W deploy >/dev/null 2>&1
fi
echo "$url"
