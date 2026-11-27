"""Find sublevel entry screens in a video.

An entry screen is a dark frame with exactly two lines of bright text: the
cave name at about 30% of the screen height and "Sublevel N" at about 58%.
Gameplay frames, even in dark caves, have bright HUD elements near the top
and bottom edges, so "nothing bright outside the two bands" rules them out.
A coarse pass checks a few frames per second; consecutive hits form one
event. The caller confirms each event by recognizing the cave name
(calibrate.calibrate), which is far more specific.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from . import templates
from ..feed import Feed
from ..video import Video

NAME_BAND = (0.20, 0.42)
SUB_BAND = (0.46, 0.70)


@dataclass
class Event:
    first: int          # first frame where the settled screen was detected
    last: int           # last such frame
    hits: int


WIDE_ASPECT = 1.55    # a game feed wider than this is a 16:9 (Wii / Wii U VC) picture
FADE_MIN_BRIGHT = 70.0
FADE_OUTSIDE = 0.015


def is_wide(feed: Feed) -> bool:
    """Wii (New Play Control!) and Wii U VC captures: the 4:3 picture stretched to 16:9. Their entry
    screen fades out about 10 frames after the last letter lands (loading is quick), so the name is
    read on fading frames (`fade`)."""
    return feed.width / max(1, feed.height) > WIDE_ASPECT


def normalize(feed_gray: np.ndarray) -> np.ndarray:
    """Scale a fading frame so its brightest outlines are at full entry-screen brightness."""
    ref = templates.bright_level(feed_gray)
    if ref < FADE_MIN_BRIGHT or ref >= templates.FULL_BRIGHT:
        return feed_gray
    return np.clip(feed_gray.astype(np.float32) * (templates.FULL_BRIGHT / ref), 0, 255).astype(np.uint8)


def is_entry_screen(feed_gray: np.ndarray, dark_max: float = 60.0, fade: bool = False) -> bool:
    """`fade`: also accept a fading screen (its outlines scaled to full brightness first)."""
    if feed_gray.mean() > dark_max:
        return False
    H = feed_gray.shape[0]
    p = templates.prep(normalize(feed_gray) if fade else feed_gray) > 0.5
    rows = p.mean(axis=1)
    n0, n1 = int(NAME_BAND[0] * H), int(NAME_BAND[1] * H)
    s0, s1 = int(SUB_BAND[0] * H), int(SUB_BAND[1] * H)
    name = rows[n0:n1].max() > 0.015      # a short Japanese name covers ~2.5% of a row
    sub = rows[s0:s1].max() > 0.015
    # Above the name only the middle half of the width counts: runners often put a timer or
    # splits in a top corner (keisen's All Treasures run), and gameplay is still ruled out by
    # the HUD along the bottom.
    W = feed_gray.shape[1]
    top = p[: int(0.12 * H), int(0.25 * W): int(0.75 * W)].mean(axis=1)
    outside = np.r_[top, rows[int(0.80 * H):]].max() if H else 1
    # Wii: a bright picture (a Pikmin, a burst of light) can sit behind the title and reach
    # into the bottom band a little; gameplay's HUD fills 20-35% of a row there
    return bool(name and sub and outside < (FADE_OUTSIDE if fade else 0.005))


def detect(video: Video, feed: Feed, step: int = 10, start: int = 0, stop: int | None = None, merge_gap: int = 300,
           progress=None) -> list[Event]:
    fade = is_wide(feed)
    if fade:
        step = min(step, 4)       # the Wii title is readable for only ~15 frames
    hits = []
    for i, gray in video.sample(step, start, stop):
        if progress and (i - start) % (step * 3000) == 0:
            progress(i, video.frame_count)
        if is_entry_screen(feed.crop(gray), fade=fade):
            hits.append(i)
    events: list[Event] = []
    for i in hits:
        if events and i - events[-1].last <= merge_gap:
            events[-1].last = i
            events[-1].hits += 1
        else:
            events.append(Event(i, i, 1))
    return events
