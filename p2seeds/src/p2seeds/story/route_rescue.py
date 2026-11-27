"""Wii U VC: titles cut to black before the cave name's letters land.

The Wii U loads quickly, so on short loads (final floors above all) the title fades out
while the last letters of the cave name are still in the air. No frame then shows a
settled name, so the entry is never a candidate and the cave can't be recognized. Two
things still hold:

- "Sublevel N" appears before the name starts falling and stays put. It is found by
  matching the "Sublevel" word taken from another entry of the same video.
- The route says which cave it is. Between two recognized entries, the missing sublevels
  belong to the cave before (after its last one read) or to the cave after (before its
  first one read). The sublevel digit picks between them. A Pay Off Debt cave the run has
  no seed in at all (mercysnow's Hole of Beasts) may sit in any gap. A sublevel number that
  came only from the sequence (no digit read) is not trusted to bound a gap.

Within one video a cave's name always lands in the same place at the same scale, so the
calibration (letter boxes) of another entry of the same cave can be used as it is. A cave
with no such entry is calibrated, on that cave alone, on the title's own last frames, where
the letters have (nearly) landed while the picture fades. The
fit only needs each letter's free fall, and the letters are visible for 25-35 frames
before the cut, so the seed can be read without a settled frame. Wrong seeds still have
to chain with their neighbours (chain.link).
"""

from __future__ import annotations

import numpy as np

from .. import caves
from . import templates
from .analyze import EventResult, _analyze_entry, _read_sublevel
from .calibrate import Calibration, calibrate
from .events import SUB_BAND, Event, normalize

SCAN_STEP = 3           # titles show "Sublevel N" for 15+ frames
WORD_MIN = 0.6          # the "Sublevel" word clearly there
WORD_KEEP = 0.3         # still there, over a bright picture or fading
DIGIT_VOTES = 5         # of the 9 digit reads on a title
WORD_FRAC = {"en": 0.75, "ja": 0.5}   # of the sub line's width, from its left end
NEAR = 90               # frames: a title this close to a recognized entry is that entry
SELF_MIN = 0.30         # a title calibrated on itself (no sibling entry): its own cave's score
SELF_FRAMES = 14        # its last frames tried for that


def _cave(r: EventResult) -> caves.Cave:
    return next(c for c in caves.CAVES if c.cavegen == r.cave_id and c.lang == (r.lang or "en"))


def _sibling_cal(video, feed, r: EventResult) -> tuple[Calibration, int] | None:
    """Calibrate a recognized entry again, on its own cave only (its settled frames)."""
    cave, best = _cave(r), None
    for f in range(r.settled_frame - 8, r.settled_frame + 3, 2):
        g = video.frame_at(f)
        if g is None:
            continue
        c = calibrate(normalize(feed.crop(g)), caves=[cave])
        if c is not None and (best is None or c.score > best[0].score):
            best = (c, f)
    return best


class _Word:
    """The 'Sublevel' word of the sub line, matched where it sits in this video."""

    def __init__(self, gray: np.ndarray, frac: float = 0.75):
        H = gray.shape[0]
        self.y0, self.y1 = int(SUB_BAND[0] * H), int(SUB_BAND[1] * H)
        p = templates.prep(gray[self.y0: self.y1])
        on = p > 0.5
        rows, cols = np.nonzero(on.mean(axis=1) > 0.01)[0], np.nonzero(on.any(axis=0))[0]
        self.ok = len(rows) > 0 and len(cols) > 0
        if not self.ok:
            return
        self.r0, self.r1, self.c0 = rows[0], rows[-1] + 1, cols[0]
        self.t = p[self.r0: self.r1, self.c0: self.c0 + int(frac * (cols[-1] + 1 - self.c0))]

    def score(self, gray: np.ndarray) -> float:
        q = templates.prep(normalize(gray)[self.y0: self.y1])
        pv, ph = 4, 40           # a two-digit number shifts a centred line a little
        reg = q[max(0, self.r0 - pv): self.r1 + pv, max(0, self.c0 - ph): self.c0 + self.t.shape[1] + ph]
        if reg.shape[0] < self.t.shape[0] or reg.shape[1] < self.t.shape[1] or reg.std() < 1e-3:
            return 0.0
        return float(templates.match(reg, self.t).max())


