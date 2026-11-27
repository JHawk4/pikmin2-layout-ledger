"""Dive reading when an anchor seed is known: evaluation on Challenge Mode All Levels runs.

    python docs/challenge_dive/anchored_eval.py VIDEO [--span 250000] [--grey-only] [--ch ...] [--out F]

The anchor is the results screen after the stage (its digits give the RNG state at the start of
the roll). Across the six decoded CMAL runs the dive's first state lies 20k-184k draws before that
roll (median 54k; data/challenge/crosscheck/dive_distances.json), so the window is the `span` dive
states whose floor-1 layout seed lies before the roll. (With the previous stage's seed as the
anchor instead, the window runs forward by the same gameplay draws; the reading is the same.)

Per dive with a known truth (the preceding roll + 5):
1. grey reader over the window (read_dive; cached as dives/<video>_<first>_a<span>.json):
   stage, crop, dive start frame, fitted geometry, its ranking;
2. detection (flower templates) scores every window state at the grey geometry;
3. the detection leaders and the grey leaders are refit with the reverse term (back_w 2) and ranked;
4. the result: detection's pick, grey's pick, whether they agree, the truth's rank and its
   distance in draws from the pick (a multiple of 4 = the same dive one Pikmin over).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.dirname(__file__))
from det_eval import ROOT, offset, prepare, st  # noqa: E402
from p2seeds.challenge import dive as cd, dive_rgb as dr
from p2seeds import rng  # noqa: E402

M = 0x7FFFFFFF


def anchored_dives(video, span):
    name = os.path.basename(video)
    rolls = [r for r in json.load(open(os.path.join(ROOT, "data", "challenge", "results_rolls.json")))[name]["results"]
             if r.get("decoded")]
    visits = [tuple(v) for v in json.load(open(os.path.join(ROOT, "data", "challenge", f"visits_{name}.json")))]
    for prev, nxt in zip(rolls, rolls[1:]):
        vs = [v for v in visits if prev["last_frame"] < v[0] < nxt["first_frame"]]
        if len(vs) != 1:
            continue
        truth = rng.next_seed(st(prev["state_after_last_draw"]), 5) & 0xFFFFFFFF
        end = st(nxt.get("first_roll_state") or nxt["anchor_state"])
        yield vs[0], truth, end


NEAR = 110_000      # draws before the results roll that hold ~93% of dives (dive_distances.json)
DET_CLEAR = 0.10    # with an unclear grey read, a detection margin at or above this wins
SMALL = 15          # stages with at most this many Pikmin are read over the whole window in one go
CLEAR = 0.05        # a grey margin at or above this is taken without widening or cross-checking


_REG = {}


def video_reg(video):
    """The video's menu registration (flower grid, median over visits), cached beside the dives."""
    name = os.path.basename(video)
    if name not in _REG:
        cache = os.path.join(ROOT, "data", "challenge", "crosscheck", "dives", f"{name}_reg.json")
        if os.path.exists(cache):
            _REG[name] = json.load(open(cache))
        else:
            visits = json.load(open(os.path.join(ROOT, "data", "challenge", f"visits_{name}.json")))
            _REG[name] = cd.video_registration(video, visits)
            os.makedirs(os.path.dirname(cache), exist_ok=True)
            json.dump(_REG[name], open(cache, "w"))
    return _REG[name]


def _grey(video, v, truth, window, tag, log, extra=()):
    name = os.path.basename(video)
    cache = os.path.join(ROOT, "data", "challenge", "crosscheck", "dives", f"{name}_{v[0]}_{tag}.json")
    if os.path.exists(cache):
        return json.load(open(cache))
    t = time.time()
    r = cd.read_dive(video, v, window=window, probe=[truth], log=log, skip_if_clear=True, reg=video_reg(video),
                     prune_coarse=(4, 4), rank_mid=500, extra_states=extra)
    r["seconds"] = time.time() - t
    r["window"] = list(window)
    os.makedirs(os.path.dirname(cache), exist_ok=True)
    json.dump(r, open(cache, "w"), default=float)
    return r


