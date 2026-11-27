"""Seed-free measurement of each visible dive Pikmin, then a lattice search for the dive's first state.
Geometry (scale, group origins, frame phase) is given: calibrated once per video layout."""
import sys, math, json, numpy as np
from scipy.optimize import differential_evolution
sys.path.insert(0, __import__("os").path.dirname(__file__))
import divefit2 as F
sys.path.insert(0, "p2seeds/src")
from p2seeds import rng
from p2seeds.story.lattice import box_points
M = 1 << 31; UNIT = 1 << 16

def measure(geom, nvis=5, seed=0):
    sx, sy, f0 = geom['sx'], geom['sy'], geom['f0']
    out = {}
    for g, key in zip(F.GROUPS, ('red', 'white')):
        u0, v0, hc = geom[key]; c = g['c']
        def loss(z):
            err = 0.0
            ps = [dict(T0=0.1 * z[3*i] - 0.1 * i - 0.5 * c, dx=z[3*i+1], dy=z[3*i+2]) for i in range(nvis)]
            for fr, o in g['obs'].items():
                pts = []
                for p in ps:
                    ox, oy = F.offsets(p, fr - f0, hc); pts.append((u0 + sx * ox, v0 + sy * oy))
                err += float(((F.render(g, pts) - o) ** 2).sum())
            return err
        bounds = [(0, 1), (-30, 30), (15, 25)] * nvis
        r = differential_evolution(loss, bounds, seed=seed, maxiter=300, popsize=20, tol=1e-7, polish=True)
        z = r.x
        out[key] = [dict(r0=z[3*i], dx=z[3*i+1], dy=z[3*i+2]) for i in range(nvis)]
        print(key, round(r.fun, 1), [(round(m['r0'], 2), round(m['dx'], 1), round(m['dy'], 1)) for m in out[key]], flush=True)
    return out

def constraints(meas, tol_dx=4.5):
    """(draw offset from the dive's first draw, rand lo, rand hi) in units of rand/32768"""
    cons = []
    for key, c in (('red', 0), ('white', 3)):
        for i, m in enumerate(meas[key]):
            j = 200 * c + 4 * i
            r1 = abs(m['dx']) / 30
            cons.append((j + 1, max(0, r1 - tol_dx / 30), min(1, r1 + tol_dx / 30), 'dx'))
            cons.append((j + 2, 0.5, 1.0, 'sign') if m['dx'] < 0 else (j + 2, 0.0, 0.5, 'sign'))
    return cons

def lattice_search(cons, use=('dx',), max_dim=10):
    cs = sorted([k for k in cons if k[3] in use], key=lambda k: k[2] - k[1])[:max_dim]
    jp, plo, phi, _ = cs[0]
    lo = [int(plo * 32768) * UNIT]; hi = [min(32768, math.ceil(phi * 32768)) * UNIT - 1]
    gens = [[1]]; others = cs[1:]
    for (j, l, h, _) in others:
        a, c = rng.jump(j - jp); a %= M; c %= M
        gens[0].append(a)
        lo.append(int(l * 32768) * UNIT - c); hi.append(min(32768, math.ceil(h * 32768)) * UNIT - 1 - c)
    for t in range(len(others)):
        row = [0] * (len(others) + 1); row[t + 1] = M; gens.append(row)
    pts = box_points(gens, lo, hi, max_nodes=20_000_000)
    if pts is None: return None
    # back to the dive's first state (the state whose value is draw 0)
    return sorted({rng.next_seed(p[0] % M, -jp) % M for p in pts})

def check(state, cons):
    bad = 0
    for (j, l, h, _) in cons:
        s = rng.next_seed(state, j) % M; r = ((s >> 16) & 0x7fff) / 32768
        bad += not (l <= r <= h)
    return bad

if __name__ == "__main__":
    # usage: python divemeasure.py '{"sx":..,"sy":..,"f0":..,"red":[u0,v0,climb],"white":[u0,v0,climb]}'
    # geometry is calibrated once per video layout (divefit2 on a dive whose seed is known)
    geom = json.loads(sys.argv[1])
    meas = measure(geom)
    cons = constraints(meas)
    cands = [s for s in (lattice_search(cons) or []) if check(s, cons) == 0]
    th = [geom['sx'], geom['sy'], *geom['red'], *geom['white']]
    from divesim import dive_params
    ranked = sorted((F.loss(th, dive_params(s), 5, geom['f0']), s) for s in cands)
    for l, s in ranked:
        print(hex(s), round(l, 1), "layout seed", hex(rng.next_seed(s, 999)))
