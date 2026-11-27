"""Fit one entry screen's letter fall without the seed search, and check the physics.

    python docs/switch/probe.py VIDEO X0,Y0,X1,Y1 FIRST LAST

FIRST/LAST: frames around the settled title (as in an Event). Prints the global fit (scale s in
px per game unit against the GC prediction H/480, residual rms) and, per letter, its fitted
start speed and a free parabola fitted to its own track (acceleration in px/frame^2, which on
GameCube is s * 1 unit/frame^2).
"""

import sys

import numpy as np

from p2seeds.story import analyze
from p2seeds.story.events import Event
from p2seeds.feed import Feed
from p2seeds.story.fit import free_fall
from p2seeds.video import Video

FITS = []
_orig_fit = analyze.fit


def _fit(tracks, *a, **kw):
    f = _orig_fit(tracks, *a, **kw)
    FITS.append((f, tracks))
    return f


analyze.fit = _fit
analyze._search = lambda f, search_kw=None, retries=True: ([], "none")
analyze._fit_with_step = lambda *a, **k: []


def main():
    video, box, first, last = sys.argv[1], sys.argv[2], int(sys.argv[3]), int(sys.argv[4])
    feed = Feed(*map(int, box.split(",")))
    v = Video(video)
    for r in analyze.analyze_event(v, feed, Event(first, last, 1)):
        print(f"{r.cave} score {r.cave_score:.2f}")
    if not FITS:
        print("no fit")
        return
    f, tracks = min(FITS[:2], key=lambda ft: ft[0].rms_px)
    H = feed.height
    print(f"s = {f.s:.4f} px/unit (GC prediction H/480 = {H / 480:.4f}), rms {f.rms_px:.3f} px, F0 {f.F0:.2f}")
    acc = []
    for t in tracks:
        fr, y = free_fall(t)
        if len(fr) >= 5:
            c = np.polyfit(fr, y, 2)
            acc.append(2 * c[0])
    print(f"free-parabola acceleration per letter: median {np.median(acc):.4f} px/frame^2 "
          f"(= {np.median(acc) / f.s:.3f} units/frame^2; GC is 1)")
    print("v:", " ".join("  -  " if not np.isfinite(x) else f"{x:5.2f}" for x in f.v))
    print("n:", " ".join(f"{x:5d}" for x in f.n_points))
    if len(sys.argv) > 5:      # append to a fits.json-style file for variants.py
        import json
        from pathlib import Path
        p = Path(sys.argv[5])
        rows = json.loads(p.read_text()) if p.exists() else []
        fl = lambda a: [None if not np.isfinite(x) else float(x) for x in a]
        rows.append({"frame": first, "cave": r.cave_id, "fit": {"v": fl(f.v), "sigma": fl(f.sigma), "rms_px": f.rms_px},
                     "s": f.s, "acc_units": float(np.median(acc) / f.s), "H": H})
        p.write_text(json.dumps(rows))


if __name__ == "__main__":
    main()
