"""Compare letter fits between runs: fit quality, letters measured, the starting-speed
distribution and the seed confidences. Physics that match GameCube should give the same
residuals and speeds spread evenly over [0, 5).

    python docs/switch/summarize.py LABEL=FITS.json [LABEL=FITS.json ...]
"""

import json
import sys
from collections import Counter

import numpy as np


def main(args):
    print("| run | entries | clean fits | median rms px | letters/entry | speeds min-max | "
          "share per fifth of [0,5) | KS vs uniform | high/medium/low/none |")
    print("|---|---|---|---|---|---|---|---|---|")
    for a in args:
        label, path = a.split("=", 1)
        rows = json.load(open(path, encoding="utf-8"))
        fits = [r["fit"] for r in rows if r["fit"]]
        clean = [f for f in fits if f["rms_px"] < 0.35]
        nm = [sum(x is not None for x in f["v"]) for f in clean]
        v = np.array([x for f in clean for x in f["v"] if x is not None])
        v = np.sort(v[(v > -0.5) & (v < 5.5)])
        ks = float(np.max(np.abs(np.arange(1, len(v) + 1) / len(v) - np.clip(v / 5, 0, 1)))) if len(v) else float("nan")
        fifths = np.histogram(v, bins=[-1, 1, 2, 3, 4, 6])[0] / max(1, len(v))
        c = Counter(r["confidence"] for r in rows)
        print(f"| {label} | {len(rows)} | {len(clean)} | {np.median([f['rms_px'] for f in clean]):.3f} | "
              f"{np.median(nm):.0f} | {v.min():.2f}-{v.max():.2f} | {' '.join(f'{x:.2f}' for x in fifths)} | "
              f"{ks:.3f} (n={len(v)}) | {c['high']}/{c['medium']}/{c['low']}/{c['none']} |")


if __name__ == "__main__":
    main(sys.argv[1:])
