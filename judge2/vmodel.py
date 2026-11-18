"""Vectorized judge2 model for fast refits on the net-timesave snapshot.

Every play has its take/skip variants (judge2 dump). For variant v:
    score(v) = sum_k w_k * F_k(v) + offset(v)
    offset   = (missing treasure pokos)/2 + cut * taken + lens_water * [SH-6 lens across water]
    F        = walking, carry, hazard, gate, adj, plus any extra columns an idea adds
prediction = sum_v score(v) * softmax(-score / temp)   (judge2's soft take/skip choice)

The shipped judge2 is W0 below; check() verifies this reproduces the Rust score.
Extra columns (per variant, computed in Python from the dump):
    bug      the old judge's bug-poko credit, pokos/2 (in-the-way carcass teki near the ship)
    cre      expected creature pokos / 2 on the variant's route (creatures.py model)
    cre_car  creature pokos / 2 of teki that carry a treasure this variant takes
"""
import numpy as np
import common, evalkit as ek
from creatures import teki_rows, taken_mask, expected

BASE = ["walking", "carry", "hazard", "gate", "adj"]
W0 = {"walking": 1.22, "carry": 0.78, "hazard": 0.60, "gate": 0.58, "adj": 0.54}
CRE_THETA = None      # set by load(); the creature kill model fitted on in-sample creature pokos


def variant_cols(p, v, theta):
    rows = teki_rows(p, taken_mask(p, v["skipped"]))
    worth = {t["name"].lower(): t["carcass"] and t["pokos"] > 0 for t in p["J"]["layout"]["tekis"]}
    haz_cre = sum(s for k, s in v["haz_by"].items() if worth.get(k, False))
    return {"bug": v["bug"],
            "haz_cre": haz_cre, "haz_nocre": v["hazard"] - haz_cre,
            "cre": expected(rows, theta) / 2 if theta is not None else 0.0,
            "cre_car": sum(pk for pk, d, car, *_ in rows if car) / 2,
            "hazard_hole": v["hazard_hole"], "water_carry": v["water_carry"] / 100.0, "taken": v["taken"]}


class Data:
    """Per play: variant feature matrix (n_variants x n_cols) and offsets."""

    def __init__(self, P, cols, theta=None, cut=10.0, lens_water=100.0):
        self.P, self.cols = P, list(cols)
        self.F, self.off = [], []
        for p in P:
            V = p["J"]["layout"]["variants"]
            F = np.zeros((len(V), len(self.cols)))
            off = np.zeros(len(V))
            for i, v in enumerate(V):
                extra = variant_cols(p, v, theta) if any(c not in v for c in self.cols) else {}
                for j, c in enumerate(self.cols):
                    F[i, j] = extra[c] if c in extra else v[c]
                off[i] = v["poko"] + cut * v["taken"] + (lens_water if v["lens_cross"] > 0 else 0.0)
            self.F.append(F); self.off.append(off)
        self.fe = ek.FE(P)
        self.y = np.array([p["cost"] for p in P])

    def preds(self, w, temp=5.0):
        w = np.asarray(w, float)
        out = np.empty(len(self.P))
        for k, (F, off) in enumerate(zip(self.F, self.off)):
            s = F @ w + off
            if temp > 0:
                e = np.exp(-(s - s.min()) / temp)
                out[k] = e @ s / e.sum()
            else:
                out[k] = s.min()
        return out

    def subset(self, idx):
        d = object.__new__(Data)
        d.P = [self.P[i] for i in idx]; d.cols = self.cols
        d.F = [self.F[i] for i in idx]; d.off = [self.off[i] for i in idx]
        d.fe = ek.FE(d.P); d.y = self.y[idx]
        return d


def fit(D, w0, free=None, temp=5.0, ridge=0.0, prior=None):
    """Least squares of the residualized prediction on the residualized cost (slope 1).
    free: indices of columns to fit (others fixed at w0). ridge pulls toward prior (scaled)."""
    from scipy.optimize import minimize
    w0 = np.asarray(w0, float); free = list(range(len(w0))) if free is None else list(free)
    prior = w0.copy() if prior is None else np.asarray(prior, float)
    yr = D.fe.resid(D.y)

    def loss(th):
        w = w0.copy(); w[free] = th
        xr = D.fe.resid(D.preds(w, temp))
        return float((yr - xr) @ (yr - xr)) + ridge * float(((w[free] - prior[free]) ** 2).sum()) * len(D.P)
    r = minimize(loss, w0[free], method="Powell", options={"xtol": 1e-3, "ftol": 1e-7, "maxiter": 20000})
    w = w0.copy(); w[free] = r.x
    return w


def loro(D, w0, free=None, temp=5.0, **kw):
    """Leave-one-runner-out predictions (weights refitted without each runner)."""
    pred = np.zeros(len(D.P))
    for r in sorted({p["runner"] for p in D.P}):
        tr = [i for i, p in enumerate(D.P) if p["runner"] != r]
        te = [i for i, p in enumerate(D.P) if p["runner"] == r]
        w = fit(D.subset(tr), w0, free, temp, **kw)
        pred[te] = D.subset(te).preds(w, temp)
    return pred


def check(side="all"):
    P = common.plays(side)
    D = Data(P, BASE)
    x = D.preds([W0[c] for c in BASE])
    return float(np.abs(x - np.array([p["J"]["pod2"] for p in P])).max())


if __name__ == "__main__":
    print("max |vmodel - Rust pod2| =", check())
