"""Cross-check the dive reader on a Challenge Mode All Levels run.

    python docs/challenge_dive/crosscheck_cmal.py VIDEO [--every N] [--span 3000000] [--max K]

For each menu visit that lies between two decoded results screens:
  truth  = the preceding roll's state after its last draw + 5   (the dive's first draw)
  search = the dive reader, using only the FOLLOWING roll: candidates are the dive starts whose
           floor-1 layout seed lies within `span` draws before that roll's first state.
The two are independent; agreement means the dive alone (plus "the stage ended within `span`
draws") identified the seed. Results go to data/challenge/crosscheck/<video>.json.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "p2seeds", "src"))

from p2seeds import challenge_dive as cd, rng  # noqa: E402


def st(x):
    return int(x, 16) if isinstance(x, str) else x


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("--every", type=int, default=1)
    ap.add_argument("--span", type=int, default=3_000_000)
    ap.add_argument("--max", type=int, default=99)
    ap.add_argument("--ch", type=int, nargs="*", help="only these stages (by the landing stage of earlier results)")
    ap.add_argument("--tag", default="", help="suffix for the output file")
    a = ap.parse_args()
    name = os.path.basename(a.video)
    rolls = json.load(open(os.path.join(ROOT, "data", "challenge", "results_rolls.json")))[name]["results"]
    rolls = [r for r in rolls if r.get("decoded")]
    vis_path = os.path.join(ROOT, "data", "challenge", f"visits_{name}.json")
    if os.path.exists(vis_path):
        visits = [tuple(v) for v in json.load(open(vis_path))]
    else:
        visits = cd.menu_visits(a.video)
        json.dump(visits, open(vis_path, "w"))
    out_dir = os.path.join(ROOT, "data", "challenge", "crosscheck")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, name + a.tag + ".json")
    out = json.load(open(out_path)) if os.path.exists(out_path) else []
    done = {tuple(r["visit"]) for r in out}
    pairs = []
    for prev, nxt in zip(rolls, rolls[1:]):
        vs = [v for v in visits if prev["last_frame"] < v[0] < nxt["first_frame"]]
        if vs:
            pairs.append((prev, nxt, vs[-1], len(vs)))  # the last visit before the next stage's results
    pairs = pairs[::a.every][:a.max]
    if a.ch:                                   # stage of each visit from an earlier untagged run
        base = os.path.join(out_dir, name + ".json")
        known = {tuple(r["visit"]): r.get("ch") for r in json.load(open(base))} if os.path.exists(base) else {}
        pairs = [x for x in pairs if known.get(tuple(x[2])) in a.ch]
    print(f"{name}: {len(pairs)} stages to check", flush=True)
    for prev, nxt, v, n_vis in pairs:
        if tuple(v) in done:
            continue
        truth = rng.next_seed(st(prev["state_after_last_draw"]), 5) & 0xFFFFFFFF
        end = st(nxt.get("first_roll_state") or nxt["anchor_state"])
        t = time.time()
        try:
            r = cd.read_dive(a.video, v, window=(end, a.span), probe=[truth], log=lambda s: print(s, flush=True))
        except Exception as e:
            r = dict(ok=False, note=repr(e))
        best = r["candidates"][0]["state"] if r.get("ok") and r.get("candidates") else None
        rank = None
        if r.get("ok"):
            for k, c in enumerate(r.get("top", [])):
                if (c["state"] & 0x7FFFFFFF) == (truth & 0x7FFFFFFF):
                    rank = k
                    break
        rec = dict(visit=list(v), ch=r.get("ch"), counts=r.get("counts"), truth=truth, best=best,
                   correct=best is not None and (best & 0x7FFFFFFF) == (truth & 0x7FFFFFFF), truth_rank=rank,
                   margin=r.get("margin"), losses=[c["loss"] for c in r.get("candidates", [])[:3]],
                   in_window=rng.distance(rng.next_seed(truth, 999), end, limit=a.span) is not None,
                   seconds=time.time() - t, note=r.get("note"), probes=r.get("probes"),
                   truth_valid=n_vis == 1)   # another visit in between may have dived too
        print(json.dumps(rec), flush=True)
        out.append(rec)
        json.dump(out, open(out_path, "w"), indent=1)


if __name__ == "__main__":
    main()
