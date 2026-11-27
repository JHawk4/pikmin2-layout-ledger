"""Does the stage-select dive agree with a layout seed? An independent check for layout-matched seeds.

Scores the dive-image loss (lower is better) of the dive state implied by the layout seed, at
999..1006 draws before it (the menu flash can add a draw), against random control states and
the dive reader's own top candidates. A layout seed whose dive state beats every control is
independent support; one in the middle of the controls means the dive says nothing (common on
noisy Wii captures).

    python docs/validator/dive_agree.py VIDEO DIVE_RESULT.json SEED [--controls 40]
"""
import json
import os
import random
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "p2seeds", "src"))
from p2seeds.challenge import dive as cd
from p2seeds import rng  # noqa: E402


def main():
    video, result, seed = sys.argv[1], sys.argv[2], int(sys.argv[3], 16)
    nctl = int(sys.argv[sys.argv.index("--controls") + 1]) if "--controls" in sys.argv else 40
    r = json.load(open(result))
    counts, region = r["counts"], tuple(r["region"])
    scale = float(np.sqrt(r["reg"]["sx"] * r["reg"]["sy"]))
    g = cd.geometry_from_vector(r["candidates"][0]["geometry"])
    span = int((0.1 * (max(counts) - 1) + 0.5 * 4) / cd.TIMER_SPEED + 45)
    dv = cd.DiveVideo(video, int(g.f0) + 2, int(g.f0) + span, None, region, scale=scale)
    for fr in r.get("dropped", []):
        dv.obs.pop(fr, None)
    frames = sorted(dv.obs)

    def loss(s):
        flat = cd.flatten(cd.dive_params(s, counts))
        coarse = float(cd.fast_loss(dv, counts, g, np.array([s], np.uint32), f0_offsets=(-3.0, -1.5, 0.0, 1.5, 3.0))[0])
        _, l2 = cd.fit_geometry(dv, flat, g, frames, fast=True, anchor=g, state=s, counts=counts)
        return min(l2, coarse)

    random.seed(seed)
    ctl = sorted(loss(random.getrandbits(32)) for _ in range(nctl))
    out = {"seed": f"{seed:08X}", "controls": ctl, "layout": {}, "reader": {}}
    for k in range(999, 1007):
        out["layout"][k] = loss(rng.prev_seed(seed, k))
    for c in r["candidates"][:3]:
        out["reader"][f"{c['state']:08X}"] = loss(c["state"])
    best = min(out["layout"].values())
    rank = sum(c < best for c in ctl)
    print(json.dumps(out))
    print(f"layout best {best:.0f} (offsets {out['layout']}), controls min {ctl[0]:.0f} median {ctl[len(ctl)//2]:.0f}; "
          f"{rank}/{nctl} controls beat it; reader {out['reader']}")


if __name__ == "__main__":
    main()
