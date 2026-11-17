"""In-sample fits of the judge2 weights (never reads OOS outcomes)."""
import sys
import numpy as np
from scipy.optimize import minimize
import common, evalkit as ek, model as M


def fit(P, base, free, fe=None, x0=None):
    fe = fe or ek.FE(P)
    yr = fe.resid([p["cost"] for p in P])

    def loss(th):
        prm = {**base, **dict(zip(free, th))}
        xr = fe.resid(M.preds(P, prm))
        return float((yr - xr) @ (yr - xr))
    x0 = x0 or [base[k] for k in free]
    r = minimize(loss, x0, method="Powell", options={"xtol": 1e-3, "ftol": 1e-6, "maxiter": 20000})
    r = minimize(loss, r.x, method="Nelder-Mead", options={"xatol": 1e-3, "fatol": 1e-6, "maxiter": 20000})
    return {**base, **dict(zip(free, [float(v) for v in r.x]))}


def boot(P, base, free, n=100, seed=1):
    """Cluster bootstrap over runs."""
    rng = np.random.default_rng(seed)
    runs = sorted({p["run"] for p in P})
    out = []
    for _ in range(n):
        pick = rng.choice(runs, len(runs))
        Q = []
        for k, r in enumerate(pick):
            Q += [{**p, "run": f"{r}#{k}"} for p in P if p["run"] == r]
        out.append([fit(Q, base, free)[k] for k in free])
    return np.array(out)
