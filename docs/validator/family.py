"""Family check: how close are the layouts of seeds a few draws away from a proposed seed?

A seed's "family" is the seeds +-N draws away whose layouts share most objects with it. A proposal
is only verified if the video separates it from every family member, so this lists, per neighbour,
the share of objects at the same place, and the objects that differ (what to look for in the video).

    python docs/validator/family.py SUB SEED [N=12] [--diff K]

Needs P2SEEDS_LAYOUTMATCH (layoutmatch.exe from docs/layout_matcher/build.sh).
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "layout_matcher"))
import lm  # noqa: E402
from p2seeds import rng  # noqa: E402

TOL = 40.0


def key(o):
    return (o["kind"], o["names"][0])


def same(a, b):
    # pod frame, so layouts whose pod sits elsewhere on the map still compare as seen on screen
    return key(a) == key(b) and abs(a["ahead"] - b["ahead"]) < TOL and abs(a["side"] - b["side"]) < TOL


def compare(la, lb):
    """(share of la's objects found in lb, objects only in la, objects only in lb, units equal)."""
    oa, ob = la["objects"], lb["objects"]
    only_a = [o for o in oa if not any(same(o, p) for p in ob)]
    only_b = [o for o in ob if not any(same(o, p) for p in oa)]
    units = [(u.get("name"), u.get("x"), u.get("z"), u.get("rot")) for u in la["units"]] == \
            [(u.get("name"), u.get("x"), u.get("z"), u.get("rot")) for u in lb["units"]]
    return 1 - len(only_a) / max(1, len(oa)), only_a, only_b, units


def fmt(o):
    return f"{o['kind']}:{'/'.join(o['names'])}@({o['ahead']:.0f},{o['side']:.0f})"


def main():
    sub, seed = sys.argv[1], int(sys.argv[2], 16)
    n = int(sys.argv[3]) if len(sys.argv) > 3 and not sys.argv[3].startswith("--") else 12
    diff = int(sys.argv[sys.argv.index("--diff") + 1]) if "--diff" in sys.argv else None
    seeds = [rng.next_seed(seed, d) if d >= 0 else rng.prev_seed(seed, -d) for d in range(-n, n + 1)]
    lays = lm.dump(sub, *seeds)
    base = lays[n]
    print(f"{sub} {seed:08X}: {len(base['objects'])} objects, {len(base['units'])} units, pod {base['pod']}")
    for i, d in enumerate(range(-n, n + 1)):
        if d == 0:
            continue
        share, oa, ob, units = compare(base, lays[i])
        flag = "  <-- family" if share > 0.5 else ""
        print(f"  {d:+3d} {seeds[i] & 0xFFFFFFFF:08X} same={share:5.0%} units_same={units} "
              f"differ={len(oa)}/{len(ob)}{flag}")
        if diff is not None and d == diff or (diff is None and share > 0.5):
            for o in oa:
                print("       truth only:", fmt(o))
            for o in ob:
                print("       nbr   only:", fmt(o))


if __name__ == "__main__":
    main()
