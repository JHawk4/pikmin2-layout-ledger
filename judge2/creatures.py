"""Creature ("bug") pokos: which creatures a runner kills and carries home, from the layout.

Measured per play: bug_pokos (treasures.json; creature pokos between two panels are shared
among the sublevels in between by time, so a sublevel without its own panel gets a smeared
share). Layout side (judge2 dump): every teki with its pokos, whether it leaves a carcass,
and its distance to each treasure's carry route and to the ship-hole route.

Model: E[creature pokos] = sum over carcass teki of pokos * p_kill, with
    p_kill = sigmoid(a + b_carrier * carries_a_taken_treasure - d / s)
d = straight-line distance (cm) from the teki to the nearest route the runner travels
(the hole route and the routes of the treasures taken). Fitted by least squares on the
measured creature pokos of in-sample plays; scored within sublevel (sublevel and run fixed
effects, as the time outcome).

  python judge2/creatures.py             in-sample fits and comparisons
"""
import sys
import numpy as np
from scipy.optimize import least_squares
import common, evalkit as ek


def taken_mask(p, skipped=None):
    """Which dump treasures (by index) the runner takes: counted ones not in `skipped`."""
    T = p["J"]["layout"]["treasures"]
    sk = list(skipped or [])
    out = []
    for t in T:
        if t["kind"] != "counted":
            out.append(False)
        elif t["name"] in sk:
            sk.remove(t["name"]); out.append(False)
        else:
            out.append(True)
    return out


def actual_taken(p):
    """Treasures the runner actually collected (panel reads), by dump index."""
    T = p["J"]["layout"]["treasures"]
    got = [c[0].lower() for c in (p.get("collected") or []) if c] + [c[0].lower() for c in (p.get("inferred") or [])]
    out = []
    for t in T:
        if t["name"] in got:
            got.remove(t["name"]); out.append(True)
        else:
            out.append(False)
    return out


def teki_rows(p, taken):
    """Per carcass teki: (pokos, d_route, carries_taken, d_hole, d_tre_min, off_route)."""
    L = p["J"]["layout"]; T = L["treasures"]
    rows = []
    for t in L["tekis"]:
        if not t["carcass"] or t["pokos"] <= 0:
            continue
        dh = t["near_hole"] if t["near_hole"] >= 0 else 1e4
        dt = [d for d, k in zip(t["near_tre"], taken) if k]
        ot = [d for d, k in zip(t["off_tre"], taken) if k]
        carrier = bool(t["carrying"]) and any(k and tr["carried_by"] == t["name"] and tr["name"] == (t["carrying"] or "").lower()
                                              for tr, k in zip(T, taken))
        rows.append((t["pokos"], min([dh] + dt), carrier, dh, min(dt) if dt else 1e4, min([t["off_hole"]] + ot), t["name"]))
    return rows


def expected(rows, th):
    a, bc, s = th[:3]
    e = 0.0
    for pk, d, car, *_ in rows:
        z = a + bc * car - d / max(s, 1.0)
        e += pk / (1 + np.exp(-z))
    return e


def fit(R, y, th0=(1.0, 3.0, 100.0)):
    r = least_squares(lambda th: np.array([expected(rows, th) for rows in R]) - y, th0,
                      bounds=([-10, -10, 5], [10, 20, 5000]))
    return r.x


def within_r2(P, fe, x, y):
    xr, yr = fe.resid(x), fe.resid(y)
    b = xr @ yr / (xr @ xr) if xr @ xr > 0 else 0
    return {"R2_slope1": 1 - (yr - xr) @ (yr - xr) / (yr @ yr), "corr2": np.corrcoef(xr, yr)[0, 1] ** 2 if xr.std() > 0 else 0,
            "beta": b, "level_R2": 1 - ((y - x) ** 2).sum() / ((y - y.mean()) ** 2).sum()}


if __name__ == "__main__":
    P = common.plays("in"); fe = ek.FE(P)
    y = np.array([p["bug_pokos"] for p in P], float)
    cap = np.array([p["creature_cap"] or 0 for p in P], float)
    oldbug = np.array([2 * p["J"]["layout"]["variants"][0]["bug"] for p in P])
    yr = fe.resid(y)
    print(f"in-sample n={len(P)}: creature pokos mean {y.mean():.2f}, within-sub(+run) sd {yr.std():.2f}; "
          f"share of within-sub cost variance: {np.var(fe.resid(y / 2)) / np.var(fe.resid([p['cost'] for p in P])):.3f}")
    for name, x in (("cap", cap), ("old judge bug term", oldbug)):
        print(f"{name:28s}", {k: round(float(v), 3) for k, v in within_r2(P, fe, x, y).items()})
    # the runner's actual route (diagnostic: what can the layout explain at best)
    Ra = [teki_rows(p, actual_taken(p)) for p in P]
    tha = fit(Ra, y); xa = np.array([expected(r, tha) for r in Ra])
    print(f"{'actual route, fit':28s}", np.round(tha, 2), {k: round(float(v), 3) for k, v in within_r2(P, fe, xa, y).items()})
    # judge2's route: the most likely take/skip choice
    def chosen_skip(p):
        ch = p["J"]["pod2_parts"]["choices"]
        return max(ch, key=lambda c: c["p"])["skip"]
    Rj = [teki_rows(p, taken_mask(p, chosen_skip(p))) for p in P]
    thj = fit(Rj, y); xj = np.array([expected(r, thj) for r in Rj])
    print(f"{'judge2 route, fit':28s}", np.round(thj, 2), {k: round(float(v), 3) for k, v in within_r2(P, fe, xj, y).items()})
    # leave-one-runner-out CV of the within-sub fit
    runners = sorted({p["runner"] for p in P})
    cv = np.zeros(len(P))
    for r in runners:
        tr = [i for i, p in enumerate(P) if p["runner"] != r]; te = [i for i, p in enumerate(P) if p["runner"] == r]
        th = fit([Rj[i] for i in tr], y[tr], thj)
        for i in te:
            cv[i] = expected(Rj[i], th)
    print(f"{'judge2 route, LORO CV':28s}", {k: round(float(v), 3) for k, v in within_r2(P, fe, cv, y).items()})
