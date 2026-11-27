"""Python's own per-entry result (before chain.py's cross-entry pass) for the entries where p2live
differs from seeds.json, so the port is compared like for like.

    python p2live/scripts/python_per_entry.py PARITY_DIR MAIN_CHECKOUT [--jobs N]

Reads PARITY_DIR/*.jsonl (p2live entries output), re-runs analyze_event the way p2live does
(detect around the frame, the nearest event, the result settled nearest the frame, the Pay Off
Debt rescue) and writes PARITY_DIR/python_per_entry.jsonl. Run it with the p2seeds environment.
"""
import json
import os
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path


def one(task):
    main, run, seeds, frame, want = task
    sys.path.insert(0, str(Path(main) / "p2seeds" / "src"))
    from p2seeds.story import analyze, events
    from p2seeds.video import Video
    m = json.load(open(seeds))["meta"]
    with Video(os.path.join(main, m["video"])) as v:
        feed = analyze.Feed(*m["feed"])
        evs = events.detect(v, feed, step=10, start=max(0, frame - 450), stop=frame + 150)
        ev = min(evs, key=lambda e: abs(e.last - frame)) if evs else events.Event(frame, frame, 0)
        res = analyze.analyze_event(v, feed, ev)
        r = min(res, key=lambda r: abs((r.settled_frame or 0) - frame))
        if r.cave_id is None and want in analyze.POD_CAVES:
            near = getattr(r, "near", []) or []
            if any(c == want and sc >= analyze.RESCUE_SCORE and mg >= analyze.RESCUE_MARGIN for c, sc, mg in near):
                res2 = analyze.analyze_event(v, feed, ev, only=want)
                r2 = min(res2, key=lambda r: abs((r.settled_frame or 0) - frame)) if res2 else None
                if r2 is not None and r2.cave_id is not None:
                    r = r2
    seed = None if r.letter_seed is None else f"0x{r.letter_seed:08X}"
    return {"run": run, "frame": frame, "py_seed": seed, "py_confidence": r.confidence,
            "py_sublevel": r.digit_value, "py_votes": {str(k): v for k, v in r.digit_votes.items()},
            "py_note": r.note}


def main():
    out_dir, main_dir = Path(sys.argv[1]), sys.argv[2]
    jobs = int(sys.argv[sys.argv.index("--jobs") + 1]) if "--jobs" in sys.argv else 4
    seeds_of = {}
    for sub in ("output", "output_at"):
        for s in Path(main_dir, "data", sub).glob("*/seeds.json"):
            seeds_of[s.parent.name] = s
    tasks = []
    for p in sorted(out_dir.glob("*.jsonl")):
        if p.name == "python_per_entry.jsonl":
            continue
        for line in p.read_text().splitlines():
            r = json.loads(line)
            if r["note"] == "no frames decoded":   # video not on disk
                continue
            if not r["same"] or r["sublevel"] != r["expected_sublevel"]:
                tasks.append((main_dir, r["run"], str(seeds_of[r["run"]]), r["frame"], r["expected_cave"]))
    print(f"{len(tasks)} entries", flush=True)
    with open(out_dir / "python_per_entry.jsonl", "w") as f, ProcessPoolExecutor(jobs) as ex:
        for row in ex.map(one, tasks):
            f.write(json.dumps(row) + "\n")
            f.flush()


if __name__ == "__main__":
    main()
