"""Where a sublevel's objects can be, in the pod's frame: sample many seeds and count the distinct
(ahead, side) spots per object kind. For single-room stages, where the pod's room is fixed, each
treasure has only a few spots, so reading which treasure sits at which spot pins the seed.

    python docs/layout_matcher/spots.py SUB [N] [KINDS]   (KINDS: comma list, default item,hole)

Prints the spots (rounded to 10 units), how often each is used, and what uses it; writes
data/lm/spots_SUB.json.
"""
import collections
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lm  # noqa: E402


def main():
    sub = sys.argv[1]
    n = int(sys.argv[2]) if len(sys.argv) > 2 else 2000
    kinds = (sys.argv[3] if len(sys.argv) > 3 else "item,hole").split(",")
    seeds = [(i * 0x9E3779B1 + 12345) & 0xFFFFFFFF for i in range(n)]
    spots = collections.defaultdict(collections.Counter)
    for i in range(0, n, 250):
        for d in lm.dump(sub, *seeds[i:i + 250]):
            for o in d["objects"]:
                if o["kind"] in kinds:
                    key = (round(o["ahead"] / 10) * 10, round(o["side"] / 10) * 10)
                    spots[key][o["names"][-1] if o["kind"] != "item" else o["names"][0]] += 1
    out = []
    for (a, s), c in sorted(spots.items(), key=lambda kv: -sum(kv[1].values())):
        out.append(dict(ahead=a, side=s, n=sum(c.values()), what=dict(c.most_common())))
        print(f"ahead {a:6d} side {s:6d}  n {sum(c.values()):5d}  {dict(c.most_common(6))}")
    os.makedirs(os.path.join(lm.ROOT, "data", "lm"), exist_ok=True)
    json.dump(out, open(os.path.join(lm.ROOT, "data", "lm", f"spots_{sub}.json"), "w"), indent=1)


if __name__ == "__main__":
    main()
