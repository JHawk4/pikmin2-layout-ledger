"""Ideas for the net-timesave judge2 (creature pokos in the outcome), scored in-sample with
leave-one-runner-out CV; `--oos NAME...` scores ideas out of sample (once each, after the
in-sample decision). Fitted weights are stored in data/net_params_<name>.json so the OOS
evaluation uses exactly the in-sample parameters.

  python judge2/ideas_net.py [NAME...]
  python judge2/ideas_net.py --oos NAME...
"""
import json, sys
import numpy as np
import common, evalkit as ek, vmodel as V
from creatures import teki_rows, taken_mask, fit as cre_fit

HV = 20.0
HERE = common.HERE


def creature_theta():
    path = HERE / "data" / "net_creature_theta.json"
    if path.exists():
        return json.loads(path.read_text())["theta"]
    P = common.plays("in")
    R = [teki_rows(p, taken_mask(p, max(p["J"]["pod2_parts"]["choices"], key=lambda c: c["p"])["skip"])) for p in P]
    th = [float(t) for t in cre_fit(R, np.array([p["bug_pokos"] for p in P], float))]
    path.write_text(json.dumps({"theta": th, "fit_on": "in-sample creature pokos, judge2's likeliest route"}, indent=1))
    return th


B5 = [V.W0[c] for c in V.BASE]


def ideas():
    """name -> (columns, start weights, indices to fit, temp, cv?)"""
    return {
        "N0_shipped": (V.BASE, B5, [], 5.0),
        "N1_refit": (V.BASE, B5, [0, 1, 2, 3, 4], 5.0),
        "N2_refit+bug_free": (V.BASE + ["bug"], B5 + [0.0], [0, 1, 2, 3, 4, 5], 5.0),
        "N3_refit+cre_credit": (V.BASE + ["cre"], B5 + [-1.0], [0, 1, 2, 3, 4], 5.0),
        "N4_refit+cre_free": (V.BASE + ["cre"], B5 + [-1.0], [0, 1, 2, 3, 4, 5], 5.0),
        "N5_refit+carrier_credit": (V.BASE + ["cre_car"], B5 + [-1.0], [0, 1, 2, 3, 4], 5.0),
        "N6_shipped+cre_credit": (V.BASE + ["cre"], B5 + [-1.0], [], 5.0),
        # hazard split: fights with creatures that repay pokos vs the rest
        "N7_haz_split": (["walking", "carry", "haz_nocre", "gate", "adj", "haz_cre"], B5 + [0.6], [0, 1, 2, 3, 4, 5], 5.0),
        "N8_refit_temp2": (V.BASE, B5, [0, 1, 2, 3, 4], 2.0),
        "N8_refit_temp10": (V.BASE, B5, [0, 1, 2, 3, 4], 10.0),
        # the captain walks corridors: union of the routes on the waypoint tree
        "N9_tree_walk_instead": (["tree_walk", "carry", "hazard", "gate", "adj"], [0.5] + B5[1:], [0, 1, 2, 3, 4], 5.0),
        "N10_tree_walk_added": (V.BASE + ["tree_walk"], B5 + [0.0], [0, 1, 2, 3, 4, 5], 5.0),
    }


_D = {}


def data(side, cols):
    key = (side, tuple(cols))
    if key not in _D:
        _D[key] = V.Data(common.plays(side), cols, theta=creature_theta())
    return _D[key]


def params(name):
    path = HERE / "data" / f"net_params_{name}.json"
    if path.exists():
        return json.loads(path.read_text())
    cols, w0, free, temp = ideas()[name]
    w = V.fit(data("in", cols), w0, free, temp) if free else np.array(w0, float)
    prm = {"cols": cols, "w": [float(x) for x in w], "temp": temp}
    path.write_text(json.dumps(prm, indent=1))
    return prm


def report(D, x):
    m = ek.metrics(D.P, x, fe=D.fe)
    sp = ek.spread_table(); hv = np.array([sp.get(p["sub"], 0) >= HV for p in D.P])
    h = ek.subset_metrics(D.P, x, hv, fe=D.fe)
    return m, h


def line(tag, name, m, h, cv=None):
    s = f"{tag} {name:26s} {ek.fmt(m)} | hv n={h['n']} R2={h['R2']:+.3f} beta={h['beta']:.2f}"
    if cv is not None:
        s += f" | LORO-CV R2={cv['R2']:+.3f} beta={cv['beta']:.2f}"
    return s


if __name__ == "__main__":
    args = sys.argv[1:]
    if args and args[0] == "--oos":
        for name in args[1:]:
            prm = params(name)
            D = data("oos", prm["cols"])
            print(line("OOS", name, *report(D, D.preds(prm["w"], prm["temp"]))))
    else:
        for name in args or list(ideas()):
            prm = params(name)
            cols, w0, free, temp = ideas()[name]
            D = data("in", cols)
            cv = ek.metrics(D.P, V.loro(D, w0, free, temp), fe=D.fe, by_sub=False) if free else None
            print(line("IN ", name, *report(D, D.preds(prm["w"], temp)), cv))
            print("     w:", dict(zip(prm["cols"], np.round(prm["w"], 3))))
