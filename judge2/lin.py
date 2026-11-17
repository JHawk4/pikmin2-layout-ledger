"""Linear (ridge-toward-prior) fits on the chosen variant, with leave-one-runner-out CV.

Prediction = offset + sum_k w_k * f_k, offsets have weight 1. Ridge pulls each w_k toward its
prior prior_k with strength lam (in units of 'plays' of Sxx: penalty lam * sum (w-prior)^2 * s_k^2
where s_k^2 is the feature's residual variance, so lam is scale free)."""
import numpy as np
import evalkit as ek


def design(P, feats, chosen):
    """feats(v, p) -> (dict features, offset)."""
    rows, off = [], []
    for p, v in zip(P, chosen):
        f, o = feats(v, p)
        rows.append(f); off.append(o)
    keys = sorted({k for r in rows for k in r})
    X = np.array([[r.get(k, 0.0) for k in keys] for r in rows])
    return keys, X, np.array(off)


def ridge(P, keys, X, off, prior, lam, fe=None):
    fe = fe or ek.FE(P)
    yr = fe.resid([p["cost"] for p in P]) - fe.resid(off)
    Xr = np.column_stack([fe.resid(X[:, i]) for i in range(X.shape[1])])
    w0 = np.array([prior.get(k, 0.0) for k in keys])
    s2 = (Xr ** 2).mean(axis=0) + 1e-9
    A = Xr.T @ Xr + lam * np.diag(s2) * 1.0
    b = Xr.T @ yr + lam * s2 * w0
    w = np.linalg.solve(A, b)
    return dict(zip(keys, w))


def predict(keys, X, off, w):
    return off + X @ np.array([w.get(k, 0.0) for k in keys])


def loro(P, keys, X, off, prior, lam):
    """Leave-one-runner-out: fit on the other runners, predict the held-out runner; then score
    all held-out predictions together with the usual fixed effects."""
    runners = sorted({p["runner"] for p in P})
    pred = np.zeros(len(P))
    for r in runners:
        tr = [i for i, p in enumerate(P) if p["runner"] != r]
        te = [i for i, p in enumerate(P) if p["runner"] == r]
        Ptr = [P[i] for i in tr]
        w = ridge(Ptr, keys, X[tr], off[tr], prior, lam)
        pred[te] = predict(keys, X[te], off[te], w)
    return ek.metrics(P, pred, by_sub=False)
