"""Known floor-1 seeds of every stage in the CMAL runs: consecutive decoded results rolls,
floor 1 = previous roll's end + 1004 draws (no menu flash), stage from stage_rates.json (matched
by the draw count to the next roll).

    python docs/layout_matcher/known_seeds.py > data/lm/known_seeds.json
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lm  # noqa: E402

CH = os.path.join(lm.ROOT, "..", "judge2-net-timesave-304bfd", "data", "challenge")


def main():
    R = json.load(open(os.path.join(CH, "results_rolls.json")))
    rates = json.load(open(os.path.join(CH, "stage_rates.json")))
    out = []
    for s in rates:
        rr = R.get(s["video"])
        if rr is None:
            continue
        rr = [r for r in (rr["results"] if isinstance(rr, dict) else rr) if r.get("decoded")]
        for p, n in zip(rr, rr[1:]):
            lay = lm.rng.next_seed(int(p["state_after_last_draw"], 16), 1004)
            d = lm.rng.distance(lay, int(n["first_roll_state"], 16), limit=1 << 21)
            if d == s["draws"]:
                out.append(dict(video=s["video"], ch=s["ch"], seed=f"{lay & 0x7FFFFFFF:08X}", prev_roll_last=p["last_frame"],
                                next_roll=n["first_frame"], next_state=n["first_roll_state"], draws=d))
                break
    out.sort(key=lambda e: (e["ch"], e["video"]))
    json.dump(out, sys.stdout, indent=1)


if __name__ == "__main__":
    main()
