"""Rank layout-matched candidate seeds by the stage-select dive's image loss (the dive reader's own
loss, but only over the given candidates, so pruning can't drop the truth).

    python docs/hunt/dive_rank.py VIDEO DIVE_RESULT.json SEEDS_FILE [TOP_FIT=25] [LATE=0,1,2]

SEEDS_FILE: one hex layout seed per line (optionally followed by k). Each seed is tried as the
dive's end after LATE extra draws (dive start = seed stepped back 999 + late). Coarse loss for all
(5 start offsets), then a geometry fit for the best TOP_FIT; prints fitted loss, best first.
"""
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "p2seeds", "src"))
from p2seeds import challenge_dive as cd, rng  # noqa: E402


def main():
    video, result, sf = sys.argv[1:4]
    top = int(sys.argv[4]) if len(sys.argv) > 4 else 25
    lates = [int(x) for x in (sys.argv[5] if len(sys.argv) > 5 else "0,1,2").split(",")]
    seeds = [l.split()[0] for l in open(sf) if l.strip()]
    r = json.load(open(result))
    counts, region = r["counts"], tuple(r["region"])
    scale = float(np.sqrt(r["reg"]["sx"] * r["reg"]["sy"]))
    g = cd.geometry_from_vector(r["candidates"][0]["geometry"])
    span = int((0.1 * (max(counts) - 1) + 0.5 * 4) / cd.TIMER_SPEED + 45)
    dv = cd.DiveVideo(video, int(g.f0) + 2, int(g.f0) + span, None, region, scale=scale)
    for fr in r.get("dropped", []):
        dv.obs.pop(fr, None)
    frames = sorted(dv.obs)
    items = []
    for s in seeds:
        for late in lates:
            for hi in (0, 0x80000000):
                items.append((s, late, rng.prev_seed(int(s, 16) | hi, 999 + late)))
    st = np.array([x[2] for x in items], np.uint32)
    coarse = cd.fast_loss(dv, counts, g, st, f0_offsets=(-3.0, -1.5, 0.0, 1.5, 3.0))
    order = np.argsort(coarse)
    ref = [(f"reader {c['state']:08X}", "-", c["state"]) for c in r["candidates"][:2]]
    out = []
    for i in list(order[:top]):
        s, late, state = items[i]
        flat = cd.flatten(cd.dive_params(state, counts))
        _, l2 = cd.fit_geometry(dv, flat, g, frames, fast=True, anchor=g, state=state, counts=counts)
        out.append((min(l2, float(coarse[i])), s, late, state, float(coarse[i])))
        print(f"  {s} late {late} state {state:08X} coarse {coarse[i]:9.0f} fitted {out[-1][0]:9.0f}", flush=True)
    for lab, _, state in ref:
        flat = cd.flatten(cd.dive_params(state, counts))
        c0 = float(cd.fast_loss(dv, counts, g, np.array([state], np.uint32), f0_offsets=(-3.0, -1.5, 0.0, 1.5, 3.0))[0])
        _, l2 = cd.fit_geometry(dv, flat, g, frames, fast=True, anchor=g, state=state, counts=counts)
        print(f"  {lab}: coarse {c0:9.0f} fitted {min(l2, c0):9.0f}")
    print("ranked:")
    for x in sorted(out)[:10]:
        print(f"  {x[1]} late {x[2]} fitted {x[0]:9.0f} (coarse {x[4]:9.0f})")


if __name__ == "__main__":
    main()
