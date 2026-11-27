"""Filter a seed window by observations read off the video, and report how much each one cuts.

    python docs/layout_matcher/match.py SUB END_STATE K_LO K_HI OBS.json OUT_PREFIX [TRUTH_SEED]

Seeds are END_STATE stepped back k draws, k in [K_LO, K_HI) (END_STATE: the first state of the
stage's results roll). OBS.json: a list of layoutmatch observations (see layoutmatch.rs), each
optionally with "label". Prints, observation by observation, the share of the window passing it
alone and the survivors of all observations so far; then the survivors (k, seed) when few.
With TRUTH_SEED, also which observations the truth passes.
"""

import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lm  # noqa: E402


def main():
    sub, end, lo, hi, obs_path, prefix = sys.argv[1:7]
    end, lo, hi = int(end, 16), int(lo), int(hi)
    truth = int(sys.argv[7], 16) & 0x7FFFFFFF if len(sys.argv) > 7 else None
    obs = json.load(open(obs_path))
    seeds_end = lm.seed_at(end, lo)
    bits = lm.scan(sub, seeds_end, hi - lo, [{k: v for k, v in o.items() if k != "label"} for o in obs],
                   prefix + ".bin")
    n = len(bits)
    alive = np.ones(n, bool)
    tk = None
    if truth is not None:
        # the truth's k: draws from it to the window's last seed (bit 31 is not part of the seed)
        for t in (truth, truth | 0x80000000):
            d = lm.rng.distance(t, seeds_end, limit=1 << 26)
            if d is not None and d < n:
                tk = d
                break
    print(f"window: {n} seeds (k {lo}..{hi}); truth at k = {None if tk is None else lo + tk}")
    rows = []
    for j, o in enumerate(obs):
        ok = (bits >> j) & 1 == 1
        alive &= ok
        t = None if tk is None else bool(ok[tk])
        rows.append(dict(label=o.get("label", str(j)), alone=float(ok.mean()), survivors=int(alive.sum()), truth=t))
        print(f"  {o.get('label', j):40s} passes {ok.mean():7.2%}  survivors {alive.sum():9d}  truth {t}")
    surv = np.nonzero(alive)[0]
    out = [dict(k=int(lo + i), seed=f"{lm.seed_at(seeds_end, int(i)) & 0x7FFFFFFF:08X}") for i in surv[:200]]
    if len(surv) <= 50:
        for e in out:
            print("   ", e)
    json.dump(dict(window=[lo, hi], truth_k=None if tk is None else lo + tk, steps=rows, survivors=out,
                   n_survivors=int(len(surv))), open(prefix + ".json", "w"), indent=1)


if __name__ == "__main__":
    main()
