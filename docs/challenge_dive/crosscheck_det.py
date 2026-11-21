"""Cross-check the detection reader (read_det, flower templates) on a Challenge Mode All Levels run.

    python docs/challenge_dive/crosscheck_det.py VIDEO [--parts flower] [--top 60] [--span 3000000]

Same test as crosscheck_cmal.py: for each menu visit between two decoded results screens, the
truth is the preceding roll's state + 5 (from the results-screen digits) and the search window is
the `span` layout seeds before the following roll. The stage, crop region, dive start frame and
geometry come from the full grey reader (read_dive, cached in crosscheck/dives/), whose fitted
geometry is the detection's starting point; the grey reader's own verdict is recorded alongside.
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
    ap.add_argument("--setup-only", action="store_true",
                    help="start from the reference geometry instead of the grey reader's fit (fast, weaker)")
    ap.add_argument("--grey-shortlist", type=int, default=0,
                    help="refit and rank only the grey reader's candidates plus its N best coarse states")
    ap.add_argument("--blind", action="store_true", help="do not add the truth to the states refit")
    a = ap.parse_args()
    name = os.path.basename(a.video)
    rolls = [r for r in json.load(open(os.path.join(ROOT, "data", "challenge", "results_rolls.json")))[name]["results"]
             if r.get("decoded")]
    visits = [tuple(v) for v in json.load(open(os.path.join(ROOT, "data", "challenge", f"visits_{name}.json")))]
    out_dir = os.path.join(ROOT, "data", "challenge", "crosscheck")
    known = {tuple(r["visit"]): r.get("ch") for r in json.load(open(os.path.join(out_dir, name + ".json")))}
    tag = (f"_grey{a.grey_shortlist}" if a.grey_shortlist else "") + ("_blind" if a.blind else "")
    out_path = os.path.join(out_dir, f"{name}_det_{a.parts.replace(',', '+')}{tag}.json")
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
            cache = os.path.join(out_dir, "dives", f"{name}_{v[0]}{'_setup' if a.setup_only else ''}.json")
            if os.path.exists(cache):
                r = json.load(open(cache))
            else:
                r = cd.read_dive(a.video, v, window=(end, a.span), setup_only=a.setup_only, probe=[truth], log=log)
                r["window"] = [end, a.span]
                os.makedirs(os.path.dirname(cache), exist_ok=True)
                json.dump(r, open(cache, "w"), default=float)
            grey = r.get("candidates", [{}])[0].get("state")
            sl = None
            if a.grey_shortlist:
                sl = [c["state"] for c in r.get("candidates", [])] + [c["state"] for c in r.get("top", [])[:a.grey_shortlist]]
            d = read_det.read(a.video, r, a.parts.split(","), a.top, truth, log=log, shortlist=sl,
                              inject_truth=not a.blind)
            best = d["rows"][0]["state"]
            rec = dict(visit=list(v), ch=r["ch"], counts=r["counts"], truth=truth, best=best,
                       correct=(best & 0x7FFFFFFF) == (truth & 0x7FFFFFFF), truth_rank=d["truth_rank"],
                       first_pass_rank=d["first_pass_rank"], margin=d["margin"],
                       scores=[x["score"] for x in d["rows"][:3]], seconds=time.time() - t,
                       grey_best=grey, grey_correct=None if grey is None else (grey & 0x7FFFFFFF) == (truth & 0x7FFFFFFF),
                       grey_margin=r.get("margin"))
        except Exception as e:
            rec = dict(visit=list(v), ch=known.get(tuple(v)), truth=truth, correct=False, note=repr(e),
                       seconds=time.time() - t)
        print(json.dumps(rec, default=float), flush=True)
        out.append(rec)
        json.dump(out, open(out_path, "w"), indent=1, default=float)


if __name__ == "__main__":
    main()