def _titles(video, feed, word: _Word, lo: int, hi: int) -> list[tuple[int, int]]:
    """(first, last) frames showing the sub line between lo and hi."""
    hits = [f for f, g in video.sample(SCAN_STEP, lo, hi) if word.score(feed.crop(g)) >= WORD_MIN]
    runs: list[list[int]] = []
    for f in hits:
        if runs and f - runs[-1][1] <= 5 * SCAN_STEP:
            runs[-1][1] = f
        else:
            runs.append([f, f])
    out = []
    for a, b in runs:
        # to the frame: the line stays on, more weakly, while the name falls over a picture
        lo2, hi2 = max(lo, a - SCAN_STEP), min(hi, b + 60)
        on = [f for f, g in zip(range(lo2, hi2), video.frames(lo2, hi2)) if word.score(feed.crop(g)) >= WORD_KEEP]
        if on:
            out.append((on[0], on[-1]))
    return out


def _sub(r: EventResult) -> int | None:
    """The entry's sublevel when its digit was read (or it came from elsewhere), not a sequence guess."""
    return None if r.sublevel_source == "sequence" else r.sublevel


def _missing(prev: EventResult | None, nxt: EventResult | None, unseen: tuple[str, ...] = ()
             ) -> list[tuple[str, int]]:
    """(cave, sublevel) the route goes through between two recognized entries; `unseen` caves (no
    entry anywhere in the run) may be anywhere."""
    out = []
    if prev is not None and prev.sublevel:
        lo = _sub(prev) or 0
        out += [(prev.cave_id, s) for s in range(lo + 1, caves.get(prev.cave_id).sublevels + 1)]
    if nxt is not None and nxt.sublevel:
        hi = _sub(nxt) or caves.get(nxt.cave_id).sublevels + 1
        if prev is not None and prev.cave_id == nxt.cave_id:
            out = [(c, s) for c, s in out if s < hi]
        else:
            out += [(nxt.cave_id, s) for s in range(1, hi)]
    for c in unseen:
        out += [(c, s) for s in range(1, caves.get(c).sublevels + 1) if (c, s) not in out]
    return out


def _unseen(found: list[EventResult]) -> tuple[str, ...]:
    """Pay Off Debt caves with no entry in a run that looks like Pay Off Debt (all its caves are)."""
    from .analyze import POD_CAVES
    have = {r.cave_id for r in found}
    if not have or not have <= set(POD_CAVES):
        return ()
    return tuple(c for c in POD_CAVES if c not in have)


def _self_cal(frames: list[np.ndarray], a: int, cave: caves.Cave) -> tuple[Calibration, int] | None:
    """Calibrate a title on its own last frames, on one cave only (no sibling entry to borrow from)."""
    best = None
    for k in range(max(0, a - SELF_FRAMES), a + 1):
        c = calibrate(normalize(frames[k]), caves=[cave])
        if c is not None and c.score >= SELF_MIN and (best is None or c.score > best[0].score):
            best = (c, k)
    return best


