"""Re-run a finished run's sublevels that are not high confidence with the current detector.

A new result replaces the old one only when it is high confidence and its letter seed chains
with a neighbouring high seed (consecutive sublevels' seeds sit within STEP_LIMIT generator
steps of each other, which almost never happens by chance). seeds.json is rewritten (the old
one is kept as seeds.before_redo.json) and the changed sublevels' pictures are dropped so the
detection page redraws them. Judging and poko counts are left to `judge` and `treasures`.

On Wii U captures it also looks for titles cut to black before the cave name landed
(route_rescue) and adds the ones whose seed chains with a neighbour.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from . import analyze, rng
from .events import Event, is_wide
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
    if is_wide(feed):
        added = _rescue(video, feed, data, STEP_LIMIT, progress)
        changed += added
        es = data["entries"]
    if changed:
        shutil.copy2(path, out / "seeds.before_redo.json")
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        for f in changed:
            for p in [out / "img" / f"fall_{f}.jpg", out / "img" / f"layout_views_{f}.jpg"]:
                p.unlink(missing_ok=True)
    return changed


def _rescue(video, feed, data: dict, limit: int, progress=None) -> list[int]:
    """Add the route rescue's titles to data["entries"] (replacing a seedless entry it stands for)
    when the letter seed chains with a neighbouring high one, the rescued ones included."""
    import re

    from . import report, route_rescue
    from .analyze import EventResult
    es = data["entries"]
    stand = [EventResult(Event(e["frame"], e["frame"], 1), settled_frame=e["frame"], cave_id=e["cave"],
                         sublevel=e.get("sublevel"), confidence=e["confidence"], lang=e.get("lang") or "en",
                         layout_seed=int(e["layout_seed"], 16) if e.get("layout_seed") else None)
             for e in es if e.get("cave") and e.get("frame")]
    extra = [r for r in route_rescue.rescue(video, feed, stand, log=lambda m: progress and progress(None, m, False))
             if r.letter_seed is not None and r.confidence in ("high", "medium")]
    anchors = {e["frame"]: int(e["letter_seed"], 16) for e in es if e["confidence"] == "high" and e.get("letter_seed")}
    kept: list = []
    grew = True
    while grew:                      # a run of rescued sublevels confirms itself from either end
        grew = False
        for r in extra:
            if r in kept:
                continue
            before = [f for f in anchors if f < r.settled_frame]
            after = [f for f in anchors if f > r.settled_frame]
            ok = ((before and rng.distance(anchors[max(before)], r.letter_seed, limit=limit) is not None)
                  or (after and rng.distance(r.letter_seed, anchors[min(after)], limit=limit) is not None))
            if ok:
                kept.append(r)
                anchors[r.settled_frame] = r.letter_seed
                grew = True
    for r in extra:
        if progress:
            progress({"cave": r.cave_id, "sublevel": r.sublevel, "confidence": "missing"}, r, r in kept)
    if not kept:
        return []
    link = next((e["link"] for e in es if e.get("link")), None)
    url = re.sub(r"[?&]t=\d+s?$", "", link) if link else None
    for r in kept:
        r.confidence = "high"
        if r.sublevel is None:
            r.sublevel, r.sublevel_source = r.digit_value, "digit"
        r.note = ", ".join(x for x in (r.note, "seed confirmed by its neighbour") if x)
    rows = report.rows(kept, data["meta"].get("fps") or video.fps, url)
    near = route_rescue.NEAR
    data["entries"] = sorted([e for e in es if e.get("layout_seed") or not any(abs(e["frame"] - r.settled_frame) < near for r in kept)]
                             + rows, key=lambda e: e["frame"])
    return [r.settled_frame for r in kept]