def grey_read(video, v, truth, end, span, log=lambda s: None, near=NEAR, tag="h"):
    """Grey reader over the window, nearest states first: the `near` draws before the roll, and the
    rest only when that read has no clear leader. Returns the read with the larger margin."""
    r = _grey(video, v, truth, (end, min(near, span), 0), f"{tag}n{near // 1000}k", log)
    r["stages"] = 1
    if span > near and r.get("counts") and sum(r["counts"]) <= SMALL:
        # few Pikmin: a wrong state can lead a part of the window clearly, so rank the whole window at once
        r = _grey(video, v, truth, (end, span, 0), f"{tag}w{span // 1000}k", log)
        r["stages"] = 1
        return r
    if span <= near or (r.get("margin") or 0) >= CLEAR or not r.get("candidates"):
        return r
    # the far part's final ranking includes the near read's leaders, so its result is the whole window's
    near_lead = [c["state"] for c in r["candidates"][:12]] + [c["state"] for c in r.get("top", [])[:50]]
    r2 = _grey(video, v, truth, (end, span - near, near), f"{tag}r{near // 1000}k_{span // 1000}k", log, extra=near_lead)
    best = r2 if r2.get("candidates") else r
    best = dict(best, seconds=r.get("seconds", 0) + r2.get("seconds", 0), stages=2)
    return best


def setup_read(video, v, end, span, truth):
    """Stage, crop, dive start frame and reference geometry only (cheap: no state search)."""
    name = os.path.basename(video)
    cache = os.path.join(ROOT, "data", "challenge", "crosscheck", "dives", f"{name}_{v[0]}_s{span // 1000}k.json")
    if os.path.exists(cache):
        return json.load(open(cache))
    t = time.time()
    r = cd.read_dive(video, v, window=(end, span), setup_only=True, log=lambda s: None)
    r["window"] = [end, span]
    r["seconds"] = time.time() - t
    os.makedirs(os.path.dirname(cache), exist_ok=True)
    json.dump(r, open(cache, "w"), default=float)
    return r


def bootstrap(ds, g, window, iters=2, k=6, back_w=2.0, log=None):
    """Geometry from detection alone: score the window at g, fit the k leaders, move g to the best
    fit, repeat."""
    for it in range(iters):
        ds.back_w = 0.0
        sc = ds.score(g, window)
        lead = []
        for i in np.argsort(-sc):
            s = int(window[i])
            if all((s & M) != (x & M) for x in lead):
                lead.append(s)
            if len(lead) == k:
                break
        ds.back_w = back_w
        fits = [ds.fit(g, s) for s in lead]
        j = int(np.argmax([v for gk, v in fits]))
        g = fits[j][0]
        if log:
            log(f"    bootstrap {it}: leader {lead[j]:08X} {fits[j][1]:.1f}")
    return g


def family_of(s, span=3):
    """s and its one-Pikmin shifts (s -+ 4j draws, j <= span), as masked states."""
    out = set()
    for j in range(-span - 1, span + 2):          # one wider: a neighbour's family overlaps
        out.add((rng.next_seed(s, 4 * j) if j >= 0 else rng.prev_seed(s, -4 * j)) & M)
    return out


