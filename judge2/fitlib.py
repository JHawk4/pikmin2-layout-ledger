"""Helpers for in-sample fits on the variant parts."""
import numpy as np
import evalkit as ek

PARTS = ["walking", "carry", "hazard", "gate", "optional", "poko", "bug", "adj", "water_carry", "water_carry_max",
         "water_hole", "hole_walk", "gate_hole", "carrier_fight", "taken"]


def full(p):
    return p["J"]["layout"]["variants"][0]


def ols(P, cols, fe=None, names=None):
    fe = fe or ek.FE(P)
    y = fe.resid([p["cost"] for p in P])
    X = np.column_stack([fe.resid(c) for c in cols])
    keep = [i for i in range(X.shape[1]) if X[:, i].std() > 1e-9]
    b, *_ = np.linalg.lstsq(X[:, keep], y, rcond=None)
    e = y - X[:, keep] @ b
    dof = len(y) - len(keep) - np.linalg.matrix_rank(fe.X)
    cov = (e @ e / dof) * np.linalg.inv(X[:, keep].T @ X[:, keep])
    out = {}
    for j, i in enumerate(keep):
        out[(names or list(range(X.shape[1])))[i]] = (float(b[j]), float(np.sqrt(cov[j, j])))
    return out, float(1 - e @ e / (y @ y))
