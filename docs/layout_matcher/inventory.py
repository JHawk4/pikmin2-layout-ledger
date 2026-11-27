"""Inventory of the Challenge Mode score WRs for the layout matcher: floors, the decoded results
roll after the dive (window end), frames dive -> roll, and how varied the pod's start is on floor 1.

    python docs/layout_matcher/inventory.py > data/lm/inventory.json
"""
import collections
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lm  # noqa: E402

WR = os.path.join(lm.ROOT, "..", "judge2-net-timesave-304bfd", "data", "challenge", "wr")
WR = os.environ.get("P2SEEDS_WR", WR)
CSV = r"C:/Users/Jordan/Desktop/Claude/cavegen3/data/resources/jhawk_judge/challenge_stages.csv"


def floors():
    out = {}
    for line in open(CSV):
        if line.startswith("#") or not line.strip():
            continue
        f = line.strip().split(",")
        ch = int(f[0][2:])
        n = int(f[24])
        out[ch] = n
    return out


def main():
    fl = floors()
    visits = json.load(open(os.path.join(WR, "visits.json")))
    res = []
    for name, info in sorted(visits.items(), key=lambda kv: kv[1]["ch"]):
        ch = info["ch"]
        good = [v for v in info["visits"] if v["reg"] >= 0.45]
        dive = next((v for v in good if v["landing"] == ch), None)
        rp = os.path.join(WR, "rolls", os.path.splitext(name)[0] + ".json")
        roll = None
        if os.path.exists(rp):
            d = json.load(open(rp))
            d = d["results"] if isinstance(d, dict) else d
            after = [r for r in d if r.get("decoded") and (dive is None or r["first_frame"] > dive["visit"][1])]
            before = [r for r in d if r.get("decoded") and dive is not None and r["last_frame"] < dive["visit"][0]]
            roll = after[0] if after else None
            prev = before[-1] if before else None
        else:
            prev = None
        sample = lm.dump(f"CH{ch}-1", *[(i * 0x9E3779B1) & 0xFFFFFFFF for i in range(300)])
        starts = collections.Counter((d["pod"]["unit_name"], d["pod"]["unit_spawn"]) for d in sample if "pod" in d)
        e = dict(ch=ch, video=name, floors=fl.get(ch), dive=dive and dive["visit"],
                 roll_frame=roll and roll["first_frame"], roll_state=roll and (roll.get("first_roll_state") or roll["anchor_state"]),
                 prev_roll_end=prev and prev["state_after_last_draw"],
                 frames=(roll["first_frame"] - dive["visit"][1]) if roll and dive else None,
                 pod_starts=len(starts), top_start=starts.most_common(1)[0])
        res.append(e)
        print(json.dumps(e), file=sys.stderr, flush=True)
    json.dump(res, sys.stdout, indent=1)


if __name__ == "__main__":
    main()