def read(ds, g, window, grey_states, first_n=40, grey_n=20, back_w=2.0, truth=None, family=3):
    """Detection read of one dive. Returns a dict with the ranking and diagnostics."""
    pool, pos = {}, {}
    if first_n:
        ds.back_w = 0.0
        sc = ds.score(g, window)                              # every window state, forward score only
        order = np.argsort(-sc)
        pos = {int(window[i]) & M: k for k, i in enumerate(order)}
    else:
        order = []
    for i in order[:first_n]:
        pool.setdefault(int(window[i]) & M, int(window[i]))
    for s in grey_states[:grey_n]:
        pool.setdefault(s & M, s)
    ds.back_w = back_w
    fits = sorted((ds.fit(g, s)[::-1] + (s,) for s in pool.values()), key=lambda x: -x[0])
    gb = fits[0][1]
    again = [(max(v, ds.fit(gb, s)[1]), s) for v, gk, s in fits[:10]]
    rank = sorted(again, reverse=True) + [(v, s) for v, gk, s in fits[10:]]
    if family:
        # the leader's one-Pikmin shifts look nearly the same: refit them all, so the pick within the
        # family is made among its members and the margin is measured against other families
        have = {s & M for v, s in rank}
        lead = rank[0][1]
        for j in range(-family, family + 1):
            m = rng.next_seed(lead, 4 * j) if j >= 0 else rng.prev_seed(lead, -4 * j)
            if j and (m & M) not in have:
                rank.append((ds.fit(gb, m)[1], m))
        rank.sort(reverse=True)
    fam = family_of(rank[0][1], family)
    sample = window[:: max(1, len(window) // 20000)]
    med = float(np.median(ds.score(gb, sample)))
    margin = (rank[0][0] - rank[1][0]) / max(1e-6, rank[0][0] - med)
    other = next((v for v, s in rank if (s & M) not in fam), rank[-1][0])
    fmargin = (rank[0][0] - other) / max(1e-6, rank[0][0] - med)
    out = dict(best=rank[0][1], margin=margin, family_margin=fmargin, top=[(float(v), int(s)) for v, s in rank[:10]])
    if truth is not None:
        out["truth_first_pass"] = pos.get(truth & M)
        out["truth_rank"] = next((k for k, (v, s) in enumerate(rank) if (s & M) == (truth & M)), None)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("videos", nargs="+")
    ap.add_argument("--span", type=int, default=250_000)
    ap.add_argument("--grey-only", action="store_true")
    ap.add_argument("--det-only", action="store_true",
                    help="no grey reader: cheap setup, geometry and ranking from detection alone (weak on dense stages)")
    ap.add_argument("--boot", type=int, default=2, help="detection-only geometry iterations")
    ap.add_argument("--ch", type=int, nargs="*")
    ap.add_argument("--first", type=int, default=0, help="detection's own window leaders refit (0: grey's only)")
    ap.add_argument("--grey-n", type=int, default=20, help="grey leaders refit")
    ap.add_argument("--back", type=float, default=2.0)
    ap.add_argument("--colour-body", action="store_true")
    ap.add_argument("--family", type=int, default=3, help="refit the leader's +-4j shifts, j <= this")
    ap.add_argument("--always-det", action="store_true", help="run the detection cross-check on clear grey reads too")
    ap.add_argument("--tag", default="h", help="cache tag for the grey reads")
    ap.add_argument("--visits", type=int, nargs="*", help="only the menu visits starting at these frames")
    ap.add_argument("--out")
    a = ap.parse_args()
    sp = dr.load_sprites()
    rows = json.load(open(a.out)) if a.out and os.path.exists(a.out) else []
    done = {(r["video"], r["visit"][0]) for r in rows}
    for video in a.videos:
        name = os.path.basename(video)
        for v, truth, end in anchored_dives(video, a.span):
            if (name, v[0]) in done or (a.visits and v[0] not in a.visits):
                continue
            t0 = time.time()
            try:
                r = setup_read(video, v, end, a.span, truth) if a.det_only else grey_read(video, v, truth, end, a.span, tag=a.tag)
            except Exception as e:                      # noqa: BLE001
                print(f"{name[:6]} {v} grey failed: {e!r}", flush=True)
                continue
            if not r.get("candidates"):
                print(f"{name[:6]} {v} no grey read ({r.get('note')})", flush=True)
                continue
            if a.ch and r["ch"] not in a.ch:
                continue
            grey = [c["state"] for c in r["candidates"] if "state" in c] + [c["state"] for c in r.get("top", [])]
            grey_ok = bool(grey) and (grey[0] & M) == (truth & M)
            line = (f"{name[:6]} CH{r['ch']:<3} {str(r['counts']):<22} grey {'OK ' if grey_ok else 'bad'} "
                    f"off {offset(grey[0], truth, 16) if grey else None} m {r.get('margin') or 0:.3f} ({r.get('seconds', 0):.0f}s)")
            clear = (r.get("margin") or 0) >= CLEAR
            if a.grey_only or (clear and not a.always_det and not a.det_only):
                rows.append(dict(video=name, visit=list(v), ch=r["ch"], counts=r["counts"], truth=truth,
                                 grey_off=offset(grey[0], truth, 16) if grey else None, grey_seconds=r.get("seconds"),
                                 grey_best=grey[0] if grey else None, grey_ok=grey_ok, grey_margin=r.get("margin"),
                                 stages=r.get("stages"), f0=r.get("f0"), det=False, final=grey[0] if grey else None,
                                 final_ok=grey_ok, clear=clear, seconds=time.time() - t0))
                print(line + f" | final {'OK ' if grey_ok else 'bad'} {'clear' if clear else 'unclear'} ({time.time() - t0:.0f}s)", flush=True)
                if a.out:
                    json.dump(rows, open(a.out, "w"), indent=1, default=float)
                continue
            ds, g = prepare(video, r, ["flower"], sp, a.colour_body)
            window = cd.window_states(end, a.span)
            if a.det_only:
                g = bootstrap(ds, g, window, a.boot, back_w=a.back)
            d = read(ds, g, window, grey, a.first, a.grey_n, a.back, truth, a.family)
            ok = (d["best"] & M) == (truth & M)
            off = offset(d["best"], truth, 16)
            agree = bool(grey) and (d["best"] & M) == (grey[0] & M)
            # the pick: grey, unless its lead is unclear and detection's is clear
            use_det = (not clear) and d["margin"] >= DET_CLEAR
            final = d["best"] if use_det else (grey[0] if grey else d["best"])
            final_ok = (final & M) == (truth & M)
            row = dict(video=name, visit=list(v), ch=r["ch"], counts=r["counts"], truth=truth, det=True,
                       stages=r.get("stages"), f0=r.get("f0"), final=final, final_ok=final_ok,
                       clear=bool(clear or use_det or agree),
                       grey_off=offset(grey[0], truth, 16) if grey else None, grey_seconds=r.get("seconds"),
                       grey_best=grey[0] if grey else None, grey_ok=grey_ok, grey_margin=r.get("margin"),
                       truth_in_grey=any((s & M) == (truth & M) for s in grey[:a.grey_n]),
                       det_ok=ok, det_off=off, agree=agree, seconds=time.time() - t0, **d)
            rows.append(row)
            print(line + f" | det {'OK ' if ok else 'bad'} off {off} m {d['margin']:.3f} first-pass {d['truth_first_pass']}"
                  f" rank {d['truth_rank']} agree {'Y' if agree else 'n'} | final {'OK ' if final_ok else 'bad'}"
                  f" {'clear' if row['clear'] else 'unclear'} ({time.time() - t0:.0f}s)", flush=True)
            if a.out:
                json.dump(rows, open(a.out, "w"), indent=1, default=float)
    if rows:
        n = len(rows)
        cl = [r for r in rows if r.get("clear")]
        print(f"dives {n}: final correct {sum(r['final_ok'] for r in rows)}, grey correct {sum(r['grey_ok'] for r in rows)}; "
              f"clear {len(cl)} of which correct {sum(r['final_ok'] for r in cl)}; detection run on {sum(bool(r.get('det')) for r in rows)}; "
              f"mean {np.mean([r['seconds'] for r in rows]):.0f}s per dive")

if __name__ == "__main__":
    main()
