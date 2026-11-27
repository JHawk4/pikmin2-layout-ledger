"""Read every stage-select dive in a Challenge Mode video and recover each floor-1 layout seed.

    python docs/challenge_dive/read_dives.py VIDEO [--out OUT.json] [--visits a-b,c-d] [--stage N]

Writes one record per menu visit: the stage, the best dive states with their image loss, the
floor-1 layout seed of the best, and the margin to the runner-up (relative loss gap).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "p2seeds", "src"))

from p2seeds.challenge import dive as cd  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("--out")
    ap.add_argument("--visits", help="comma-separated first-last frame ranges (skip detection)")
    ap.add_argument("--stage", type=int, help="challenge stage number (skip landing detection)")
    ap.add_argument("--keep", type=int, default=4_000_000)
    a = ap.parse_args()
    t = time.time()
    if a.visits:
        visits = [tuple(int(x) for x in v.split("-")) for v in a.visits.split(",")]
    else:
        visits = cd.menu_visits(a.video)
    print(f"{len(visits)} menu visits ({time.time() - t:.0f}s): {visits}", flush=True)
    out = []
    for v in visits:
        try:
            r = cd.read_dive(a.video, v, ch=a.stage, keep=a.keep, log=lambda s: print(s, flush=True))
        except Exception as e:  # keep going on one bad visit
            r = dict(ok=False, note=repr(e))
        r["visit"] = list(v)
        out.append(r)
        if a.out:
            with open(a.out, "w") as f:
                json.dump(out, f, indent=1, default=lambda x: float(x) if hasattr(x, "__float__") else str(x))
    print(f"done in {time.time() - t:.0f}s")


if __name__ == "__main__":
    main()
