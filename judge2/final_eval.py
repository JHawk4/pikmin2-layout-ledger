"""Final comparison, old judge vs judge2 (the Rust pod2 score in data/judged.json).

  python judge2/final_eval.py            in-sample, OOS, all plays; per sublevel and per cave
"""
import json
import numpy as np
import common, evalkit as ek, model as M

HV = 20.0


def pooled_beta(xr, yr):
    b = float(xr @ yr / (xr @ xr)); e = yr - b * xr
    return b, float(np.sqrt((e @ e) / max(1, len(xr) - 1) / (xr @ xr)))


def block(side):
    P = common.plays(side); fe = ek.FE(P)
    old = np.array([p["judge"] for p in P]); new = np.array([p["J"]["pod2"] for p in P])
    sp = ek.spread_table(); hv = np.array([sp.get(p["sub"], 0) >= HV for p in P])
    out = {}
    for name, x in (("old", old), ("judge2", new)):
        m = ek.metrics(P, x, fe=fe); h = ek.subset_metrics(P, x, hv, fe=fe)
        caves = {}
        for cave in sorted({p["cave"] for p in P}):
            k = np.array([p["cave"] == cave for p in P])
            caves[cave] = pooled_beta(m["xr"][k], m["yr"][k]) + (int(k.sum()),)
        out[name] = (m, h, caves)
    return P, out


if __name__ == "__main__":
    # the Rust score must equal the Python model with the shipped (rounded) weights
    prm = {**M.OLD, "w_walk": 1.22, "w_carry": 0.78, "w_haz": 0.60, "w_gate": 0.58, "w_adj": 0.54,
           "w_bug": 0, "w_opt": 0, "decide": True, "lens_water": 100, "temp": 5}
    P = common.plays("all")
    d = np.abs(M.preds(P, prm) - np.array([p["J"]["pod2"] for p in P])).max()
    print(f"Rust pod2 vs Python model: max |diff| = {d:.4f} s over {len(P)} plays\n")
    res = {}
    for side in ("in", "oos", "all"):
        P, out = block(side); res[side] = (P, out)
        print(f"== {side} ==")
        for name, (m, h, caves) in out.items():
            print(f"{name:7s} {ek.fmt(m)} | high-var n={h['n']} R2={h['R2']:+.3f} corr2={h['corr2']:.3f} beta={h['beta']:.2f}±{h['se']:.2f}")
            print("        caves: " + "  ".join(f"{c} {b:.2f}±{s:.2f}" for c, (b, s, n) in caves.items()))
    # per-sublevel betas on all plays
    P, out = res["all"]
    sp = ek.spread_table()
    mo, mn = out["old"][0], out["judge2"][0]
    print("\nper sublevel (all plays): spread, n, old beta±se, judge2 beta±se, R2 old -> judge2 (slope 1)")
    for s in sorted(mn["per_sub"], key=lambda s: -sp.get(s, 0)):
        a, b = mo["per_sub"][s], mn["per_sub"][s]
        if b.get("sxx", 0) <= 1e-6:
            continue
        r_old = 1 - a["sse1"] / a["syy"] if a.get("syy") else float("nan")
        r_new = 1 - b["sse1"] / b["syy"] if b.get("syy") else float("nan")
        print(f"{s:7s} {sp.get(s, 0):5.1f} n={b['n']:3d}  old {a.get('beta', float('nan')):5.2f}±{a.get('se', float('nan')):.2f}"
              f"  new {b['beta']:5.2f}±{b['se']:.2f}   R2 {r_old:+.2f} -> {r_new:+.2f}")
