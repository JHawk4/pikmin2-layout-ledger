"""Fixed out-of-sample split, by whole runner (all of a runner's runs go to the same side).

Why runner, not run: several runners have 3-6 runs (JackDraz, iid01, IceCube, Kap,
theurbandear). Their routing habits (which treasure they skip, how they handle a gate) are
exactly what the judge would be tuned to, so splitting a runner across sides would leak.
Runners are shuffled with a fixed seed and walked in that order; each is put in OOS if it keeps
the OOS share <= 33% of the usable plays, stopping once it reaches 27%."""
import json, random
from collections import Counter
from pathlib import Path

SEED = 20261115
D = Path(__file__).resolve().parent / "data"
plays = [p for p in json.loads((D / "plays.json").read_text(encoding="utf-8"))["plays"] if not p["judge_fixed"]]
n_by = Counter(p["runner"] for p in plays)
runners = sorted(n_by)
random.Random(SEED).shuffle(runners)
oos, tot = [], 0
for r in runners:
    if tot >= 0.27 * len(plays):
        break
    if tot + n_by[r] <= 0.33 * len(plays):
        oos.append(r); tot += n_by[r]
ins = sorted(set(runners) - set(oos))
runs = sorted({(p["runner"], p["run"]) for p in plays})
split = {"rng_seed": SEED, "unit": "runner", "target_oos_fraction": 0.30,
         "oos_runners": sorted(oos), "in_sample_runners": ins,
         "oos_runs": sorted(r for who, r in runs if who in oos),
         "in_sample_runs": sorted(r for who, r in runs if who not in oos),
         "oos_plays": tot, "in_sample_plays": len(plays) - tot, "plays_by_runner": dict(n_by)}
(D / "split.json").write_text(json.dumps(split, indent=1), encoding="utf-8")
print(json.dumps({k: split[k] for k in ("oos_runners", "oos_plays", "in_sample_plays")}))
