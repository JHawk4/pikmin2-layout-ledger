"""Largest residuals of judge2 (shipped) on the net outcome, in-sample unless 'all' is given."""
import sys, numpy as np, common, evalkit as ek
side = sys.argv[1] if len(sys.argv) > 1 else "in"
P = common.plays(side); fe = ek.FE(P)
x = np.array([p["J"]["pod2"] for p in P]); m = ek.metrics(P, x, fe=fe)
e = m["yr"] - m["xr"]
sp = ek.spread_table()
mad = np.median(np.abs(e - np.median(e))) * 1.4826
print(f"robust sd of residual {mad:.1f} s")
for k in np.argsort(-np.abs(e))[:int(sys.argv[2]) if len(sys.argv) > 2 else 30]:
    p = P[k]; ch = max(p["J"]["pod2_parts"]["choices"], key=lambda c: c["p"])
    got = [c[0] for c in (p["collected"] or []) if c] + [c[0] + "*" for c in (p.get("inferred") or [])]
    print(f"{p['sub']:6s} sp{sp.get(p['sub'],0):4.0f} {p['runner']:12s} {p['run'][:22]:22s} f{p['frame']:<7d} {p['layout_seed']} "
          f"e={e[k]:+6.1f} y={m['yr'][k]:+6.1f} x={m['xr'][k]:+6.1f} took={p['took']:6.1f} tp={p['treasure_pokos']} bug={p['bug_pokos']} "
          f"clip={p['bug_clipped']} skip={ch['skip']}@{ch['p']} got={got}")
