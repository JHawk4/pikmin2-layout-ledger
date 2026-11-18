"""Linear within-sublevel fits of measured creature pokos on route-distance bands (diagnostic)."""
import numpy as np, common, evalkit as ek
from creatures import teki_rows, taken_mask, actual_taken
P = common.plays("in"); fe = ek.FE(P)
y = np.array([p["bug_pokos"] for p in P], float); yr = fe.resid(y)
def feats(rows, bands=(100, 200, 400, 800)):
    f = [sum(pk for pk, d, car, *_ in rows if car)]
    lo = 0
    for b in bands:
        f.append(sum(pk for pk, d, car, *_ in rows if not car and lo <= d < b)); lo = b
    f.append(sum(pk for pk, d, car, *_ in rows if not car and d >= lo))
    return f
def chosen(p):
    return max(p["J"]["pod2_parts"]["choices"], key=lambda c: c["p"])["skip"]
for label, tk in (("judge2 route", lambda p: taken_mask(p, chosen(p))), ("actual route", actual_taken)):
    F = np.array([feats(teki_rows(p, tk(p))) for p in P], float)
    Fr = np.column_stack([fe.resid(F[:, j]) for j in range(F.shape[1])])
    b, *_ = np.linalg.lstsq(Fr, yr, rcond=None)
    r2 = 1 - ((yr - Fr @ b) ** 2).sum() / (yr @ yr)
    # leave-one-runner-out
    pred = np.zeros(len(P))
    for r in sorted({p["runner"] for p in P}):
        tr = np.array([p["runner"] != r for p in P])
        bb, *_ = np.linalg.lstsq(Fr[tr], yr[tr], rcond=None); pred[~tr] = Fr[~tr] @ bb
    cv = 1 - ((yr - pred) ** 2).sum() / (yr @ yr)
    print(f"{label}: coef (carrier, <100, 100-200, 200-400, 400-800, >800 cm) = {np.round(b, 2)}  in R2 {r2:.3f}  LORO CV R2 {cv:.3f}")
    # per-sublevel within R2 for the high creature-variance sublevels
