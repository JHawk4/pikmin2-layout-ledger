"""All Treasures plays for fitting at2: one row per high-confidence floor with its time and
CaveGen's at parts (judge2.exe, Japanese treasure weights).

    python judge2/at_snapshot.py RUN_DIR [RUN_DIR ...]  -> judge2/data/at_plays.json

A RUN_DIR holds judge.json or seeds.json (entries with frame, cave, sublevel, layout_seed,
confidence) and its meta (fps, players). A floor's time runs from its entry screen to the
next floor's entry screen in the same cave; a cave's last floor is left out (no results
screen is read for All Treasures yet). When a run enters a cave more than once (the Bulblax
Kingdom purple farm: down a few floors, out, and in again), only the last visit counts.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXE = HERE.parent / "data" / "build" / "judge2" / "release" / "judge2.exe"


def last_visits(E: list[dict]) -> list[dict]:
    """Drop every visit to a cave but the last. A visit ends where the cave changes or the
    sublevel stops going up."""
    visits: list[list[dict]] = []
    for e in E:
        v = visits[-1] if visits else None
        if v and v[-1]["cave"] == e["cave"] and e["sublevel"] > v[-1]["sublevel"]:
            v.append(e)
        else:
            visits.append([e])
    last = {v[0]["cave"]: k for k, v in enumerate(visits)}
    return [e for k, v in enumerate(visits) if last[v[0]["cave"]] == k for e in v]


def plays(run_dir: Path) -> list[dict]:
    f = run_dir / "judge.json" if (run_dir / "judge.json").exists() else run_dir / "seeds.json"
    d = json.loads(f.read_text(encoding="utf-8"))
    meta = d.get("meta", {})
    fps = meta.get("fps") or 30.0
    players = (meta.get("run") or {}).get("players") or []
    runner = players[0]["name"] if players else run_dir.name.split("_", 1)[1].rsplit("_", 1)[0]
    E = last_visits([e for e in d["entries"] if e.get("cave") and e.get("sublevel")])
    out = []
    for a, b in zip(E, E[1:]):
        if a.get("confidence") != "high" or not a.get("layout_seed"):
            continue
        if b["cave"] != a["cave"] or b["sublevel"] != a["sublevel"] + 1:
            continue
        out.append({"run": run_dir.name, "runner": runner, "sub": f"{a['cave']}-{a['sublevel']}",
                    "seed": a["layout_seed"], "frame": a["frame"], "took": (b["frame"] - a["frame"]) / fps,
                    "link": a.get("link")})
    return out


def main(dirs: list[str]) -> None:
    rows = [p for d in dirs for p in plays(Path(d))]
    reqs = "".join(json.dumps({"sub": r["sub"], "seed": r["seed"], "judge": "at", "region": "jpn"}) + "\n" for r in rows)
    ans = subprocess.run([str(EXE)], input=reqs, capture_output=True, text=True, check=True).stdout.splitlines()
    for r, a in zip(rows, ans):
        a = json.loads(a)
        r["old"] = a["old"]
        r.update(a["at2_parts"]["raw"])
    out = HERE / "data" / "at_plays.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(rows, indent=0), encoding="utf-8")
    print(f"{len(rows)} plays from {len(dirs)} runs -> {out}")


if __name__ == "__main__":
    main(sys.argv[1:])
