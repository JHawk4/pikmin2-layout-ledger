"""scan.py SUB END_HEX COUNT OBS.json OUT.bin [show N]: survivors after each observation (in order) and all-pass seeds."""
import sys, json, numpy as np
sys.path.insert(0, "docs/layout_matcher"); sys.path.insert(0, "p2seeds/src")
import lm
sub, end, count, obsf, out = sys.argv[1], int(sys.argv[2], 16), int(sys.argv[3]), sys.argv[4], sys.argv[5]
obs = json.load(open(obsf))
m = lm.scan(sub, end, count, obs, out)
alive = np.ones(len(m), bool)
for j, o in enumerate(obs):
    b = (m >> j) & 1 == 1
    alive &= b
    print(f"{j} {o.get('label', o)}: alone {b.mean():.3f} survivors {alive.sum()}")
full = (1 << len(obs)) - 1
cnt = np.array([bin(int(x)).count("1") for x in m]) if len(m) < 2_000_000 else None
for need in (len(obs), len(obs) - 1):
    ks = np.nonzero(cnt >= need)[0]
    print(f"seeds passing >= {need}/{len(obs)}: {len(ks)}")
    for k in ks[:40]:
        miss = [j for j in range(len(obs)) if not (m[k] >> j) & 1]
        print(f"  k {k:8d} seed {lm.seed_at(end, int(k)):08X} miss {miss}")
