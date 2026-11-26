"""How specific a candidate's visible objects are: scan COUNT seeds before END for each of the
given observations ("an object named N within TOL of (ahead, side)") and report how many seeds
pass each one alone and all together, and where the candidate (and seeds fitting all) sit.

    python docs/ch_hunt/specificity.py SUB END COUNT OBS.json [--seed HEX]

OBS.json: [{"names": [...], "ahead": a, "side": s, "tol": t, "what": "...", "negate": false}, ...]
(<= 32). With "negate": true the observation holds when no such object is there.
"""
import argparse
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "layout_matcher"))
import lm  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("sub"), ap.add_argument("end"), ap.add_argument("count", type=int), ap.add_argument("obs")
    ap.add_argument("--out", default=None), ap.add_argument("--show", type=int, default=20)
    a = ap.parse_args()
    obs = json.load(open(a.obs))
    obs = obs["obs"] if isinstance(obs, dict) else obs
    end = int(a.end, 16)
    out = a.out or os.path.splitext(a.obs)[0] + "_scan.bin"
    bits = lm.scan(a.sub, end, a.count, [dict(names=o["names"], ahead=o["ahead"], side=o["side"], tol=o["tol"]) for o in obs], out)
    neg = sum(1 << j for j, o in enumerate(obs) if o.get("negate"))
    bits = bits ^ np.uint32(neg)      # "negate": true observations hold when nothing matches there
    full = (1 << len(obs)) - 1
    alive = np.ones(a.count, bool)
    for j, o in enumerate(obs):
        b = (bits >> j) & 1 == 1
        alive &= b
        print(f"  {o.get('what', o['names'])!s:40.40s} alone {b.mean():6.1%}  cumulative survivors {alive.sum()}")
    cnt = np.zeros(a.count, np.int32)
    for j in range(len(obs)):
        cnt += ((bits >> j) & 1).astype(np.int32)
    print("count histogram (top):", {int(c): int((cnt == c).sum()) for c in range(len(obs) - 3, len(obs) + 1)})
    for k in np.argsort(-cnt, kind="stable")[:a.show]:
        s = lm.seed_at(end, int(k)) & 0x7FFFFFFF
        print(f"  k {int(k):8d} seed {s:08X} passes {cnt[k]}/{len(obs)}")


if __name__ == "__main__":
    main()
