"""Print each proposal (sublevel + seed) that has no verdict yet, once; then keep watching.

    python docs/validator/pending.py [--once] [--every 60]
"""
import json
import os
import sys
import time

HUNT = os.environ.get("CH_SEED_HUNT", r"C:\Users\Jordan\Desktop\Claude\ch-seed-hunt")


def load(name):
    out = []
    try:
        for ln in open(os.path.join(HUNT, name), encoding="utf-8"):
            ln = ln.strip()
            if ln:
                try:
                    out.append(json.loads(ln))
                except ValueError:
                    pass
    except OSError:
        pass
    return out


def main():
    every = int(sys.argv[sys.argv.index("--every") + 1]) if "--every" in sys.argv else 60
    shown = set()
    while True:
        done = {(v.get("sublevel"), str(v.get("seed", "")).upper()) for v in load("verdicts.jsonl")}
        for p in load("proposals.jsonl"):
            k = (p.get("sublevel"), str(p.get("seed", "")).upper())
            if k not in done and k not in shown:
                shown.add(k)
                print(f"PENDING {k[0]} {k[1]} post {p.get('post')} by {p.get('finder')}: {p.get('methods')}", flush=True)
        if "--once" in sys.argv:
            return
        time.sleep(every)


if __name__ == "__main__":
    main()
