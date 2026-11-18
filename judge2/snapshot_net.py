"""Snapshot every high-confidence Pay Off Debt play, with creature pokos, into judge2/data/plays_net.json.

The net-timesave outcome (p2seeds.site.calibration, POKOS_PER_SECOND = 2):
    cost = seconds from this sublevel's entry screen to the next one's - total pokos / 2
total pokos = treasure pokos + creature ("bug") pokos, as treasures.reliable_pokos() gives
them (None when more than 30 creature pokos had to be clipped: no outcome then).

  python judge2/snapshot_net.py [path to the main checkout's data/output]

Run once; afterwards everything works from the snapshot (other sessions keep re-processing runs).
Fields per play: run, runner, sub, layout_seed, judge (CaveGen's pod score), judge2 (the
judge2 shipped before this snapshot), took, treasure_pokos, bug_pokos, bug_clipped, pokos
(reliable total), creature_cap, cost (net), plus frame/link for looking a play up.
"""
import json, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "data" / "output"
sys.path.insert(0, str(ROOT / "p2seeds" / "src"))
from p2seeds import judge_report, treasures  # noqa: E402

plays = []
for jf in sorted(OUT.glob("*/judge.json")):
    d = jf.parent
    j = json.loads(jf.read_text(encoding="utf-8"))
    if j.get("kind", "pod") != "pod":
        continue
    meta = j["meta"]; run = meta.get("run", {})
    fps = meta.get("fps", 30.0)
    tre = json.loads((d / "treasures.json").read_text(encoding="utf-8")) if (d / "treasures.json").exists() else {}
    e = j["entries"]
    for a, b in zip(e, e[1:]):
        if not (a["cave"] == b["cave"] and a.get("sublevel") and b.get("sublevel") == a["sublevel"] + 1):
            continue
        if not judge_report.trusted(a) or "judge_score" not in a:
            continue
        t = tre.get(str(a["frame"]))
        took = (b["frame"] - a["frame"]) / fps
        pokos = treasures.reliable_pokos(t)
        plays.append({
            "run": d.name, "runner": ", ".join(p["name"] for p in run.get("players", [])) or d.name,
            "cave": a["cave"], "sublevel": a["sublevel"], "sub": f'{a["cave"]}-{a["sublevel"]}',
            "frame": a["frame"], "next_frame": b["frame"], "fps": fps, "link": a.get("link"), "time": a.get("time"),
            "layout_seed": a.get("layout_seed"), "next_confidence": b.get("confidence"),
            "judge": a["judge_score"], "judge_fixed": a.get("judge_fixed"),
            "judge2": a.get("judge2_score"), "judge2_fixed": a.get("judge2_fixed"),
            "took": took,
            "treasure_pokos": t.get("treasure_pokos") if t else None,
            "bug_pokos": t.get("bug_pokos") if t else None,
            "bug_clipped": t.get("bug_clipped") if t else None,
            "creature_cap": t.get("creature_cap") if t else None,
            "pokos": pokos,
            "cost": took - pokos / 2.0 if pokos is not None else None,
            "treasures": t.get("treasures") if t else None,
            "collected": t.get("collected") if t else None, "items": t.get("items") if t else None,
            "inferred": t.get("inferred") if t else None,
        })
(ROOT / "judge2" / "data" / "plays_net.json").write_text(json.dumps(
    {"created": time.strftime("%Y-%m-%d %H:%M:%S"), "source": str(OUT) + "/*/judge.json + treasures.json",
     "plays": plays}, indent=1), encoding="utf-8")
print(len(plays), "plays,", len({p["run"] for p in plays}), "runs,",
      sum(p["cost"] is None for p in plays), "without reliable pokos,",
      sum(bool(p["judge_fixed"]) for p in plays), "fixed layouts")
