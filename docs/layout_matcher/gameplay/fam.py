"""fam.py SUB SEED [R=10]: neighbours SEED-R..SEED+R (RNG steps): objects in pod frame, and the diff to SEED."""
import sys, os
sys.path.insert(0, "docs/layout_matcher"); sys.path.insert(0, "p2seeds/src")
import lm
from p2seeds import rng
sub, s0 = sys.argv[1], int(sys.argv[2], 16); R = int(sys.argv[3]) if len(sys.argv) > 3 else 10
seeds = [rng.prev_seed(s0, -d) if d < 0 else rng.next_seed(s0, d) for d in range(-R, R + 1)]
seeds = [rng.prev_seed(s0, R - i) if i < R else rng.next_seed(s0, i - R) for i in range(2 * R + 1)]
ds = lm.dump(sub, *seeds)
def objs(d):
    return sorted((o["names"][0], round(o["ahead"] / 30) * 30, round(o["side"] / 30) * 30) for o in d["objects"])
base = objs(ds[R])
if len(sys.argv) > 4:
    print(ds[R].get("pod")); [print(o) for o in base]
for i, d in enumerate(ds):
    o = objs(d); same = len(set(o) & set(base))
    print(f"{i - R:+3d} {seeds[i]:08X} pod={d.get('pod',{}).get('unit_spawn')} objs={len(o)} same_as_center={same}")
