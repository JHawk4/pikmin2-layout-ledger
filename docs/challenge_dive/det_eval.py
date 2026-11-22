"""Compare detection-scorer variants on dives with a known truth (fast: grey reads are cached).

    python docs/challenge_dive/det_eval.py VIDEO [VIDEO ...] [--short 60] [--variants "0,3;1,3;2,3"]

For every truth-valid visit of each video that has a cached grey read
(data/challenge/crosscheck/dives/<video>_<first>.json, made by crosscheck_det.py), the states
refit are: the grey reader's final candidates, its `--short` best coarse states, and the truth.
Each variant (back_w, sigma[, det_thr]) refits them all from the same start geometry, then the best
10 again from the best geometry, and reports the truth's rank and the margin
(best - second) / (best - median of a window sample).

A variant ranks the truth 0 = it would read the dive correctly from this shortlist. `in` says
whether the truth is in the grey shortlist at all (if not, a blind read cannot get it right).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

import numpy as np

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "p2seeds", "src"))
from p2seeds import challenge_dive as cd, dive_detect as dd, dive_rgb as dr, rng  # noqa: E402


def st(x):
    return int(x, 16) if isinstance(x, str) else x


def dives(video):
    name = os.path.basename(video)
    rolls = [r for r in json.load(open(os.path.join(ROOT, "data", "challenge", "results_rolls.json")))[name]["results"]
             if r.get("decoded")]
    visits = [tuple(v) for v in json.load(open(os.path.join(ROOT, "data", "challenge", f"visits_{name}.json")))]
    for prev, nxt in zip(rolls, rolls[1:]):
        vs = [v for v in visits if prev["last_frame"] < v[0] < nxt["first_frame"]]
        if len(vs) != 1:
            continue
        cache = os.path.join(ROOT, "data", "challenge", "crosscheck", "dives", f"{name}_{vs[0][0]}.json")
        if os.path.exists(cache):
            yield vs[0], rng.next_seed(st(prev["state_after_last_draw"]), 5) & 0xFFFFFFFF, json.load(open(cache))


def prepare(video, r, parts, sp, colour_body=False):
    counts, region = r["counts"], tuple(r["region"])
    g = dr.shifted_geometry(cd.geometry_from_vector(r["candidates"][0]["geometry"]), sp)
    span = int((0.1 * (max(counts) - 1) + 0.5 * 4) / cd.TIMER_SPEED + 45)
    rd = dr.RGBDive(video, int(g.f0) - 4, int(g.f0) + span, region, drop=r.get("dropped", []), sp=sp)
    ds = dd.DetScorer(rd, counts, sp, g.sx, g.sy, parts=parts, colour_body=colour_body)
    du, dv = ds.origin_correction(g)
    g = g.copy(origins={c: (u + du, v + dv) for c, (u, v) in g.origins.items()},
               goal=(g.goal[0] + du, g.goal[1] + dv), v100=g.v100 + dv)
    return ds, g


def evaluate(ds, g, states, truth, sample):
    fits = sorted(((ds.fit(g, int(s))[::-1]) + (int(s),) for s in states), key=lambda x: -x[0])
    gb = fits[0][1]
    again = []
    for v, gk, s in fits[:10]:
        g2, v2 = ds.fit(gb, s)
        again.append((max(v, v2), s))
    rank = sorted(again, reverse=True) + [(v, s) for v, gk, s in fits[10:]]
    med = float(np.median(ds.score(gb, sample)))
    tr = next((k for k, (v, s) in enumerate(rank) if (s & 0x7FFFFFFF) == (truth & 0x7FFFFFFF)), None)
    margin = (rank[0][0] - rank[1][0]) / max(1e-6, rank[0][0] - med)
    sb, _, fam = ds.resolve_shift(gb, rank[0][1])
    return tr, margin, rank[0][1], sb, fam


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("videos", nargs="+")
    ap.add_argument("--short", type=int, default=60)
    ap.add_argument("--parts", default="flower")
    ap.add_argument("--variants", default="0,3;1,3;2,3")
    ap.add_argument("--out")
    ap.add_argument("--colour-body", action="store_true", help="body colour evidence for red/yellow/blue")
    ap.add_argument("--ch", type=int, nargs="*", help="only these stages")
    ap.add_argument("--late", type=float, default=1.0, help="weight of the landing phase")
    a = ap.parse_args()
    variants = [tuple(float(x) for x in v.split(",")) for v in a.variants.split(";")]
    sp = dr.load_sprites()
    rows = []
    for video in a.videos:
        for v, truth, r in dives(video):
            if a.ch and r["ch"] not in a.ch:
                continue
            t0 = time.time()
            ds, g = prepare(video, r, a.parts.split(","), sp, a.colour_body)
            ds.late_w = a.late
            grey = [c["state"] for c in r.get("candidates", [])] + [c["state"] for c in r.get("top", [])[:a.short]]
            inn = any((s & 0x7FFFFFFF) == (truth & 0x7FFFFFFF) for s in grey)
            uniq = {}
            for x in grey + [truth]:                 # bit 31 does not change a dive: one of each pair
                uniq.setdefault(x & 0x7FFFFFFF, x)
            states = np.array(list(uniq.values()), np.uint64)
            end, n = r["window"]
            sample = cd.window_states(end, n)[:: max(1, n // 50_000)]
            gc = (r["candidates"][0]["state"] & 0x7FFFFFFF) == (truth & 0x7FFFFFFF)
            row = dict(video=os.path.basename(video), visit=list(v), ch=r["ch"], counts=r["counts"], truth_in=inn,
                       grey_ok=gc, grey_margin=r.get("margin"), res={})
            line = f"{row['video'][:6]} CH{r['ch']:<3} in={'Y' if inn else 'n'} grey {'OK ' if gc else 'bad'} {r.get('margin') or 0:.3f} |"
            for var in variants:
                ds.back_w, ds.sigma = var[0], var[1]
                if len(var) > 2:
                    ds.set_detections(var[2])
                tr, m, best, sb, fam = evaluate(ds, g, states, truth, sample)
                sok = (sb & 0x7FFFFFFF) == (truth & 0x7FFFFFFF)
                row["res"][str(var)] = dict(rank=tr, margin=m, best=best, shift_best=sb, shift_ok=sok, family=fam)
                line += f" {var}: rank {tr} m {m:.3f} shift {'OK' if sok else 'x'} |"
            print(line + f" ({time.time() - t0:.0f}s)", flush=True)
            rows.append(row)
            if a.out:
                json.dump(rows, open(a.out, "w"), indent=1, default=float)
    for var in variants:
        k = str(var)
        ok = sum(1 for r in rows if r["res"][k]["rank"] == 0 and r["truth_in"])
        conf = [r for r in rows if r["res"][k]["margin"] >= 0.08]
        print(f"{var}: correct blind {ok}/{len(rows)}; margin>=8%: {sum(1 for r in conf if r['res'][k]['rank'] == 0 and r['truth_in'])}/{len(conf)} correct")
        sok = sum(1 for r in rows if r["res"][k]["shift_ok"] and r["truth_in"])
        print(f"{var}: after shift resolution, correct blind {sok}/{len(rows)}")


if __name__ == "__main__":
    main()
