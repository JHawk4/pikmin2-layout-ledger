"""How much a challenge sublevel's layout varies between seeds.

Dumps N random seeds with layoutmatch and reports, in bits, the entropy of the whole
layout signature (pod spawn + every object's kind and position, rounded), and per object kind.
Positions are in the pod's frame (ahead, side), rounded to 50 units. A floor with only a few bits (a lone boss in a fixed room) can't be pinned from video.

usage: python variation.py SUB [SUB ...] [--n 2000]
"""
import argparse, collections, json, math, os, random, subprocess

LM = os.environ.get("P2SEEDS_LAYOUTMATCH", r"C:\Users\Jordan\Desktop\Claude\p2-vod-seeds\.claude\worktrees\wii-digits-728a39\data\build\cg3lm\release\layoutmatch.exe")


def dump(sub, seeds):
    out = []
    for i in range(0, len(seeds), 200):
        chunk = seeds[i:i + 200]
        r = subprocess.run([LM, "dump", sub, *[f"{s:08X}" for s in chunk]], capture_output=True, text=True, check=True)
        for line in r.stdout.splitlines():
            line = line.strip()
            if line.startswith("{"):
                out.append(json.loads(line))
    return out


def entropy(counter):
    n = sum(counter.values())
    return -sum(c / n * math.log2(c / n) for c in counter.values())


def sig(objs, grid=20):
    return tuple(sorted((o["kind"], "/".join(o["names"]), round(o["ahead"] / grid), round(o["side"] / grid)) for o in objs))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("subs", nargs="+")
    ap.add_argument("--n", type=int, default=2000)
    a = ap.parse_args()
    rng = random.Random(1)
    seeds = [rng.getrandbits(31) for _ in range(a.n)]
    for sub in a.subs:
        lays = dump(sub, seeds)
        full = collections.Counter()
        units = collections.Counter()
        per = collections.defaultdict(collections.Counter)
        for L in lays:
            units[tuple((u["name"], u["x"], u["z"], u["rotation"]) for u in L["units"])] += 1
            full[(L["pod"]["unit_name"], L["pod"]["unit_spawn"], sig(L["objects"], 50))] += 1
            byname = collections.defaultdict(list)
            for o in L["objects"]:
                byname["/".join(o["names"])].append((round(o["ahead"] / 50), round(o["side"] / 50)))
            for k, v in byname.items():
                per[k][tuple(sorted(v))] += 1
        print(f"{sub}: {len(lays)} layouts, distinct full={len(full)} ({entropy(full):.1f} bits), unit layouts={len(units)} ({entropy(units):.1f} bits)")
        for k, c in sorted(per.items(), key=lambda kv: -entropy(kv[1])):
            print(f"    {k:40s} {entropy(c):5.1f} bits  ({len(c)} distinct)")


if __name__ == "__main__":
    main()
