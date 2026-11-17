"""Shared evaluation for judge2: the same fixed-effects calibration as p2seeds.site.calibration().

A prediction x and an outcome y (cost = seconds - pokos/2) are both residualized on
sublevel and run fixed effects (Frisch-Waugh), then
    beta  = <xr, yr> / <xr, xr>       (1 = one predicted second is one real second)
    R2    = 1 - |yr - xr|^2 / |yr|^2  (the prediction taken at face value, slope 1)
    corr2 = corr(xr, yr)^2            (best achievable R2 after a global rescale)
Per-sublevel betas use the same residuals restricted to that sublevel's rows.

Plays come from data/plays.json; split from data/split.json. Only `in` (in-sample) is used
while developing; `oos` is evaluated once per idea, after the in-sample decision.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

D = Path(__file__).resolve().parent / "data"
ROOT = Path(__file__).resolve().parents[1]


def load_plays(side: str = "in") -> list[dict]:
    """side: 'in', 'oos' or 'all'. Fixed layouts (judge_fixed) carry no comparison and are dropped."""
    plays = [p for p in json.loads((D / "plays.json").read_text(encoding="utf-8"))["plays"] if not p["judge_fixed"]]
    split = json.loads((D / "split.json").read_text(encoding="utf-8"))
    oos = set(split["oos_runners"])
    if side == "in":
        plays = [p for p in plays if p["runner"] not in oos]
    elif side == "oos":
        plays = [p for p in plays if p["runner"] in oos]
    # a sublevel with one play carries no comparison
    cnt: dict[str, int] = {}
    for p in plays:
        cnt[p["sub"]] = cnt.get(p["sub"], 0) + 1
    return [p for p in plays if cnt[p["sub"]] >= 2]


def fe_matrix(plays: list[dict]) -> np.ndarray:
    subs = sorted({p["sub"] for p in plays})
    runs = sorted({p["run"] for p in plays})
    X = np.zeros((len(plays), len(subs) + len(runs) - 1))
    for k, p in enumerate(plays):
        X[k, subs.index(p["sub"])] = 1
        j = runs.index(p["run"])
        if j > 0:
            X[k, len(subs) + j - 1] = 1
    return X


class FE:
    """Residualizer for one set of plays."""

    def __init__(self, plays: list[dict]):
        self.plays = plays
        self.X = fe_matrix(plays)
        self.pinv = np.linalg.pinv(self.X)

    def resid(self, v) -> np.ndarray:
        v = np.asarray(v, dtype=float)
        return v - self.X @ (self.pinv @ v)


def spread_table() -> dict[str, float]:
    """5th-95th percentile spread of random-layout pod scores (CaveGen rank_file.txt)."""
    out = {}
    with open(ROOT / "vendor" / "CaveGen" / "files" / "rank_file.txt", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            key, _, rest = line.partition(";")
            if key.endswith("-pod"):
                v = np.array([float(x) for x in rest.strip().split(";") if x])
                out[key[:-4]] = float(np.percentile(v, 95) - np.percentile(v, 5))
    return out


def metrics(plays: list[dict], x, y=None, fe: FE | None = None, by_sub: bool = True) -> dict:
    fe = fe or FE(plays)
    y = np.array([p["cost"] for p in plays]) if y is None else np.asarray(y, float)
    xr, yr = fe.resid(x), fe.resid(y)
    dof = max(1, len(plays) - np.linalg.matrix_rank(fe.X) - 1)
    beta = float(xr @ yr / (xr @ xr)) if xr @ xr > 0 else float("nan")
    e = yr - beta * xr
    se = float(np.sqrt((e @ e) / dof / (xr @ xr))) if xr @ xr > 0 else float("nan")
    out = {"n": len(plays), "beta": beta, "se": se,
           "R2": float(1 - ((yr - xr) @ (yr - xr)) / (yr @ yr)),
           "corr2": float(np.corrcoef(xr, yr)[0, 1] ** 2), "sd_y": float(np.sqrt(yr @ yr / dof)),
           "rmse": float(np.sqrt(((yr - xr) @ (yr - xr)) / dof))}
    if by_sub:
        subs: dict[str, list[int]] = {}
        for k, p in enumerate(plays):
            subs.setdefault(p["sub"], []).append(k)
        per = {}
        for s, ks in subs.items():
            a, b = xr[ks], yr[ks]
            sxx = float(a @ a)
            if sxx <= 1e-9:
                per[s] = {"n": len(ks), "sxx": 0.0}
                continue
            bs = float(a @ b / sxx)
            es = b - bs * a
            se_s = float(np.sqrt((es @ es) / max(1, len(ks) - 2) / sxx)) if len(ks) > 2 else float("nan")
            per[s] = {"n": len(ks), "beta": bs, "se": se_s, "sxx": sxx, "sse1": float((b - a) @ (b - a)), "syy": float(b @ b)}
        out["per_sub"] = per
        # calibration heterogeneity: chi2 of per-sublevel betas against beta=1 (weights sxx/sigma^2)
        sig2 = float((e @ e) / dof)
        chi = sum(v["sxx"] * (v["beta"] - 1) ** 2 / sig2 for v in per.values() if v.get("sxx", 0) > 1e-9)
        out["chi2_beta1"] = chi
        out["k_subs"] = sum(1 for v in per.values() if v.get("sxx", 0) > 1e-9)
    out["xr"], out["yr"] = xr, yr
    return out


def subset_metrics(plays, x, keep, fe=None):
    """Metrics on a subset of rows, with the residuals computed on the full set."""
    m = metrics(plays, x, fe=fe, by_sub=False)
    xr, yr = m["xr"][keep], m["yr"][keep]
    beta = float(xr @ yr / (xr @ xr))
    e = yr - beta * xr
    return {"n": int(np.sum(keep)), "beta": beta, "se": float(np.sqrt((e @ e) / max(1, len(xr) - 1) / (xr @ xr))),
            "R2": float(1 - ((yr - xr) @ (yr - xr)) / (yr @ yr)), "corr2": float(np.corrcoef(xr, yr)[0, 1] ** 2)}


def fmt(m: dict) -> str:
    s = f"n={m['n']} R2={m['R2']:+.3f} corr2={m['corr2']:.3f} beta={m['beta']:.2f}±{m['se']:.2f}"
    if "chi2_beta1" in m:
        s += f" chi2(beta_s=1)={m['chi2_beta1']:.0f}/{m['k_subs']}"
    return s
