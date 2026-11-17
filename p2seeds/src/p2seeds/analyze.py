"""Analyze one entry-screen event: cave, letter fall, seed."""

from __future__ import annotations

from dataclasses import dataclass, field, replace

import numpy as np

from . import digits, lattice, letters_model, templates
from .calibrate import Calibration, calibrate
from .events import Event, is_entry_screen
from .feed import Feed
from .fit import FitResult, fit
from .search import Candidate, search
from .track import track_all
from .video import Video

MIN_CAVE_SCORE = 0.38      # name-match score below this means "not an entry screen"
MIN_CAVE_MARGIN = 0.12     # and the best cave must beat the second best by this much
MIN_CAVE_SCORE_JA = 0.48   # short Japanese names match random text up to ~0.40; true ones score ~0.6
FALL_LEAD = 110            # frames before a settled run starts that may contain the fall
FALL_TAIL = 40             # and after (late bounces)
LOW_MATCH = 0.4            # fallback template-match threshold for falling letters
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
    lang: str = "en"
    num_chars: int = 0


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


def digit_crop(feed_gray: np.ndarray, lang: str = "en") -> np.ndarray | None:
    """The number at the end of the 'Sublevel N' line (or Japanese '地下 N'), prepped.

    One or two digits: the rightmost group of glyphs, trimmed to its own rows. In
    Japanese a leading "1" (10-15) sits further from the next digit than the
    grouping gap, so a narrow glyph just left of the number joins it."""
    H = feed_gray.shape[0]
    y0, y1 = int(0.46 * H), int(0.70 * H)
    p = templates.prep(feed_gray[y0:y1])
    on = p > 0.5
    rows = np.nonzero(on.mean(axis=1) > 0.01)[0]
    cols = np.nonzero(on.any(axis=0))[0]
    if len(rows) == 0 or len(cols) == 0:
        return None
    # glyph groups separated by gaps of >= 25% of the line height
    gap = max(3, int(0.25 * (rows[-1] - rows[0] + 1)))
    groups, start = [], cols[0]
    for a, b in zip(cols[:-1], cols[1:]):
        if b - a > gap:
            groups.append((start, a))
            start = b
    groups.append((start, cols[-1]))
    x0, x1 = groups[-1]
    h = rows[-1] - rows[0] + 1
    if lang == "ja" and len(groups) > 1:
        a, b = groups[-2]
        if b - a + 1 < 0.45 * h and x0 - b <= 0.8 * h:
            x0 = a
    glyph_rows = np.nonzero(on[:, x0: x1 + 1].any(axis=1))[0]   # the number's own height
    if len(glyph_rows) == 0:
        return None
    return p[glyph_rows[0]: glyph_rows[-1] + 1, x0: x1 + 1]


