"""Per-sublevel scale factors, shrunk toward 1 by empirical Bayes, tested by leave-one-runner-out."""
import json, sys
import numpy as np
import common, evalkit as ek, model as M


def eb_scales(P, x, fe=None):
    """beta_s ~ N(1, tau2); beta_s_hat ~ N(beta_s, se_s^2). Returns shrunk beta per sublevel and tau2."""
    m = ek.metrics(P, x, fe=fe)
    sig2 = float(((m["yr"] - m["beta"] * m["xr"]) ** 2).sum() / max(1, len(P) - 1))
    subs = {s: v for s, v in m["per_sub"].items() if v.get("sxx", 0) > 1e-6}
    b = np.array([v["beta"] for v in subs.values()]); v = np.array([sig2 / s["sxx"] for s in subs.values()])
    # method of moments for tau2
    tau2 = max(0.0, (np.sum((b - 1) ** 2) - np.sum(v)) / len(b))
    out = {}
    for (s, st), bi, vi in zip(subs.items(), b, v):
        k = tau2 / (tau2 + vi) if tau2 > 0 else 0.0
        out[s] = 1 + k * (bi - 1)
    return out, tau2


def apply(P, x, scales):
    return np.array([xi * scales.get(p["sub"], 1.0) for p, xi in zip(P, x)])


if __name__ == "__main__":
    prm = json.load(open(common.HERE / "data" / sys.argv[1]))
    P = common.plays("in"); x = M.preds(P, prm)
    sc, tau2 = eb_scales(P, x)
    print("tau2", tau2, "tau", np.sqrt(tau2))
    print({s: round(v, 2) for s, v in sorted(sc.items(), key=lambda r: r[1])})
    # LORO: scales fitted without the runner, the base model fixed
    runners = sorted({p["runner"] for p in P})
    xs = np.zeros(len(P))
    for r in runners:
        tr = [i for i, p in enumerate(P) if p["runner"] != r]
        s_r, _ = eb_scales([P[i] for i in tr], x[tr])
        for i, p in enumerate(P):
            if p["runner"] == r:
                xs[i] = x[i] * s_r.get(p["sub"], 1.0)
    print("LORO base  ", ek.fmt(ek.metrics(P, x)))
    print("LORO scaled", ek.fmt(ek.metrics(P, xs)))
