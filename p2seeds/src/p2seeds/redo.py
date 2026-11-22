"""Re-run a finished run's sublevels that are not high confidence with the current detector.

When the run has its pre-link state (fits.json), a newer per-entry read replaces the old one
there (unless it is less confident), and the whole run is linked again with `chain.link`, which
confirms a seed that sits a short RNG distance from its neighbours and drops a stray one. Without
it, a new result replaces the old one only when it is high confidence and its letter seed chains
with a neighbouring high seed (consecutive sublevels' seeds sit within STEP_LIMIT generator steps
of each other, which almost never happens by chance).

Updating only seeds.json is not enough: seeds.json is linked from fits.json, so a later relink
(or a chain re-tune) would bring back the old detector's read. That is how 08_CurtisDN kept two
wrong medium seeds (Hole of Beasts 2, Frontier Cavern 1) that the current detector reads high,
and how wr29_JackDraz's Glutton's Kitchen 4 kept a window match on 6 mistracked letters.

seeds.json is rewritten (the old one is kept as seeds.before_redo.json), fits.json too (kept as
fits.before_redo.json), and the changed sublevels' pictures are dropped so the detection page
redraws them. Judging and poko counts are left to `judge` and `treasures`.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from . import analyze, chain, rng
from .events import Event
from .feed import Feed
from .video import Video

REDONE = "redone with a newer detector"
_RANK = {"high": 3, "medium": 2, "low": 1}


def refresh(row: dict, r) -> bool:
    """Put a newer per-entry read `r` (an EventResult) into its fits.json `row`, keeping the row's
    frame, cave and sublevel. Not when it is less confident than the read already there."""
    if r.fit is None or _RANK.get(r.confidence, 0) < _RANK.get(row.get("confidence"), 0):
        return False
    new = chain.row(r)
    if new["letter_seed"] == row.get("letter_seed") and new["fit"] == row.get("fit"):
        return False
    for k in ("num_chars", "confidence", "letter_seed", "layout_seed", "fit", "candidates"):
        row[k] = new[k]
    row["note"] = ", ".join(x for x in (r.note, REDONE) if x)
    return True


def _todo(es, fits_by_frame) -> list[int]:
    """Entries to analyze again: every one whose own read (fits.json) or final seed is not high.
    A final high seed may rest on a weak own read that a window search matched (wr29_JackDraz's
    Glutton's Kitchen 4), and an earlier redo changed seeds.json only."""
    out = []
    for i, e in enumerate(es):
        row = fits_by_frame.get(e["frame"])
        if e.get("cave") and row is not None and (e["confidence"] != "high" or row.get("confidence") != "high"):
            out.append(i)
    return out


def _analyze(video, feed, e):
    rs = analyze.analyze_event(video, feed, Event(e["frame"], e["frame"], 1))
    return next((x for x in rs if x.cave_id == e["cave"]), rs[0])


def redo(out_dir: str | Path, progress=None) -> list[int]:
    out = Path(out_dir)
    path, fpath = out / "seeds.json", out / "fits.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    es = data["entries"]
    video, feed = Video(data["meta"]["video"]), Feed(*data["meta"]["feed"])
    old = {e["frame"]: e.get("letter_seed") for e in es}

    if fpath.exists():
        rows = json.loads(fpath.read_text(encoding="utf-8"))
        by_frame = {r["frame"]: r for r in rows}
        refreshed = []
        for i in _todo(es, by_frame):
            e = es[i]
            row = by_frame[e["frame"]]
            r = _analyze(video, feed, e)
            ok = refresh(row, r)
            if progress:
                progress(e, r, ok)
            if ok:
                refreshed.append((e, r))
        if not refreshed:
            return []
        shutil.copy2(fpath, out / "fits.before_redo.json")
        shutil.copy2(path, out / "seeds.before_redo.json")
        fpath.write_text(json.dumps(rows), encoding="utf-8")
        chain.relink_dir(out, data)          # writes seeds.json
        for e, r in refreshed:
            if e.get("letter_seed") == (None if r.letter_seed is None else f"0x{r.letter_seed:08X}"):
                _stats(e, r)
        path.write_text(json.dumps(data, indent=1), encoding="utf-8")
        changed = [e["frame"] for e in es if e.get("letter_seed") != old[e["frame"]]]
    else:
        changed = _redo_seeds_only(es, video, feed, progress)
        if changed:
            shutil.copy2(path, out / "seeds.before_redo.json")
            path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    for f in changed:
        for p in [out / "img" / f"fall_{f}.jpg", out / "img" / f"layout_views_{f}.jpg"]:
            p.unlink(missing_ok=True)
    return changed


def _stats(e, r) -> None:
    """The fit numbers seeds.json shows for an entry whose seed is the new read."""
    e.update({
        "letters_measured": int(sum(1 for x in r.fit.v if x == x)), "fit_rms_px": round(r.fit.rms_px, 3),
        "bias": round(r.candidates[0].bias, 3), "score": round(r.candidates[0].score, 2),
        "runner_up_score": round(r.candidates[1].score, 2) if len(r.candidates) > 1 else None})


def _redo_seeds_only(es, video, feed, progress) -> list[int]:
    from .site import STEP_LIMIT

    def high(j):
        return es[j]["confidence"] == "high" and es[j].get("letter_seed")

    changed = []
    for i, e in enumerate(es):
        if e["confidence"] == "high" or not e.get("cave"):
            continue
        r = _analyze(video, feed, e)
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
        e.update({"letter_seed": f"0x{r.letter_seed:08X}", "layout_seed": f"0x{r.layout_seed:08X}", "confidence": "high",
                  "note": ", ".join(x for x in (r.note, REDONE + ", seed confirmed by its neighbour") if x)})
        _stats(e, r)
        changed.append(e["frame"])
    return changed
