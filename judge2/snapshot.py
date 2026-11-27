"""Snapshot every high-confidence Pay Off Debt play into judge2/data/plays.json.

A play = one runner on one sublevel that is followed by the next sublevel of the same cave
(the last sublevel of a cave has no end screen to measure against). Mirrors
p2seeds.ledger.site.calibration(): only `a` (the entry played) must be trusted; took is the gap
between the two entry screens; cost = took - pokos / 2.
Run once; afterwards everything works from the snapshot (other sessions re-process runs).
"""
import json, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "output"

plays = []
for jf in sorted(OUT.glob("*/judge.json")):
    d = jf.parent
    j = json.loads(jf.read_text(encoding="utf-8"))
    if j.get("kind", "pod") != "pod":
        continue
    meta = j["meta"]; run = meta.get("run", {})
    fps = meta.get("fps", 30.0)
    tre = {}
    if (d / "treasures.json").exists():
        tre = json.loads((d / "treasures.json").read_text(encoding="utf-8"))
    e = j["entries"]
    for a, b in zip(e, e[1:]):
        if not (a["cave"] == b["cave"] and a.get("sublevel") and b.get("sublevel") == a["sublevel"] + 1):
            continue
        if a.get("confidence") != "high" or "judge_score" not in a:
            continue
        t = tre.get(str(a["frame"]))
        took = (b["frame"] - a["frame"]) / fps
        pokos = t.get("pokos") if t else None
        plays.append({
            "run": d.name, "run_id": run.get("id"), "runner": ", ".join(p["name"] for p in run.get("players", [])) or d.name,
            "run_time": run.get("time_seconds"), "date": run.get("date"),
            "cave": a["cave"], "sublevel": a["sublevel"], "sub": f'{a["cave"]}-{a["sublevel"]}',
            "frame": a["frame"], "next_frame": b["frame"], "fps": fps, "link": a.get("link"), "time": a.get("time"),
            "layout_seed": a.get("layout_seed"), "next_confidence": b.get("confidence"),
            "judge": a["judge_score"], "judge_median": a.get("judge_median"), "judge_fixed": a.get("judge_fixed"),
            "took": took, "pokos": pokos, "cost": took - pokos / 2.0 if pokos is not None else None,
            "treasures": t.get("treasures") if t else None,
            "collected": t.get("collected") if t else None, "items": t.get("items") if t else None,
        })
(ROOT / "judge2" / "data" / "plays.json").write_text(json.dumps(
    {"created": time.strftime("%Y-%m-%d %H:%M:%S"), "source": "data/output/*/judge.json + treasures.json", "plays": plays},
    indent=1), encoding="utf-8")
print(len(plays), "plays,", len({p["run"] for p in plays}), "runs,", sum(p["cost"] is None for p in plays), "without pokos,",
      sum(bool(p["judge_fixed"]) for p in plays), "fixed layouts")