def split_digits(crop: np.ndarray | None) -> list[np.ndarray]:
    """Cut a number into its digits at empty columns; each digit is trimmed to its rows."""
    if crop is None or crop.size == 0:
        return []
    on = crop > 0.5
    filled = on.any(axis=0)
    h = crop.shape[0]
    parts, start = [], None
    for x, f in enumerate(np.r_[filled, False]):
        if f and start is None:
            start = x
        elif not f and start is not None:
            parts.append((start, x))
            start = None
    # merge slivers (a broken stroke) into their neighbor
    merged: list[list[int]] = []
    for a, b in parts:
        if merged and (b - a < 0.12 * h or merged[-1][1] - merged[-1][0] < 0.12 * h) and a - merged[-1][1] <= 2:
            merged[-1][1] = b
        else:
            merged.append([a, b])
    out = []
    for a, b in merged:
        rows = np.nonzero(on[:, a:b].any(axis=1))[0]
        if len(rows) and rows[-1] - rows[0] + 1 >= 0.6 * h:     # a digit spans the line height
            out.append(crop[rows[0]: rows[-1] + 1, a:b])
    return out


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
        min_score = MIN_CAVE_SCORE_JA if cal is not None and cal.cave.lang == "ja" else MIN_CAVE_SCORE
        if cal is None or cal.score < min_score or margin < MIN_CAVE_MARGIN:
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
    r.cave, r.cave_id, r.cave_score, r.runner_up = cal.cave.label, cal.cave.cavegen, cal.score, cal.runner_up
    r.lang = cal.cave.lang
    r.num_chars = cal.cave.num_chars
    r.digit_crop = digit_crop(frames[k], r.lang)
    r.digit_value, r.digit_votes = _read_sublevel(frames, a, b, lang=r.lang)

    # the fall ends shortly after the run starts (bounces settle inside it)
    if a < FALL_LEAD:
        extra = [feed.crop(g) for g in video.frames(max(0, start - FALL_LEAD), start)]
        frames = extra + frames
        a, k = a + len(extra), k + len(extra)
    clip = frames[a - FALL_LEAD: min(len(frames), a + FALL_TAIL)]
    # Japanese glyphs match less sharply and short names lose 1-2 characters to the fade-in
    ja = cal.cave.lang == "ja"
    fit_kw = dict(min_score=0.5, min_letters=2) if ja else {}
    s_guess = feed.height / 480.0

    # Variants, cheapest and most reliable first; stop at the first high-confidence seed.
    #  - match: falling letters match less sharply than settled ones (motion, the fade-in,
    #    bubbles), so a second pass accepts weaker matches; a spurious match cannot produce
    #    a confident seed, the fit and the search decide.
    #  - clock: repeated frames are usually game lag (the game paused), but a capture that
    #    shows the game unevenly repeats frames the game ran through; then the video's own
    #    clock is right.
    first_failure = None
    #  - blended: each frame a 50/50 blend of two game frames, so falling letters show twice
    for weak, wall_clock, blended in ((False, False, False), (False, True, False), (True, False, False),
                                      (True, True, False), (True, False, True), (True, True, True)):
        if r.confidence == "high":
            break
        fall, times = game_times(clip, wall=wall_clock)
        raw = track_all(fall, cal, min_score=LOW_MATCH, blended=blended) if weak else track_all(fall, cal)
        tracks = [replace(t, frames=to_time(t.frames, times)) for t in raw]
        kw = {**fit_kw, "min_score": min(fit_kw.get("min_score", 0.55), LOW_MATCH)} if weak else fit_kw
        try:
            f = fit(tracks, cal.cave.num_chars, s_guess=s_guess, **kw)
        except ValueError as exc:
            first_failure = first_failure or f"fit failed: {exc}"
            continue
        n_meas = int(np.sum(np.isfinite(f.v)))
        if n_meas < 4:
            first_failure = first_failure or "too few letters measured"   # chain.link may still find it
            continue
        how = ", ".join(x for x in ("weaker letter matches allowed" if weak else "",
                                     "timed by the video clock" if wall_clock else "",
                                     "blended frames (letters doubled)" if blended else "") if x)
        cands, conf = _search(f, search_kw)
        if r.fit is None or _RANK[conf] > _RANK[r.confidence]:
            r.fit, r.candidates, r.confidence, r.note = f, cands, conf, how
        if conf != "high" and n_meas >= 5:
            # the capture may have skipped or repeated one game frame mid-fall: every letter
            # is then a frame further along (or behind) from that point on
            for f2, d, k in _fit_with_step(tracks, cal.cave.num_chars, s_guess, f):
                c2, conf2 = _search(f2, search_kw, retries=False)
                if _RANK[conf2] > _RANK[r.confidence]:
                    r.fit, r.candidates, r.confidence = f2, c2, conf2
                    r.note = ", ".join(x for x in (how, f"timing step of {d:+d} frame at fall frame {k}") if x)
    if r.fit is None:
        r.note = first_failure or "fit failed"
        return r
    if not r.candidates:
        r.note = (f"letter fit too poor ({r.fit.rms_px:.2f} px)" if r.fit.rms_px > MAX_FIT_RMS_PX
                  else "no seed matches")
        return r
    best = r.candidates[0]
    r.letter_seed = best.letter_seed
    r.layout_seed = letters_model.layout_seed(best.letter_seed, cal.cave.num_chars)
    return r


def to_time(frames: np.ndarray, times: np.ndarray) -> np.ndarray:
    """Clip frame numbers -> game time. A blended frame's lower copy (frame k + 0.5) is the
    game frame after frame k's."""
    k = np.floor(frames).astype(int)
    return times[k] + np.where(frames - k > 0, 1.0, 0.0)


_RANK = {"none": 0, "low": 1, "medium": 2, "high": 3}


def _search(f: FitResult, search_kw: dict | None = None, retries: bool = True) -> tuple[list[Candidate], str]:
    """Lattice search over the measured letters (milliseconds). When that is not conclusive
    and there are letters to spare, retry leaving out one letter, then two: a single
    mistracked letter otherwise rules out the true seed."""
    kw = {k: v for k, v in (search_kw or {}).items() if k in ("k_tol", "max_bias", "cap", "top")}
    measured = [i for i in range(len(f.v)) if np.isfinite(f.v[i]) and np.isfinite(f.sigma[i])]

    def attempt(leave_out=()):
        try:
            # retries get a smaller budget: a box that big is ambiguous anyway
            c = lattice.search(f.v, f.sigma, leave_out=leave_out,
                               max_nodes=100_000 if leave_out else 500_000, **kw)
        except ValueError:
            return [], "none"
        return c, _confidence(c)

    best = attempt()
    for k in ((1, 2) if retries else ()):
        if best[1] == "high" or len(measured) - k < 6 or f.rms_px > MAX_FIT_RMS_PX:
            break
        import itertools
        for out in itertools.combinations(measured, k):
            c = attempt(out)
            if (_RANK[c[1]], -(c[0][0].score if c[0] else 1e9)) > (_RANK[best[1]], -(best[0][0].score if best[0] else 1e9)):
                best = c
    return best