def rescue(video, feed, results: list[EventResult], log=print) -> list[EventResult]:
    """New results for cut-short titles in the gaps the route leaves (wide feeds)."""
    # only entries with a seed anchor the route: a seedless one's cave may be a guess
    seeded = [r for r in results if r.cave_id and r.sublevel and r.settled_frame and r.confidence in ("high", "medium")]
    if not seeded:
        return []
    langs = [r.lang or "en" for r in seeded]
    lang = max(set(langs), key=langs.count)          # the run's language
    found = sorted((r for r in seeded if (r.lang or "en") == lang), key=lambda r: r.settled_frame)
    cals: dict[str, tuple[Calibration, int] | None] = {}

    def cal_for(cave_id: str, near: int):
        if cave_id not in cals:
            sibs = sorted((r for r in found if r.cave_id == cave_id), key=lambda r: abs(r.settled_frame - near))
            cals[cave_id] = _sibling_cal(video, feed, sibs[0]) if sibs else None
        return cals[cave_id]

    first = cal_for(found[0].cave_id, found[0].settled_frame)
    if first is None:
        return []
    # "Sublevel N" / "地下 N 階": the template stops before the digit
    word = _Word(normalize(feed.crop(video.frame_at(first[1]))), frac=WORD_FRAC[lang])
    if not word.ok:
        return []

    unseen = _unseen(found)
    by_id = {c.cavegen: c for c in caves.CAVES if c.lang == lang}
    out = []
    gaps = [(None, found[0])] + list(zip(found, found[1:])) + [(found[-1], None)]
    for prev, nxt in gaps:
        want = _missing(prev, nxt, unseen)
        if not want:
            continue
        lo = prev.settled_frame + NEAR if prev else 0
        hi = nxt.settled_frame - NEAR if nxt else video.frame_count
        if hi - lo < 30:
            continue
        for t0, t1 in _titles(video, feed, word, lo, hi):
            # a title near an entry with a seed is that entry; one near a seedless entry is tried
            # (the caller replaces that entry with this one, see replaced)
            if any(abs(r.settled_frame - t1) < NEAR for r in results if r.settled_frame and r.layout_seed is not None):
                continue
            start = max(0, t1 - 150)
            frames = [feed.crop(g) for g in video.frames(start, min(video.frame_count, t1 + 30))]
            a = t1 - start
            digit, votes = _read_sublevel([normalize(f) for f in frames], max(0, t0 - start), a, n=9, lang=lang)
            # a real title shows its digit clearly, and it is one the route still needs; bright
            # gameplay can half-match the "Sublevel" word but not that
            if digit is None or votes.get(digit, 0) < DIGIT_VOTES:
                continue
            options = [cs for cs in want if cs[1] == digit]
            if not options:
                continue
            best = None
            for cave_id in dict.fromkeys(c for c, _ in options):
                cs = cal_for(cave_id, t1)
                if cs is not None:
                    cal, k = cs[0], a
                else:
                    own = _self_cal(frames, a, by_id[cave_id]) if cave_id in by_id else None
                    if own is None:
                        continue
                    cal, k = own
                r = _analyze_entry(video, feed, Event(t0, t1, 1), frames, start, cal, k, k, k)
                r.digit_value = digit
                subs = [s for c, s in options if c == cave_id]
                if len(subs) == 1:
                    r.sublevel, r.sublevel_source = subs[0], "digit" if digit is not None else "route"
                if best is None or _rank(r) > _rank(best):
                    best = r
            if best is None or (best.layout_seed is None and best.fit is None):
                log(f"    {t1:>6} {'/'.join(c for c, _ in options) or '-'} cut-short title: "
                    f"{best.note if best else 'no cave from the route'}")
                continue
            # a fit without a seed of its own (a short Japanese name) is still worth keeping: the
            # chain's window search next to a neighbour's seed can find it (chain.link)
            best.note = ", ".join(x for x in (best.note, "title cut short: cave from the route, letters fitted as they fell") if x)
            out.append(best)
    return out


def replaced(results: list[EventResult], extra: list[EventResult]) -> list[EventResult]:
    """results without the seedless entries a rescued title stands for, plus the rescued ones."""
    def gone(r):
        return r.layout_seed is None and r.settled_frame and any(abs(r.settled_frame - x.settled_frame) < NEAR for x in extra)
    return sorted([r for r in results if not gone(r)] + extra, key=lambda r: r.settled_frame or r.event.first)


def _rank(r: EventResult) -> int:
    return {"none": 0, "low": 1, "medium": 2, "high": 3}[r.confidence]
