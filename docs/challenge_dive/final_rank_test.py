"""Test of a fairer final ranking for the anchored dive reader, on cached reads.

    python docs/challenge_dive/final_rank_test.py VIDEO --rows anch3_VIDEO.json --out F [--misses] [--ch ...]

The reader's last step fits the geometry to each of its top candidates separately and compares the
fitted losses. Those fits do not converge to the same optimum from different starts (5-10% apart),
so the comparison is partly luck, and each extra fit of a one-Pikmin shift is another chance to win.
Here every candidate is fitted from the reference geometry, then every candidate is scored under
every fitted geometry (start frame +-2 Pikmin delays) and keeps its best: any geometry found for
one candidate is available to all.

Candidates: the cached reads' leaders (near, far and whole-window reads) and their one-Pikmin
shifts. The truth and its neighbours are scored too but reported separately ("with truth").
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor

import numpy as np

sys.path.insert(0, os.path.dirname(__file__))
from anchored_eval import NEAR, ROOT, anchored_dives, video_reg  # noqa: E402
from p2seeds import challenge_dive as cd, rng  # noqa: E402

M = 0x7FFFFFFF
STEP = 0.1 / cd.TIMER_SPEED          # frames between two Pikmin of one colour


def step(s, k):
    return (rng.next_seed(s, k) if k >= 0 else rng.prev_seed(s, -k)) & 0xFFFFFFFF


def cached_candidates(name, first, top_n=6):
    """(candidates, pool): the cached reads' refined candidates, top few and the leaders' one-Pikmin
    shifts; and everything else the reads kept (their top 200 each)."""
    out, leaders, pool = [], [], []
    d = os.path.join(ROOT, "data", "challenge", "crosscheck", "dives")
    for tag in ("hn110k", "hr110k_250k", "hw250k"):
        p = os.path.join(d, f"{name}_{first}_{tag}.json")
        if not os.path.exists(p):
            continue
        c = json.load(open(p))
        if not c.get("candidates"):
            continue
        leaders.append(c["candidates"][0]["state"])
        out += [x["state"] for x in c["candidates"]] + [x["state"] for x in c.get("top", [])[:top_n]]
        pool += [x["state"] for x in c.get("top", [])]
    for s in leaders:
        out += [step(s, 4 * j) for j in (-3, -2, -1, 1, 2, 3)]
    seen, uniq = set(), []
    for s in out:
        if s & M not in seen:
            seen.add(s & M)
            uniq.append(int(s) & 0xFFFFFFFF)
    return uniq, [int(s) & 0xFFFFFFFF for s in pool]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("--rows", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--misses", action="store_true")
    ap.add_argument("--ch", type=int, nargs="*")
    ap.add_argument("--threads", type=int, default=6)
    a = ap.parse_args()
    name = os.path.basename(a.video)
    rows = {r["visit"][0]: r for r in json.load(open(a.rows))}
    res = json.load(open(a.out)) if os.path.exists(a.out) else []
    done = {r["visit"][0] for r in res}
    for v, truth, end in anchored_dives(a.video, 250_000):
        r = rows.get(v[0])
        if r is None or v[0] in done or (a.ch and r["ch"] not in a.ch):
            continue
        if a.misses and r["grey_off"] in (0, 1, 2):
            continue
        t0 = time.time()
        got = {}
        cd.read_dive(a.video, v, window=(end, NEAR, 0), log=lambda s: None, reg=video_reg(a.video),
                     hook=lambda dv, counts, g, st: got.update(dv=dv, counts=counts, g=g) or dict(ok=True))
        dv, counts, g = got["dv"], got["counts"], got["g"]
        cands, pool = cached_candidates(name, v[0])
        S, loss, G, gi = cd.cross_rank(dv, counts, g, cands, pool, a.threads, add=150 if sum(counts) <= 15 else 8)
        off = lambda x: next((k for k in range(-16, 17) if (step(truth, k) & M) == (x & M)), None)  # noqa: E731
        has = lambda xs: any((x & M) == (truth & M) for x in xs)  # noqa: E731
        m = (loss[1] - loss[0]) / loss[0]
        fam = {step(S[0], 4 * j) & M for j in range(-3, 4)}
        other = next((l for x, l in zip(S, loss) if x & M not in fam), loss[-1])
        row = dict(video=name, visit=list(v), ch=r["ch"], counts=counts, truth=truth, old_off=r["grey_off"],
                   n_cands=len(cands), n_final=len(S), pick=S[0], off=off(S[0]), margin=float(m),
                   family_margin=float((other - loss[0]) / loss[0]), f0=G[gi[0]].f0, f0_setup=g.f0,
                   truth_in_cands=has(cands), truth_in_pool=has(pool), truth_in_final=has(S),
                   top=[(off(x), float(l)) for x, l in zip(S[:6], loss)], seconds=time.time() - t0)
        res.append(row)
        json.dump(res, open(a.out, "w"), indent=1, default=float)
        print(f"{name[:6]} CH{r['ch']:<2} {str(counts):<22} old off {r['grey_off']}  new off {row['off']} m {m:.3f} "
              f"fam {row['family_margin']:.3f} {[(k, round(l)) for k, l in row['top'][:4]]} truth in cands/pool/final "
              f"{row['truth_in_cands']}/{row['truth_in_pool']}/{row['truth_in_final']} ({row['seconds']:.0f}s)", flush=True)

if __name__ == "__main__":
    main()
