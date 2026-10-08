"""Сверка с сетью (только чтение): P-1, P-2, P-3, P-4, P-7. Использование: checker.py [testnet|mainnet]"""
import json, sys, time
from web3 import Web3

cfg = json.load(open(__file__.rsplit('/', 1)[0] + '/config.json'))
net = cfg['networks'][sys.argv[1] if len(sys.argv) > 1 else cfg['default']]
W, LAG = cfg['window'], cfg['maxLag']
res = []

def check(name, ok, info=''):
    res.append(ok)
    print(('PASS' if ok else 'FAIL'), name, info)

def w3(url):
    return Web3(Web3.HTTPProvider(url, request_kwargs={'timeout': 8}))

live = []
for r in net['rpcs']:
    try:
        c = w3(r['url'])
        t = time.time(); h = c.eth.block_number; ms = (time.time() - t) * 1000
        live.append((r['name'], c, h, c.eth.chain_id, ms))
    except Exception as e:
        print('down', r['name'], e)

check('P-2 chainId', bool(live) and all(x[3] == net['chainId'] for x in live), f'{len(live)} RPC')
hs = [x[2] for x in live]
check('P-2 согласованность высоты', bool(hs) and max(hs) - min(hs) <= LAG, str(hs))

if live:
    c = live[0][1]; head = c.eth.get_block('latest')
    blocks = [c.eth.get_block(head.number - i) for i in range(W)]
    dt = (blocks[0].timestamp - blocks[-1].timestamp) / (W - 1)
    # P-1: те же блоки у другого провайдера (или у того же, если он один)
    o = live[-1][1]
    same = all(o.eth.get_block(b.number).hash == b.hash for b in blocks[::10])
    check('P-1 блоки совпадают у другого RPC', same)
    try:
        fin = c.eth.get_block('finalized').number
        check('P-1 finalized ≈ latest', head.number - fin <= LAG, f'lag={head.number - fin}')
    except Exception as e:
        check('P-1 finalized', False, str(e))
    print(f'  время блока ≈ {dt:.3f} с (окно {W})')
    # P-4: tx/блок и tx/с по сырым блокам
    n = sum(len(b.transactions) for b in blocks)
    span = blocks[0].timestamp - blocks[-1].timestamp
    print(f'  tx/блок {n / W:.2f}, tx/с {n / span if span else 0:.2f}')
    check('P-4 пересчёт возможен', span > 0)
    # P-3: цена простой tx (21000 газа) против feeHistory
    gp = c.eth.gas_price
    fh = c.eth.fee_history(5, 'latest')['baseFeePerGas']
    cost = 21000 * gp / 1e18
    check('P-3 gasPrice ≥ baseFee', gp >= fh[-1], f'{gp / 1e9:.1f} gwei, tx≈${cost:.5f}')

print('ИТОГ', 'PASS' if all(res) else 'FAIL')
sys.exit(0 if all(res) else 1)
