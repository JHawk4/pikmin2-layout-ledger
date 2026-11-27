"""Rank dive candidates that pass a layout filter (itemscan output) by the dive image loss.

    python docs/challenge_dive/rank_filtered.py VIDEO RESULT.json SCAN.bin END_STATE NITEMS ITEM_COL DIST [DIST ...]

SCAN.bin comes from `p2seeds-cg3`'s itemscan (seed k = END_STATE stepped back k draws). Layout
seeds whose item column ITEM_COL equals one of the DIST values (to 0.5 units) are kept; their dive
first states (layout seed - 999 draws) are scored with fast_loss at the read's best geometry over
dive-start offsets, then the best few get a full geometry fit.
"""

import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "p2seeds", "src"))
from p2seeds.challenge import dive as cd
from p2seeds import rng  # noqa: E402


def main():
    video, result, scan, end, ni, col = sys.argv[1:7]
    dists = [float(x) for x in sys.argv[7:]]
    end, ni, col = int(end, 16), int(ni), int(col)
    a = np.fromfile(scan, np.float32).reshape(-1, ni)[:, col]
    keep = np.zeros(len(a), bool)
    for d in dists:
        keep |= np.abs(a - d) < 0.5
    ks = np.nonzero(keep)[0]
    print(f"{len(ks)} of {len(a)} layouts pass", flush=True)
    # dive first state of layout k: end stepped back k + 999 draws
    first = np.array(cd.window_states(end, len(a)))[ks]
    r = json.load(open(result))
    counts, region = r["counts"], tuple(r["region"])
    scale = float(np.sqrt(r["reg"]["sx"] * r["reg"]["sy"]))
    g = cd.geometry_from_vector(r["candidates"][0]["geometry"])
    span = int((0.1 * (max(counts) - 1) + 0.5 * 4) / cd.TIMER_SPEED + 45)
    dv = cd.DiveVideo(video, int(g.f0) + 2, int(g.f0) + span, None, region, scale=scale)
    for fr in r.get("dropped", []):
        dv.obs.pop(fr, None)
    frames = sorted(dv.obs)
    loss = cd.fast_loss(dv, counts, g, first, f0_offsets=(-3.0, -1.5, 0.0, 1.5, 3.0))
    o = np.argsort(loss)[:40]
    print("coarse top:", [(f"{int(first[i]):08X}", round(float(loss[i]))) for i in o[:10]], flush=True)
    out = []
    for i in o:
        s = int(first[i])
        flat = cd.flatten(cd.dive_params(s, counts))
        g2, l2 = cd.fit_geometry(dv, flat, g, frames, fast=True, anchor=g, state=s, counts=counts)
        out.append((min(l2, float(loss[i])), s, int(ks[i])))
    out.sort()
    ref = [(c["state"], c["loss"]) for c in r["candidates"][:3]]
    print("reader's own (unfiltered) top:", [(f"{s:08X}", round(l)) for s, l in ref])
    for l, s, k in out[:15]:
        print(f"  state {s:08X} layout {cd.layout_seed(s) & 0x7FFFFFFF:08X} k {k} loss {l:.0f}")
    json.dump([dict(state=s, layout=cd.layout_seed(s), k=k, loss=l) for l, s, k in out],
              open(os.path.splitext(scan)[0] + f"_rank{col}.json", "w"), indent=1)


if __name__ == "__main__":
    main()
