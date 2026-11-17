"""Every idea as a parameter set, scored in-sample; `--oos NAME` scores one idea out of sample.

Weights marked 'fit' are fitted in-sample (fit.py) and stored in data/params_<name>.json, so
the OOS evaluation uses exactly the in-sample parameters."""
import json, sys
import common, evalkit as ek, model as M, fit as F

HV = 20.0   # high-variance sublevels: 5th-95th spread of random-layout pod scores >= 20 s


def ideas():
    """name -> (base params, free params to fit in-sample)."""
    o = M.OLD
    W5 = ["w_walk", "w_carry", "w_haz", "w_gate", "w_adj"]
    return {
        "old": (o, []),
        "old_scaled": (o, ["scale"]),
        "no_bug_credit": ({**o, "w_bug": 0}, []),
        "decide": ({**o, "decide": True}, []),
        "decide_lens_water": ({**o, "decide": True, "lens_water": 100}, []),
        "no_optional": ({**o, "w_opt": 0}, []),
        "B+C+D": ({**o, "w_bug": 0, "w_opt": 0, "decide": True, "lens_water": 100}, []),
        "B+C+D_scaled": ({**o, "w_bug": 0, "w_opt": 0, "decide": True, "lens_water": 100}, ["scale"]),
        "B+C+D+weights": ({**o, "w_bug": 0, "w_opt": 0, "decide": True, "lens_water": 100}, W5),
        "soft5": ({**o, "w_bug": 0, "w_opt": 0, "decide": True, "lens_water": 100, "temp": 5}, W5),
    }


def params(name, P=None, fe=None):
    path = common.HERE / "data" / f"params_{name}.json"
    if path.exists():
        return json.loads(path.read_text())
    base, free = ideas()[name]
    prm = F.fit(P, base, free, fe=fe) if free else dict(base)
    path.write_text(json.dumps(prm, indent=1))
    return prm


def report(P, prm, fe=None):
    fe = fe or ek.FE(P)
    x = M.preds(P, prm)
    m = ek.metrics(P, x, fe=fe)
    sp = ek.spread_table()
    hv = [sp.get(p["sub"], 0) >= HV for p in P]
    import numpy as np
    h = ek.subset_metrics(P, x, np.array(hv), fe=fe)
    return m, h


def line(name, m, h):
    return f"{name:22s} {ek.fmt(m)} | high-var n={h['n']} R2={h['R2']:+.3f} beta={h['beta']:.2f}±{h['se']:.2f}"


if __name__ == "__main__":
    P = common.plays("in"); fe = ek.FE(P)
    if len(sys.argv) > 2 and sys.argv[1] == "--oos":
        Q = common.plays("oos"); feq = ek.FE(Q)
        for name in sys.argv[2:]:
            prm = params(name, P, fe)
            print("OOS", line(name, *report(Q, prm, feq)))
    else:
        names = sys.argv[1:] or list(ideas())
        for name in names:
            prm = params(name, P, fe)
            print("IN ", line(name, *report(P, prm, fe)))
