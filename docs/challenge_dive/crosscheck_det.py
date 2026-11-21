"""Cross-check the detection reader (read_det, flower templates) on a Challenge Mode All Levels run.

    python docs/challenge_dive/crosscheck_det.py VIDEO [--parts flower] [--top 60] [--span 3000000]

Same test as crosscheck_cmal.py: for each menu visit between two decoded results screens, the
truth is the preceding roll's state + 5 (from the results-screen digits) and the search window is
the `span` layout seeds before the following roll. The stage, crop region, dive start frame and
reference geometry come from read_dive(setup_only=True); the rest is read_det.read.
Results go to data/challenge/crosscheck/<video>_det_<parts>.json.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "p2seeds", "src"))
sys.path.insert(0, os.path.dirname(__file__))

from p2seeds import challenge_dive as cd, rng  # noqa: E402
import read_det  # noqa: E402


def st(x):
    return int(x, 16) if isinstance(x, str) else x


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("--parts", default="flower")
    ap.add_argument("--top", type=int, default=60)
    ap.add_argument("--span", type=int, default=3_000_000)
    ap.add_argument("--ch", type=int, nargs="*")
    a = ap.parse_args()
    name = os.path.basename(a.video)
    rolls = [r for r in json.load(open(os.path.join(ROOT, "data", "challenge", "results_rolls.json")))[name]["results"]
             if r.get("decoded")]
    visits = [tuple(v) for v in json.load(open(os.path.join(ROOT, "data", "challenge", f"visits_{name}.json")))]
    out_dir = os.path.join(ROOT, "data", "challenge", "crosscheck")
    known = {tuple(r["visit"]): r.get("ch") for r in json.load(open(os.path.join(out_dir, name + ".json")))}
    out_path = os.path.join(out_dir, f"{name}_det_{a.parts.replace(',', '+')}.json")
    out = json.load(open(out_path)) if os.path.exists(out_path) else []
    done = {tuple(r["visit"]) for r in out}
    pairs = []
    for prev, nxt in zip(rolls, rolls[1:]):
        vs = [v for v in visits if prev["last_frame"] < v[0] < nxt["first_frame"]]
        if len(vs) == 1 and tuple(vs[0]) in known:      # one visit only: the truth is valid
            pairs.append((prev, nxt, vs[0]))
    if a.ch:
        pairs = [x for x in pairs if known.get(tuple(x[2])) in a.ch]
    print(f"{name}: {len(pairs)} stages", flush=True)
    for prev, nxt, v in pairs:
        if tuple(v) in done:
            continue
        truth = rng.next_seed(st(prev["state_after_last_draw"]), 5) & 0xFFFFFFFF
        end = st(nxt.get("first_roll_state") or nxt["anchor_state"])
        t = time.time()
        log = lambda s: print("   ", s, flush=True)  # noqa: E731
        try:
            r = cd.read_dive(a.video, v, window=(end, a.span), setup_only=True, log=log)
            d = read_det.read(a.video, r, a.parts.split(","), a.top, truth, log=log)
            best = d["rows"][0]["state"]
            rec = dict(visit=list(v), ch=r["ch"], counts=r["counts"], truth=truth, best=best,
                       correct=(best & 0x7FFFFFFF) == (truth & 0x7FFFFFFF), truth_rank=d["truth_rank"],
                       first_pass_rank=d["first_pass_rank"], margin=d["margin"],
                       scores=[x["score"] for x in d["rows"][:3]], seconds=time.time() - t)
        except Exception as e:
            rec = dict(visit=list(v), ch=known.get(tuple(v)), truth=truth, correct=False, note=repr(e),
                       seconds=time.time() - t)
        print(json.dumps(rec, default=float), flush=True)
        out.append(rec)
        json.dump(out, open(out_path, "w"), indent=1, default=float)


if __name__ == "__main__":
    main()
