"""Rotation/scale sweep of the fast layoutmatch scan, for gameplay frames whose camera turn is unknown.

    python docs/layout_matcher/gameplay/rotscan.py SUB END_HEX COUNT PTS.json OUT.json
        [--rot-step 10] [--scales 0.8,1.0,1.2] [--tol 0.18] [--need N]

PTS.json as for simfit, with exactly one "pod" point. For every camera turn and scale the other marks become pod-frame
(side, ahead) observations with tolerance --tol x distance (min 60 units); layoutmatch scans COUNT draws before END.
Keeps every seed passing >= --need marks (default all) under some turn/scale, then rank them with simfit --seeds.
"""
import argparse, json, math, os, sys, tempfile
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..")); sys.path.insert(0, os.path.join(HERE, "..", "..", "..", "p2seeds", "src"))
import lm  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("sub"); ap.add_argument("end"); ap.add_argument("count", type=int); ap.add_argument("pts"); ap.add_argument("out")
ap.add_argument("--rot-step", type=float, default=10); ap.add_argument("--scales", default="0.8,1.0,1.2")
ap.add_argument("--tol", type=float, default=0.18); ap.add_argument("--need", type=int)
a = ap.parse_args()
pts = json.load(open(a.pts))["points"]
pod = [p for p in pts if p["names"] == ["pod"]][0]["px"]
marks = [p for p in pts if p["names"] != ["pod"]]
need = a.need or len(marks)
end = int(a.end, 16)
hits = {}
tmp = tempfile.mkdtemp()
for s in [float(v) for v in a.scales.split(",")]:
    for rd in np.arange(0, 360, a.rot_step):
        th = math.radians(rd)
        obs = []
        for p in marks:
            dx, dy = (p["px"][0] - pod[0]) / s, (p["px"][1] - pod[1]) / s
            # pixel = Rot(th) (side, -ahead)  ->  (side, -ahead) = Rot(-th) pixel
            side = math.cos(th) * dx + math.sin(th) * dy
            mahead = -math.sin(th) * dx + math.cos(th) * dy
            dist = math.hypot(dx, dy)
            obs.append(dict(label=p.get("label", ""), names=p["names"], side=round(side), ahead=round(-mahead),
                            tol=round(max(60, a.tol * dist + 40 / s))))
        m = lm.scan(a.sub, end, a.count, obs, os.path.join(tmp, "m.bin"))
        cnt = np.zeros(len(m), int)
        for j in range(len(obs)):
            cnt += (m >> j) & 1
        ks = np.nonzero(cnt >= need)[0]
        for k in ks:
            k = int(k)
            if k not in hits or hits[k][0] < cnt[k]:
                hits[k] = (int(cnt[k]), s, float(rd))
        print(f"scale {s} rot {rd:5.1f}: {len(ks)} seeds >= {need}/{len(obs)} (total {len(hits)})", flush=True)
json.dump([dict(k=k, seed=f"{lm.seed_at(end, k) & 0x7FFFFFFF:08X}", n=v[0], scale=v[1], rot=v[2])
           for k, v in sorted(hits.items())], open(a.out, "w"), indent=0)
print(len(hits), "seeds ->", a.out)
