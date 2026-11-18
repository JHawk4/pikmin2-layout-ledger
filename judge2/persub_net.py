"""Per-sublevel calibration of judge2 vs the old judge (in-sample by default)."""
import sys, numpy as np, common, evalkit as ek
side = sys.argv[1] if len(sys.argv) > 1 else "in"
P = common.plays(side); fe = ek.FE(P); sp = ek.spread_table()
mo = ek.metrics(P, [p["judge"] for p in P], fe=fe); mn = ek.metrics(P, [p["J"]["pod2"] for p in P], fe=fe)
print("sub     spread  n   old beta±se    judge2 beta±se  R2 old->j2   SSE share j2")
tot = sum(v["sse1"] for v in mn["per_sub"].values() if "sse1" in v)
for s in sorted(mn["per_sub"], key=lambda s: -sp.get(s, 0)):
    a, b = mo["per_sub"][s], mn["per_sub"][s]
    if b.get("sxx", 0) <= 1e-6: continue
    print(f"{s:7s} {sp.get(s,0):5.1f} {b['n']:3d}  {a.get('beta',np.nan):5.2f}±{a.get('se',np.nan):.2f}   {b['beta']:5.2f}±{b['se']:.2f}"
          f"   {1-a['sse1']/a['syy']:+.2f}->{1-b['sse1']/b['syy']:+.2f}   {b['sse1']/tot:.3f}")
