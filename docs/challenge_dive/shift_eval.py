"""Can the one-Pikmin shift family (state -+ 4j draws) be resolved? Uses dives with a known truth.

    python docs/challenge_dive/shift_eval.py VIDEO [--back 2] [--colour-body] [--ch ...] [--out F]

For each dive: fit the truth's geometry, then score the truth's family with DetScorer.shift_family
(geometry fixed except f0). Also starts from a wrong member (truth - 4) refit on its own, to check
that resolution from a shifted read lands on the truth.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.dirname(__file__))
from det_eval import ROOT, dives, prepare  # noqa: E402
from p2seeds.challenge import dive_rgb as dr
from p2seeds import rng  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("videos", nargs="+")
    ap.add_argument("--parts", default="flower")
    ap.add_argument("--back", type=float, default=2.0)
    ap.add_argument("--colour-body", action="store_true")
    ap.add_argument("--late", type=float, default=1.0, help="weight of the landing phase (flight to the goal)")
    ap.add_argument("--ch", type=int, nargs="*")
    ap.add_argument("--out")
    a = ap.parse_args()
    sp = dr.load_sprites()
    rows = []
    for video in a.videos:
        for v, truth, r in dives(video):
            if a.ch and r["ch"] not in a.ch:
                continue
            t0 = time.time()
            ds, g = prepare(video, r, a.parts.split(","), sp, a.colour_body)
            ds.back_w, ds.late_w = a.back, a.late
            row = dict(video=os.path.basename(video), ch=r["ch"], counts=r["counts"], res={})
            for name, start in (("truth", truth), ("minus4", rng.prev_seed(truth, 4)), ("plus4", rng.next_seed(truth, 4))):
                picked, _, sc = ds.resolve_family(g, start)
                ok = (picked & 0x7FFFFFFF) == (truth & 0x7FFFFFFF)
                mem = list(sc)
                srt = sorted(sc.values())
                row["res"][name] = dict(ok=ok, offset=4 * (mem.index(picked) - 3), gap=srt[-1] - srt[-2],
                                        fam=[(float(v), int(m)) for m, v in sc.items()])
            print(f"CH{r['ch']:<3} " + " | ".join(f"{n}: {'OK' if x['ok'] else 'x '} pick {x['offset']:+d} gap {x['gap']:.1f}"
                                               for n, x in row["res"].items()) + f" ({time.time() - t0:.0f}s)", flush=True)
            rows.append(row)
            if a.out:
                json.dump(rows, open(a.out, "w"), indent=1)
    for n in ("truth", "minus4", "plus4"):
        print(n, sum(r["res"][n]["ok"] for r in rows), "/", len(rows))


if __name__ == "__main__":
    main()
