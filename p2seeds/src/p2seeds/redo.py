"""Re-run a finished run's sublevels that are not high confidence with the current detector.

A new result replaces the old one only when it is high confidence and its letter seed chains
with a neighbouring high seed (consecutive sublevels' seeds sit within STEP_LIMIT generator
steps of each other, which almost never happens by chance). seeds.json is rewritten (the old
one is kept as seeds.before_redo.json) and the changed sublevels' pictures are dropped so the
detection page redraws them. Judging and poko counts are left to `judge` and `treasures`.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from . import analyze, rng
from .events import Event
from .feed import Feed
from .video import Video


def redo(out_dir: str | Path, progress=None) -> list[int]:
    from .site import STEP_LIMIT
    out = Path(out_dir)
    path = out / "seeds.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    es = data["entries"]
    video, feed = Video(data["meta"]["video"]), Feed(*data["meta"]["feed"])

    def high(j):
        return es[j]["confidence"] == "high" and es[j].get("letter_seed")

    changed = []
    for i, e in enumerate(es):
        if e["confidence"] == "high" or not e.get("cave"):
            continue
        rs = analyze.analyze_event(video, feed, Event(e["frame"], e["frame"], 1))
        r = next((x for x in rs if x.cave_id == e["cave"]), rs[0])
        ok = False
        if r.confidence == "high" and r.letter_seed is not None:
            prev = next((j for j in range(i - 1, -1, -1) if high(j)), None)
            nxt = next((j for j in range(i + 1, len(es)) if high(j)), None)
            ok = ((prev is not None and rng.distance(int(es[prev]["letter_seed"], 16), r.letter_seed, limit=STEP_LIMIT) is not None)
                  or (nxt is not None and rng.distance(r.letter_seed, int(es[nxt]["letter_seed"], 16), limit=STEP_LIMIT) is not None))
        if progress:
            progress(e, r, ok)
        if not ok:
            continue
        e.update({
            "letter_seed": f"0x{r.letter_seed:08X}", "layout_seed": f"0x{r.layout_seed:08X}", "confidence": "high",
            "letters_measured": int(sum(1 for x in r.fit.v if x == x)), "fit_rms_px": round(r.fit.rms_px, 3),
            "bias": round(r.candidates[0].bias, 3), "score": round(r.candidates[0].score, 2),
            "runner_up_score": round(r.candidates[1].score, 2) if len(r.candidates) > 1 else None,
            "note": ", ".join(x for x in (r.note, "redone with a newer detector, seed confirmed by its neighbour") if x)})
        changed.append(e["frame"])
    if changed:
        shutil.copy2(path, out / "seeds.before_redo.json")
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        for f in changed:
            for p in [out / "img" / f"fall_{f}.jpg", out / "img" / f"layout_views_{f}.jpg"]:
                p.unlink(missing_ok=True)
    return changed
