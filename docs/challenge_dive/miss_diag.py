"""Why a dive was misread: score the true state, its neighbours and the reader's pick directly.

    python docs/challenge_dive/miss_diag.py VIDEO --rows anch3_VIDEO.json [--ch 13 2] [--all] [--out F]

For each missed dive (or every dive with --all) the dive is set up exactly as the anchored reader
does (stage, crop, start frame), then these states are fitted one by one (geometry and start frame
free, as in the reader's final step): truth + k draws for k in -16..16, and the reader's pick.
Printed: loss at the reference geometry (best over start offsets -4..4 frames), loss after the fit,
and the fitted start frame. No window search, so it takes seconds per dive.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor

import numpy as np

sys.path.insert(0, os.path.dirname(__file__))
from anchored_eval import NEAR, anchored_dives, video_reg  # noqa: E402
from p2seeds import challenge_dive as cd, rng  # noqa: E402

M = 0x7FFFFFFF
OFFS = tuple(np.arange(-4.0, 4.01, 0.5))


def step(s, k):
    return (rng.next_seed(s, k) if k >= 0 else rng.prev_seed(s, -k)) & 0xFFFFFFFF


def diag(video, v, truth, end, pick, ks=range(-16, 17), threads=6):
    got = {}

    def hook(dv, counts, g, st):
        got.update(dv=dv, counts=counts, g=g)
        return dict(ok=True)

    cd.read_dive(video, v, window=(end, NEAR, 0), log=lambda s: None, reg=video_reg(video), hook=hook)
    dv, counts, g = got["dv"], got["counts"], got["g"]
    frames = sorted(dv.obs)
    cd._inputs(dv, 1, 1)
    states = {k: step(truth, k) for k in ks}
    if pick is not None and all((pick & M) != (s & M) for s in states.values()):
        states["pick"] = pick
    keys = list(states)
    arr = [states[k] for k in keys]
    fixed = cd.fast_loss(dv, counts, g, arr, f0_offsets=OFFS)

    def fit(x):
        flat = cd.flatten(cd.dive_params(x, counts))
        return cd.fit_geometry(dv, flat, g, frames, fast=True, anchor=g, state=x, counts=counts)

    with ThreadPoolExecutor(threads) as ex:
        fits = list(ex.map(fit, arr))
    out = []
    for k, s, lf, (gk, l) in zip(keys, arr, fixed, fits):
        out.append(dict(k=k, state=s, fixed=float(lf), fit=min(float(l), float(lf)), f0=gk.f0, sx=gk.sx, sy=gk.sy))
    import cv2
    n = int(cv2.VideoCapture(video).get(cv2.CAP_PROP_FRAME_COUNT))
    ce = cd.closing_end(video, max(0, int(v[0] - 45) - 30), min(n - 1, int(v[1] + 2) + 12))
    return dict(ce=ce, counts=counts, f0=g.f0, sx=g.sx, sy=g.sy, frames=len(frames), states=out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("--rows", required=True)
    ap.add_argument("--ch", type=int, nargs="*")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--out")
    a = ap.parse_args()
    rows = {r["visit"][0]: r for r in json.load(open(a.rows))}
    res = json.load(open(a.out)) if a.out and os.path.exists(a.out) else []
    done = {r["visit"][0] for r in res}
    for v, truth, end in anchored_dives(a.video, 250_000):
        r = rows.get(v[0])
        if r is None or v[0] in done or (a.ch and r["ch"] not in a.ch):
            continue
        if not a.all and r["grey_off"] in (0, 1, 2):
            continue
        d = diag(a.video, v, truth, end, r.get("final"))
        d.update(ch=r["ch"], visit=list(v), grey_off=r["grey_off"], truth=truth)
        by = sorted(d["states"], key=lambda x: x["fit"])
        t = next(x for x in d["states"] if x["k"] == 0)
        best = by[0]
        print(f"CH{r['ch']:<2} {str(d['counts']):<22} read off {r['grey_off']}  f0 {d['f0']:.1f} (closing {d['ce']})  truth fit {t['fit']:.0f} "
              f"(fixed {t['fixed']:.0f}, f0 {t['f0'] - d['f0']:+.1f})  best k={best['k']} fit {best['fit']:.0f} "
              f"(f0 {best['f0'] - d['f0']:+.1f})  rel {(t['fit'] - best['fit']) / best['fit']:+.3f}", flush=True)
        print("     " + "  ".join(f"{x['k']}:{x['fit']:.0f}/{x['f0'] - d['f0']:+.1f}" for x in by[:8]), flush=True)
        res.append(d)
        if a.out:
            json.dump(res, open(a.out, "w"), indent=1, default=float)


if __name__ == "__main__":
    main()
