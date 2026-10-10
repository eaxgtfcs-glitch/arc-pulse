# make check — local gate: syntax, contract build, no secrets, network checks (reads only), dashboard vs chain in a real browser.
PY=.venv/bin/python
NET?=testnet
URL?=https://eaxgtfcs-glitch.github.io/arc-pulse/
check:
	$(PY) -m py_compile ping.py checker.py check_ui.py
	$(PY) -c "import solcx; solcx.compile_files(['contracts/Pinger.sol'], solc_version='0.8.24')"
	K=$$(tr -d '[:space:]' < /etc/agent/arc.key | sed 's/^0x//'); [ -n "$$K" ] && ! git grep -q -I -i -F "$$K" $$(git rev-list --all | head -50) || (echo 'private key in repo'; exit 1)
	! git ls-files | grep -E '\.key$$|\.env$$'
	ARC_ADDR=$$(cat /etc/agent/arc.address) $(PY) checker.py $(NET)
	$(PY) check_ui.py $(URL) --net $(NET)

# make mutate — check the checker: broken copies of the page must all FAIL check_ui.py (≈5 min)
mutate:
	$(PY) mutate.py --net $(NET)

# make verify — what the independent verifier runs
x402-check:
	$(PY) x402/check_x402.py --net testnet

x402-mutate:
	$(PY) x402/mutate_x402.py

x402-live:   # the deployed endpoint, real mainnet payments (~$0.02)
	ALLOW_MAINNET=1 $(PY) x402/check_x402.py --url https://arc-pulse-x402.arc-pulse.workers.dev/metrics --net mainnet

verify: check mutate x402-check x402-mutate
