"""Anchored dive read for a score-record video: the grey dive reader searched only over the states
whose floor-1 layout seed lies within SPAN draws before the stage's results roll.

    python docs/ch_hunt/wr_anchored.py CH SPAN [--video V] [--roll ROLLS.json] [--visit A,B] [--out F]

Defaults read the WR inputs of the challenge-mode-seeds worktree (data/challenge/wr: visits.json,
rolls/wr_<CH>_r<rule>.json, the videos). Writes the reader's full result (top candidates with their
floor-1 layout seeds) as JSON. Use it to get a shortlist, then check each candidate's layout.
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import sys
import time

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "p2seeds", "src"))
from p2seeds.challenge import dive as cd  # noqa: E402

WR = os.environ.get("WR_DATA", r"C:\Users\Jordan\Desktop\Claude\p2-vod-seeds\.claude\worktrees\judge2-net-timesave-304bfd\data\challenge\wr")


def below_normal():
    """The CPU is shared with other hunt sessions: run at below-normal priority on Windows."""
    if os.name == "nt":
        import ctypes
        ctypes.windll.kernel32.SetPriorityClass(ctypes.windll.kernel32.GetCurrentProcess(), 0x4000)


def main():
    below_normal()
    ap = argparse.ArgumentParser()
    ap.add_argument("ch", type=int)
    ap.add_argument("span", type=int)
    ap.add_argument("--video"), ap.add_argument("--roll"), ap.add_argument("--visit"), ap.add_argument("--out")
    ap.add_argument("--roll-index", type=int, default=-1, help="which decoded results screen is the anchor")
    a = ap.parse_args()
    video = a.video or glob.glob(os.path.join(WR, f"wr_{a.ch:02d}_r2?.*"))[0]
    name = os.path.basename(video)
    if a.visit:
        visit = tuple(int(x) for x in a.visit.split(","))
    else:
        vis = json.load(open(os.path.join(WR, "visits.json")))[name]["visits"]
        visit = tuple(next(v for v in vis if v["landing"] == a.ch and v["reg"] >= 0.45)["visit"])
    rollf = a.roll or os.path.join(WR, "rolls", os.path.splitext(name)[0] + ".json")
    rolls = [r for r in json.load(open(rollf))["results"] if r.get("decoded") and r["first_frame"] > visit[1]]
    r = rolls[a.roll_index if a.roll_index >= 0 else 0]
    end = int(r.get("first_roll_state") or r["anchor_state"], 16)
    print(f"CH{a.ch} {name} visit {visit} roll frame {r['first_frame']} end {end:08X} span {a.span}", flush=True)
    t = time.time()
    res = cd.read_dive(video, visit, ch=a.ch, window=(end, a.span, 0), log=lambda s: print(s, flush=True),
                       skip_if_clear=False, prune_coarse=(4, 4), rank_mid=500)
    res["seconds"] = time.time() - t
    res["anchor"] = dict(frame=r["first_frame"], end=f"{end:08X}")
    out = a.out or os.path.join(ROOT, "data", "challenge", "hunt3", f"dive_ch{a.ch}.json")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    json.dump(res, open(out, "w"), default=float, indent=1)
    for c in res.get("candidates", [])[:10]:
        print(f"  state {c['state'] & 0xFFFFFFFF:08X} loss {c['loss']:.1f} layout {c['layout_seed'] & 0x7FFFFFFF:08X}")
    print("margin", res.get("margin"), "seconds", round(res["seconds"]))


if __name__ == "__main__":
    main()
