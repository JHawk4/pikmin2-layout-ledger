"""Analyze one entry-screen event: cave, letter fall, seed."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from . import digits, letters_model, templates
from .calibrate import Calibration, calibrate
from .events import Event, is_entry_screen
from .feed import Feed
from .fit import FitResult, fit
from .search import Candidate, search
from .track import track_all
from .video import Video

MIN_CAVE_SCORE = 0.38      # name-match score below this means "not an entry screen"
MIN_CAVE_MARGIN = 0.12     # and the best cave must beat the second best by this much
FALL_LEAD = 110            # frames before a settled run starts that may contain the fall
FALL_TAIL = 40             # and after (late bounces)
MAX_FIT_RMS_PX = 0.6       # good fits are ~0.05-0.15 px


@dataclass
class EventResult:
    event: Event
    settled_frame: int | None = None
    cave: str | None = None
    cave_id: str | None = None
    cave_score: float = 0.0
    runner_up: tuple | None = None
    fit: FitResult | None = None
    candidates: list[Candidate] = field(default_factory=list)
    letter_seed: int | None = None
    layout_seed: int | None = None
    confidence: str = "none"       # "high", "medium", "low", "none"
    note: str = ""
    digit_crop: np.ndarray | None = None
    digit_value: int | None = None
    digit_votes: dict = field(default_factory=dict)
    sublevel: int | None = None
    sublevel_source: str = ""


def entry_runs(frames: list[np.ndarray], min_len: int = 6) -> list[tuple[int, int]]:
    """Runs [a, b] of consecutive frames that look like a settled entry screen.

    While letters are still falling they cross the top of the screen, so a run
    starts roughly when the name has landed and ends at the fade-out. Other
    dark text screens (menus, memory card checks, overworld titles) form runs
    too; the caller tells them apart by recognizing the cave name.
    """
    flags = [is_entry_screen(f) for f in frames]
    runs, k = [], 0
    while k < len(flags):
        if flags[k]:
            a = k
            while k < len(flags) and flags[k]:
                k += 1
            if k - a >= min_len:
                runs.append((a, k - 1))
        k += 1
    return runs


def digit_crop(feed_gray: np.ndarray) -> np.ndarray | None:
    """The rightmost glyph on the 'Sublevel N' line (the number), prepped."""
    H = feed_gray.shape[0]
    y0, y1 = int(0.46 * H), int(0.70 * H)
    p = templates.prep(feed_gray[y0:y1])
    on = p > 0.5
    rows = np.nonzero(on.mean(axis=1) > 0.01)[0]
    cols = np.nonzero(on.any(axis=0))[0]
    if len(rows) == 0 or len(cols) == 0:
        return None
    # glyph groups separated by gaps of >= 6% of the line height
    gap = max(3, int(0.25 * (rows[-1] - rows[0] + 1)))
    groups, start = [], cols[0]
    for a, b in zip(cols[:-1], cols[1:]):
        if b - a > gap:
            groups.append((start, a))
            start = b
    groups.append((start, cols[-1]))
    x0, x1 = groups[-1]
    glyph_rows = np.nonzero(on[:, x0: x1 + 1].any(axis=1))[0]   # the digit's own height
    if len(glyph_rows) == 0:
        return None
    return p[glyph_rows[0]: glyph_rows[-1] + 1, x0: x1 + 1]


def analyze_event(video: Video, feed: Feed, event: Event, search_kw: dict | None = None) -> list[EventResult]:
    """All sublevel entries inside one candidate window (usually one, sometimes two
    when consecutive entries are only seconds apart). Unrecognized windows yield a
    single result with a note."""
    start = max(0, event.first - 150)
    stop = min(video.frame_count, event.last + 30)
    frames = [feed.crop(g) for g in video.frames(start, stop)]
    if not frames:
        return [EventResult(event, note="no frames decoded")]
    runs = entry_runs(frames)
    if not runs:
        return [EventResult(event, note="no settled entry screen")]

    # recognize the cave on each run; a run that continues the previous one (same
    # cave, small gap, e.g. split by a flicker) belongs to the same entry
    entries: list[list] = []          # [cal, a, b, k]
    best_reject = None
    for a, b in runs:
        k = max(a, b - 3)             # late in the run: bubbles have faded, before the fade-out
        cal = calibrate(frames[k])
        margin = cal.score - (cal.runner_up[1] if cal.runner_up else 0.0) if cal else 0.0
        if cal is None or cal.score < MIN_CAVE_SCORE or margin < MIN_CAVE_MARGIN:
            if cal and (best_reject is None or cal.score > best_reject[0].score):
                best_reject = (cal, margin)
            continue
        if entries and entries[-1][0].cave == cal.cave and a - entries[-1][2] < 60:
            entries[-1][2] = b
            if cal.score > entries[-1][0].score:
                entries[-1][0], entries[-1][3] = cal, k
            continue
        entries.append([cal, a, b, k])
    if not entries:
        if best_reject:
            cal, margin = best_reject
            return [EventResult(event, cave_score=cal.score,
                                note=f"cave name not recognized (best {cal.cave.cavegen} {cal.score:.2f}, margin {margin:.2f})")]
        return [EventResult(event, note="no text found")]
    return [_analyze_entry(video, feed, event, frames, start, *e, search_kw=search_kw) for e in entries]


def _analyze_entry(video, feed, event, frames, start, cal, a, b, k, search_kw=None) -> EventResult:
    r = EventResult(event)
    r.settled_frame = start + k
    r.cave, r.cave_id, r.cave_score, r.runner_up = cal.cave.name, cal.cave.cavegen, cal.score, cal.runner_up
    r.digit_crop = digit_crop(frames[k])
    r.digit_value, r.digit_votes = _read_sublevel(frames, a, b)

    # the fall ends shortly after the run starts (bounces settle inside it)
    if a < FALL_LEAD:
        extra = [feed.crop(g) for g in video.frames(max(0, start - FALL_LEAD), start)]
        frames = extra + frames
        a, k = a + len(extra), k + len(extra)
    fall = drop_repeats(frames[a - FALL_LEAD: min(len(frames), a + FALL_TAIL)])
    tracks = track_all(fall, cal)
    try:
        r.fit = fit(tracks, cal.cave.num_chars, s_guess=feed.height / 480.0)
    except ValueError as exc:
        r.note = f"fit failed: {exc}"
        return r
    if np.sum(np.isfinite(r.fit.v)) < 6:
        r.note = "too few letters measured"
        return r
    if r.fit.rms_px > MAX_FIT_RMS_PX:
        # a poor fit means wide tolerances, which makes the search enumerate huge sets
        r.note = f"letter fit too poor ({r.fit.rms_px:.2f} px)"
        return r
    # a narrow bias window is ~3x faster; widen only if it finds nothing convincing
    for max_bias in (0.15, 0.5):
        r.candidates = search(r.fit.v, r.fit.sigma, max_bias=max_bias, **(search_kw or {}))
        r.confidence = _confidence(r.candidates)
        if r.confidence in ("high", "medium"):
            break
    if not r.candidates:
        r.note = "no seed matches"
        return r
    best = r.candidates[0]
    r.letter_seed = best.letter_seed
    r.layout_seed = letters_model.layout_seed(best.letter_seed, cal.cave.num_chars)
    return r


def drop_repeats(frames: list[np.ndarray], thr: float = 0.1) -> list[np.ndarray]:
    """Remove frames identical to the one before.

    A repeated frame means the game did not advance (a lag frame, e.g. right
    after a save prompt, or a duplicate from the capture). Keeping it would
    put every later letter position one game frame late. Static frames before
    the fall carry no information, so dropping them is harmless.
    """
    out = [frames[0]] if frames else []
    for f in frames[1:]:
        if np.abs(f.astype(np.int16) - out[-1].astype(np.int16)).mean() > thr:
            out.append(f)
    return out


def _read_sublevel(frames: list[np.ndarray], a: int, b: int, n: int = 7) -> tuple[int | None, dict]:
    """Read the sublevel digit on several frames of the settled run; majority of clear reads."""
    votes: dict[int, int] = {}
    for j in np.linspace(a, b, n).astype(int):
        value, _ = digits.read(digit_crop(frames[j]))
        if value is not None:
            votes[value] = votes.get(value, 0) + 1
    if not votes:
        return None, votes
    value, count = max(votes.items(), key=lambda kv: kv[1])
    return (value if count > sum(votes.values()) / 2 else None), votes


def _confidence(cands: list[Candidate]) -> str:
    """'high' when many letters agree tightly and nothing else comes close."""
    if not cands:
        return "none"
    best = cands[0]
    n_meas = int(np.sum(np.isfinite(best.residuals)))
    gap = (cands[1].score - best.score) if len(cands) > 1 else float("inf")
    per = best.score / max(1, n_meas)
    if n_meas >= 10 and per < 4 and gap > 30:
        return "high"
    if n_meas >= 7 and per < 6 and gap > 15:
        return "medium"
    return "low"
