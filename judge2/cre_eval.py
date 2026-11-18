"""Creature-poko model (creatures.py, theta fitted in-sample) against measured creature pokos."""
import json, collections, numpy as np, common, evalkit as ek
from creatures import teki_rows, taken_mask, expected, within_r2
th = json.load(open(common.HERE / "data" / "net_creature_theta.json"))["theta"]
Pin = common.plays("in")
sub_mean = collections.defaultdict(list)
for p in Pin: sub_mean[p["sub"]].append(p["bug_pokos"])
sub_mean = {k: np.mean(v) for k, v in sub_mean.items()}
def chosen(p): return max(p["J"]["pod2_parts"]["choices"], key=lambda c: c["p"])["skip"]
print("theta (a, b_carrier, s cm):", np.round(th, 2))
for side in ("in", "oos"):
    P = common.plays(side); fe = ek.FE(P)
    y = np.array([p["bug_pokos"] for p in P], float)
    x = np.array([expected(teki_rows(p, taken_mask(p, chosen(p))), th) for p in P])
    cap = np.array([p["creature_cap"] or 0 for p in P], float)
    sm = np.array([sub_mean.get(p["sub"], np.nan) for p in P]); ok = ~np.isnan(sm)
    old = np.array([2 * p["J"]["layout"]["variants"][0]["bug"] for p in P])
    def lev(z, k=slice(None)): return 1 - ((y[k] - z[k]) ** 2).sum() / ((y[k] - y[k].mean()) ** 2).sum()
    print(f"{side}: n={len(P)} measured mean {y.mean():.2f} (sd {y.std():.2f}); model mean {x.mean():.2f}; "
          f"level R2 model {lev(x):.3f}, in-sample sublevel means {lev(sm, ok):.3f}, old judge bug term {lev(old):.3f}, cap {lev(cap):.3f}; "
          f"MAE model {np.abs(y-x).mean():.2f}; within-sublevel corr2 model {within_r2(P, fe, x, y)['corr2']:.3f}, "
          f"old bug term {within_r2(P, fe, old, y)['corr2']:.3f}; share of measured<=cap {(y <= cap + 0.5).mean():.3f}; mean measured/cap {y.sum()/cap.sum():.2f}")
