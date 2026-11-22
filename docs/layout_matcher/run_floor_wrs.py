"""Run floormatch2 on every WR with picked comedown frames (obs/comedown_frames.json), in that
order, skipping ones already done. Window: k in [0, min(60 x frames dive->roll, 1.5M)).

    python docs/layout_matcher/run_floor_wrs.py [CH ...]
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import floormatch2 as fm  # noqa: E402
import lm  # noqa: E402
from inventory import WR  # noqa: E402
from wr_comedown import INV, crop_for  # noqa: E402

OUT = os.path.join(lm.ROOT, "data", "lm", "fm")


def main():
    frames = json.load(open(os.path.join(os.path.dirname(__file__), "obs", "comedown_frames.json")))
    inv = {e["ch"]: e for e in json.load(open(INV))}
    want = [int(a) for a in sys.argv[1:]] or [int(k) for k in frames]
    os.makedirs(OUT, exist_ok=True)
    for ch in want:
        e = inv[ch]
        prefix = os.path.join(OUT, f"wr{ch:02d}")
        if os.path.exists(prefix + ".json") or not e["roll_state"]:
            continue
        hi = min(int(60 * (e["frames"] or 25000)), 1_500_000)
        video = os.path.join(WR, e["video"])
        print(f"== CH{ch} k 0..{hi}", flush=True)
        fm.run(video, crop_for(video), frames[str(ch)], f"CH{ch}-1", int(e["roll_state"], 16), 0, hi, prefix)


if __name__ == "__main__":
    main()
