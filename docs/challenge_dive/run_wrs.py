"""Read the floor-1 seed of each Pikmin 2 challenge-mode WR video's dive.

    python docs/challenge_dive/run_wrs.py [CH ...]

Inputs (data/challenge/wr/, gitignored): wr_list.json (from the pikmin-wrs boards), the videos
wr_<CH>_r<rule>.*, and visits.json (menu visits with registration score and landing stage).
Writes data/challenge/wr/dives/wr_<CH>.json per stage.
"""
from __future__ import annotations

import glob
import json
import os
import sys
import time

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "p2seeds", "src"))

from p2seeds import challenge_dive as cd  # noqa: E402

WR = os.path.join(ROOT, "data", "challenge", "wr")


def pick_visit(info, ch):
    good = [v for v in info["visits"] if v["reg"] >= 0.45]
    for v in good:
        if v["landing"] == ch:
            return v
    early = [v for v in good if v["visit"][0] < 900]
    return early[-1] if early else None


def main():
    visits = json.load(open(os.path.join(WR, "visits.json")))
    want = [int(a) for a in sys.argv[1:]]
    os.makedirs(os.path.join(WR, "dives"), exist_ok=True)
    for name, info in sorted(visits.items()):
        ch = info["ch"]
        if want and ch not in want:
            continue
        out = os.path.join(WR, "dives", f"wr_{ch:02d}.json")
        if os.path.exists(out):
            continue
        v = pick_visit(info, ch)
        if v is None:
            json.dump(dict(ok=False, note="no stage-select dive in the video", ch=ch, video=name), open(out, "w"))
            print(name, "no dive", flush=True)
            continue
        counts = cd.stage_counts(ch)
        if sum(counts) == 0:
            json.dump(dict(ok=False, note="stage has no Pikmin in the dive colours", ch=ch, video=name), open(out, "w"))
            print(name, "no dive Pikmin", flush=True)
            continue
        t = time.time()
        try:
            r = cd.read_dive(os.path.join(WR, name), tuple(v["visit"]), ch=ch, log=lambda s: print(s, flush=True))
        except Exception as e:
            r = dict(ok=False, note=repr(e))
        r.update(video=name, visit=v["visit"], seconds=time.time() - t)
        json.dump(r, open(out, "w"), indent=1, default=lambda x: float(x) if hasattr(x, "__float__") else str(x))
        print(name, "done", r.get("candidates", [{}])[0] if r.get("ok") else r.get("note"), flush=True)


if __name__ == "__main__":
    main()
