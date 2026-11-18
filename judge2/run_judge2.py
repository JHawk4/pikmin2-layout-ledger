"""Call the judge2 binary on every snapshot play (layout features only; no outcomes are read).

  python judge2/run_judge2.py        -> data/judged.json: {key: {old, pod2, parts, pod2_parts, layout}}
Key = run|frame. Checks the copied old judge reproduces judge.json's score.
"""
import json, subprocess, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXE = HERE.parent / "data" / "build" / "judge2" / "release" / "judge2.exe"


def judge_many(reqs: list[dict]) -> list[dict]:
    inp = "\n".join(json.dumps(r) for r in reqs) + "\n"
    out = subprocess.run([str(EXE)], input=inp, capture_output=True, text=True, check=True).stdout
    return [json.loads(l) for l in out.splitlines() if l.strip()]


def main():
    plays = json.loads((HERE / "data" / "plays_net.json").read_text(encoding="utf-8"))["plays"]
    reqs = [{"sub": p["sub"], "seed": p["layout_seed"], "dump": True} for p in plays]
    res = judge_many(reqs)
    out, bad = {}, 0
    for p, r in zip(plays, res):
        if "error" in r:
            print("error", p["sub"], p["layout_seed"], r["error"]); continue
        if abs(round(r["old"], 2) - p["judge"]) > 0.011:
            bad += 1; print("mismatch", p["run"], p["sub"], p["layout_seed"], r["old"], p["judge"])
        out[f'{p["run"]}|{p["frame"]}'] = r
    (HERE / "data" / "judged.json").write_text(json.dumps(out), encoding="utf-8")
    print(len(out), "judged,", bad, "old-score mismatches")


if __name__ == "__main__":
    main()
