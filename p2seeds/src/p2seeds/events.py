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
from .feed import Feed
from .video import Video

NAME_BAND = (0.20, 0.42)
SUB_BAND = (0.46, 0.70)


@dataclass
class Event:
    first: int          # first frame where the settled screen was detected
    last: int           # last such frame
    hits: int


def is_entry_screen(feed_gray: np.ndarray, dark_max: float = 60.0) -> bool:
    if feed_gray.mean() > dark_max:
        return False
    H = feed_gray.shape[0]
    p = templates.prep(feed_gray) > 0.5
    rows = p.mean(axis=1)
    n0, n1 = int(NAME_BAND[0] * H), int(NAME_BAND[1] * H)
    s0, s1 = int(SUB_BAND[0] * H), int(SUB_BAND[1] * H)
    name = rows[n0:n1].max() > 0.03
    sub = rows[s0:s1].max() > 0.03
    outside = np.r_[rows[: int(0.12 * H)], rows[int(0.80 * H):]].max() if H else 1
    return bool(name and sub and outside < 0.005)


def detect(video: Video, feed: Feed, step: int = 10, start: int = 0, stop: int | None = None, merge_gap: int = 300,
           progress=None) -> list[Event]:
    hits = []
    for i, gray in video.sample(step, start, stop):
        if progress and (i - start) % (step * 3000) == 0:
            progress(i, video.frame_count)
        if is_entry_screen(feed.crop(gray)):
            hits.append(i)
    events: list[Event] = []
    for i in hits:
        if events and i - events[-1].last <= merge_gap:
            events[-1].last = i
            events[-1].hits += 1
        else:
            events.append(Event(i, i, 1))
    return events
