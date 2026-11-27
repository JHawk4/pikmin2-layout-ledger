"""Dive-image loss of given floor-1 layout seeds, next to the dive reader's own best states.

    python docs/layout_matcher/dive_check.py VIDEO DIVE_RESULT.json SEED [SEED ...]

The dive's first state is the layout seed stepped back 999 draws (challenge_dive.layout_seed).
Each state gets a geometry fit from the reader's best geometry, as rank_filtered.py does.
"""
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "p2seeds", "src"))
from p2seeds.challenge import dive as cd
from p2seeds import rng  # noqa: E402


def main():
    video, result = sys.argv[1:3]
    seeds = [int(s, 16) for s in sys.argv[3:]]
    r = json.load(open(result))
    counts, region = r["counts"], tuple(r["region"])
    scale = float(np.sqrt(r["reg"]["sx"] * r["reg"]["sy"]))
    g = cd.geometry_from_vector(r["candidates"][0]["geometry"])
    span = int((0.1 * (max(counts) - 1) + 0.5 * 4) / cd.TIMER_SPEED + 45)
    dv = cd.DiveVideo(video, int(g.f0) + 2, int(g.f0) + span, None, region, scale=scale)
    for fr in r.get("dropped", []):
        dv.obs.pop(fr, None)
    frames = sorted(dv.obs)
    states = []
    for s in seeds:
        for hi in (0, 0x80000000):
            states.append((f"layout {s:08X}{' (bit31)' if hi else ''}", rng.prev_seed(s | hi, 999)))
    for c in r["candidates"][:3]:
        states.append((f"reader {c['state']:08X} -> {cd.layout_seed(c['state']) & 0x7FFFFFFF:08X}", c["state"]))
    for label, s in states:
        flat = cd.flatten(cd.dive_params(s, counts))
        coarse = float(cd.fast_loss(dv, counts, g, np.array([s], np.uint32), f0_offsets=(-3.0, -1.5, 0.0, 1.5, 3.0))[0])
        _, l2 = cd.fit_geometry(dv, flat, g, frames, fast=True, anchor=g, state=s, counts=counts)
        print(f"{label:45s} state {s:08X}  coarse {coarse:9.0f}  fitted {min(l2, coarse):9.0f}", flush=True)


if __name__ == "__main__":
    main()
