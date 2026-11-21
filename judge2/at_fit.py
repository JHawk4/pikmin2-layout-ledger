"""Fit at2's weights on All Treasures floor times (judge2/data/at_plays.json, at_snapshot.py).

    took = runner + sublevel + sum_k w_k * part_k + noise

with a fixed effect per sublevel and per runner, so only differences between layouts of the
same sublevel (and between runners' paces) inform the weights. Parts that are constant within a
sublevel (the treasure count) cancel out. Each weight is shrunk towards CaveGen's (1) by a
ridge penalty `lam` (in seconds² per unit² of weight), and every choice is checked by leaving one
run out: fit on the others, predict the left-out run's layout differences.

    python judge2/at_fit.py            prints CaveGen vs fitted, in-sample and leave-one-run-out
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

PARTS = ["walking", "purple_walk", "carry", "hazard", "gate"]
HERE = Path(__file__).resolve().parent


def load(min_plays: int = 2) -> list[dict]:
    rows = json.loads((HERE / "data" / "at_plays.json").read_text(encoding="utf-8"))
    n = {}
    for r in rows:
        n[r["sub"]] = n.get(r["sub"], 0) + 1
    return [r for r in rows if n[r["sub"]] >= min_plays]


def design(rows):
    subs = sorted({r["sub"] for r in rows})
    runners = sorted({r["runner"] for r in rows})
    F = np.zeros((len(rows), len(subs) + len(runners) - 1))
    for k, r in enumerate(rows):
        F[k, subs.index(r["sub"])] = 1
        j = runners.index(r["runner"])
        if j:
            F[k, len(subs) + j - 1] = 1
    X = np.array([[r[p] for p in PARTS] for r in rows], float)
    y = np.array([r["took"] for r in rows], float)
    return F, X, y


def resid(F, v):
    coef, *_ = np.linalg.lstsq(F, v, rcond=None)
    return v - F @ coef


def fit(rows, lam=50.0, parts=PARTS):
    F, X, y = design(rows)
    idx = [PARTS.index(p) for p in parts]
    Xr = np.column_stack([resid(F, X[:, i]) for i in idx])
    yr = resid(F, y)
    prior = np.ones(len(idx))
    A = Xr.T @ Xr + lam * np.eye(len(idx))
    w = np.linalg.solve(A, Xr.T @ yr + lam * prior)
    full = np.ones(len(PARTS))
    full[idx] = w
    return full


def score(rows, w):
    return np.array([sum(wk * r[p] for wk, p in zip(w, PARTS)) for r in rows])


def explained(rows, w):
    """Share of the within-sublevel, within-runner variance of time that the judge explains
    at face value (slope 1), and the fitted slope."""
    F, _, y = design(rows)
    xr, yr = resid(F, score(rows, w)), resid(F, y)
    e = yr - xr
    return 1 - (e @ e) / (yr @ yr), float(xr @ yr / (xr @ xr)), float(np.corrcoef(xr, yr)[0, 1])


def loro(rows, lam, parts=PARTS):
    """Leave one run out: squared error of the left-out run's layout differences, predicted by a
    judge fitted without it (sublevel and runner levels refitted on all rows, judge weights not)."""
    runs = sorted({r["run"] for r in rows})
    err = {"cavegen": 0.0, "fit": 0.0}
    n = 0
    for out in runs:
        train = [r for r in rows if r["run"] != out]
        w = fit(train, lam, parts)
        for name, ww in (("cavegen", np.ones(len(PARTS))), ("fit", w)):
            F, _, y = design(rows)
            yr = resid(F, y - score(rows, ww))
            m = np.array([r["run"] == out for r in rows])
            err[name] += float(yr[m] @ yr[m])
        n += int(sum(r["run"] == out for r in rows))
    return {k: v / n for k, v in err.items()}, n


if __name__ == "__main__":
    rows = load()
    print(f"{len(rows)} plays, {len({r['sub'] for r in rows})} sublevels, {len({r['run'] for r in rows})} runs")
    one = np.ones(len(PARTS))
    r2, slope, corr = explained(rows, one)
    print(f"CaveGen at:   R2 {r2:.3f}  slope {slope:.2f}  corr {corr:.2f}")
    for lam in (0.0, 10.0, 50.0, 200.0, 1000.0):
        w = fit(rows, lam)
        r2, slope, corr = explained(rows, w)
        cv, n = loro(rows, lam)
        print(f"lam {lam:6g}: " + " ".join(f"{p} {x:.2f}" for p, x in zip(PARTS, w))
              + f" | R2 {r2:.3f} slope {slope:.2f} | LORO mse cavegen {cv['cavegen']:.0f} fit {cv['fit']:.0f} (n {n})")
