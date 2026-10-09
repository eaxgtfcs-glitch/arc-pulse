# make check — local gate: syntax, contract build, no secrets, network checks (reads only), dashboard vs chain in a real browser.
PY=.venv/bin/python
NET?=testnet
URL?=https://eaxgtfcs-glitch.github.io/arc-pulse/
check:
	$(PY) -m py_compile ping.py checker.py check_ui.py
	$(PY) -c "import solcx; solcx.compile_files(['contracts/Pinger.sol'], solc_version='0.8.24')"
	! git grep -n -I -E '(0x)?[0-9a-fA-F]{64}' -- ':!contracts/*.json' ':!data/*' | grep -v -i -E 'topic|keccak|TOPIC_PING|hash' || (echo 'possible private key in repo'; exit 1)
	! git ls-files | grep -E '\.key$$|\.env$$'
	ARC_ADDR=$$(cat /etc/agent/arc.address) $(PY) checker.py $(NET)
	$(PY) check_ui.py $(URL) --net $(NET)