def _fit_with_step(tracks, num_chars: int, s_guess: float, base: FitResult,
                   min_gain: float = 0.8, max_picks: int = 40) -> list[tuple[FitResult, int, int]]:
    """Refits assuming the video skipped (+1) or repeated (-1) one game frame at
    clip frame k. Returns the plausible (fit, d, k), most letters first.

    game_times removes repeated frames, but a dropped frame leaves no trace in
    the pixels: every letter position after it is simply one game frame further on.
    Two rankings are kept because neither is reliable alone: the right shift lets
    more letters keep a clean free fall, but a wrong one can rescue a mistracked
    letter; and fewer letters alone also lower the rms.
    """
    frames = np.concatenate([t.frames for t in tracks]) if tracks else np.array([])
    if len(frames) == 0:
        return []
    lo, hi = int(frames.min()) + 1, int(frames.max())
    n_old = int(np.sum(np.isfinite(base.v)))

    def attempt(d, k):
        shifted = [replace(t, frames=np.where(t.frames >= k, t.frames + d, t.frames)) for t in tracks]
        try:
            return fit(shifted, num_chars, s_guess=s_guess)
        except ValueError:
            return None

    tried = {}
    for d in (1, -1):
        for k in range(lo, hi):
            f = attempt(d, k)
            if f is not None and f.rms_px <= MAX_FIT_RMS_PX:
                tried[(d, k)] = f

    def n_let(f):
        return int(np.sum(np.isfinite(f.v)))

    better = {dk: f for dk, f in tried.items()
              if n_let(f) > n_old or (n_let(f) == n_old and f.rms_px <= min_gain * base.rms_px)}
    # every plausible shift is returned (the lattice search is cheap enough to try them all);
    # the caller keeps the one whose seed is most convincing
    ranked = sorted(better.items(), key=lambda kv: (-n_let(kv[1]), kv[1].rms_px))
    return [(f, *dk) for dk, f in ranked[:max_picks]]


def game_times(frames: list[np.ndarray], thr: float = 0.1, rel: float = 0.25,
               jump: float = 1.35, wall: bool = False) -> tuple[list[np.ndarray], np.ndarray]:
    """Drop repeated frames and give each kept frame its game-frame time.

    A repeated frame means the game did not advance (a lag frame, e.g. right
    after a save prompt, or a duplicate from the capture). Keeping it would put
    every later letter position one game frame late. After re-encoding a
    duplicate is not pixel-identical, so a frame also counts as a repeat when it
    changed far less than its neighbors did (`rel` times their median change).

    Uneven frame pacing in a capture shows one game frame twice and then skips
    the next. The skip is a change about 1.5x the usual right next to a repeat;
    such a frame advances the game time by 2. A lone skip is left to the
    timing-step fallback.

    `wall=True` keeps the same frames but times each by its index in the clip: right when
    the repeats come from the capture showing the game unevenly (e.g. every third frame
    a duplicate), so the game advanced through them. The caller tries both.
    """
    if not frames:
        return [], np.zeros(0)
    d = np.array([np.abs(b.astype(np.int16) - a.astype(np.int16)).mean() for a, b in zip(frames[:-1], frames[1:])])
    local = np.zeros(len(d))
    for j in range(len(d)):
        around = np.r_[d[max(0, j - 3): j], d[j + 1: j + 4]]
        local[j] = float(np.median(around)) if len(around) else 0.0
    repeat = d <= np.maximum(thr, rel * local)
    inc = np.where(repeat, 0, 1)
    for j in range(len(d)):
        near_repeat = (j > 0 and repeat[j - 1]) or (j + 1 < len(d) and repeat[j + 1])
        if not repeat[j] and near_repeat and local[j] > 0.5 and d[j] >= jump * local[j]:
            inc[j] = 2
    t = np.r_[0, np.cumsum(inc)]
    keep = np.r_[True, ~repeat]
    if wall:
        t = np.arange(len(frames), dtype=float)
    return [f for f, k in zip(frames, keep) if k], t[keep].astype(float)


def drop_repeats(frames: list[np.ndarray], **kw) -> list[np.ndarray]:
    return game_times(frames, **kw)[0]


def _read_sublevel(frames: list[np.ndarray], a: int, b: int, n: int = 7, lang: str = "en") -> tuple[int | None, dict]:
    """Read the sublevel digit on several frames of the settled run; majority of clear reads."""
    votes: dict[int, int] = {}
    for j in np.linspace(a, b, n).astype(int):
        crop = digit_crop(frames[j], lang)
        # two digits when the crop splits into two readable ones; else one digit
        # (some Japanese digits are drawn in separate strokes and split apart)
        parts = split_digits(crop)
        value = digits.read_number(parts) if len(parts) == 2 else None
        if value is None and crop is not None:
            value = digits.read(crop)[0]
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
