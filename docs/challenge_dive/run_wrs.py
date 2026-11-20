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
SPAN = 3_000_000           # floor-1 seed lies at most this many draws before the stage's results roll


def _ok_mismatch(r):
    """Flagged rolls are still usable when misreads are a small share of the digits."""
    m, n = r.get("digits_mismatched", 0), r.get("digits_matched", 1)
    return m <= 0.1 * n


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
        window = None
        roll_path = os.path.join(WR, "rolls", os.path.splitext(name)[0] + ".json")
        roll = None
        if os.path.exists(roll_path):
            data = json.load(open(roll_path))
            data = data["results"] if isinstance(data, dict) else data
            rolls = [r for r in data if r.get("decoded") and r["first_frame"] > v["visit"][1] and _ok_mismatch(r)]
            if rolls:
                roll = rolls[0]
                st = roll.get("first_roll_state") or roll["anchor_state"]
                end = int(st, 16) if isinstance(st, str) else st
                visible = sum(min(k, 50) for k in counts)
                if visible <= 12:
                    # few Pikmin: also use how many draws this stage takes per frame (CMAL runs)
                    skip, span = cd.draw_window(ch, roll["first_frame"] - v["visit"][1])
                    window = (end, span, skip)
                else:
                    window = (end, SPAN)
        t = time.time()
        try:
            r = cd.read_dive(os.path.join(WR, name), tuple(v["visit"]), ch=ch, window=window,
                             keep=4_000_000, log=lambda s: print(s, flush=True))
        except Exception as e:
            r = dict(ok=False, note=repr(e))
        r.update(video=name, visit=v["visit"], seconds=time.time() - t, window=window,
                 roll=dict(first_frame=roll["first_frame"], state=roll.get("first_roll_state") or roll["anchor_state"],
                           end=roll.get("state_after_last_draw")) if roll else None)
        json.dump(r, open(out, "w"), indent=1, default=lambda x: float(x) if hasattr(x, "__float__") else str(x))
        print(name, "done", r.get("candidates", [{}])[0] if r.get("ok") else r.get("note"), flush=True)


if __name__ == "__main__":
    main()
