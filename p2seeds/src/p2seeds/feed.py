"""Locate the game feed inside a stream layout.

Splits, timers, borders and backgrounds barely change over a run; the game
picture changes constantly. The feed is the largest region with high
per-pixel variation across frames sampled through the whole video.
"""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

from .video import Video


@dataclass
class Feed:
    x0: int
    y0: int
    x1: int  # exclusive
    y1: int

    @property
    def width(self) -> int:
        return self.x1 - self.x0

    @property
    def height(self) -> int:
        return self.y1 - self.y0

    def crop(self, gray: np.ndarray) -> np.ndarray:
        return gray[self.y0:self.y1, self.x0:self.x1]


def find_feed(video: Video, samples: int = 240) -> Feed:
    n = video.frame_count
    idx = np.linspace(n * 0.02, n * 0.98, samples).astype(int)
    acc = acc2 = None
    count = 0
    for i in idx:
        g = video.frame_at(int(i))
        if g is None:
            continue
        g = g.astype(np.float32)
        acc = g if acc is None else acc + g
        acc2 = g * g if acc2 is None else acc2 + g * g
        count += 1
    mean = acc / count
    std = np.sqrt(np.maximum(acc2 / count - mean * mean, 0))

    active = (std > max(12.0, 0.35 * np.percentile(std, 99))).astype(np.uint8)
    k = max(3, (min(std.shape) // 60) | 1)
    active = cv2.morphologyEx(active, cv2.MORPH_CLOSE, np.ones((k, k), np.uint8))
    active = cv2.morphologyEx(active, cv2.MORPH_OPEN, np.ones((k, k), np.uint8))
    num, labels, stats, _ = cv2.connectedComponentsWithStats(active)
    if num <= 1:
        return Feed(0, 0, video.width, video.height)
    big = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    mask = labels == big
    # A split timer next to the game can join the same component. The game is the
    # solid rectangle: alternately keep the longest run of columns, then rows, that
    # are mostly active within the current bounds.
    y0, y1, x0, x1 = 0, mask.shape[0], 0, mask.shape[1]
    for _ in range(3):
        x0, x1 = _longest_run(mask[y0:y1, :].mean(axis=0) > 0.7, offset=0)
        y0, y1 = _longest_run(mask[:, x0:x1].mean(axis=1) > 0.7, offset=0)
    x0, x1, y0, y1 = _tighten(std, x0, x1, y0, y1)
    return Feed(int(x0), int(y0), int(x1), int(y1))


def _tighten(std: np.ndarray, x0: int, x1: int, y0: int, y1: int, frac: float = 0.08, level: float = 0.75):
    """Pull each edge inward to where the game picture really starts.

    Busy overlays (a splits column with a running timer) vary enough to pass the
    activity threshold, so the box can include a strip of them. Inside the game
    the variation is uniformly high; move each edge inward, at most `frac` of the
    size, past columns/rows whose mean variation is clearly below the interior's.
    """
    def edge(profile: np.ndarray, forward: bool) -> int:
        ref = np.median(profile)
        lim = max(1, int(frac * len(profile)))
        order = range(lim) if forward else range(len(profile) - 1, len(profile) - 1 - lim, -1)
        for i in order:
            if profile[i] >= level * ref:
                return i
        return 0 if forward else len(profile) - 1

    for _ in range(2):
        cols = std[y0:y1, x0:x1].mean(axis=0)
        x0, x1 = x0 + edge(cols, True), x0 + edge(cols, False) + 1
        rows = std[y0:y1, x0:x1].mean(axis=1)
        y0, y1 = y0 + edge(rows, True), y0 + edge(rows, False) + 1
    return x0, x1, y0, y1


def _longest_run(flags: np.ndarray, offset: int) -> tuple[int, int]:
    best, start = (0, len(flags)), None
    best_len = -1
    for i, f in enumerate(np.r_[flags, False]):
        if f and start is None:
            start = i
        elif not f and start is not None:
            if i - start > best_len:
                best, best_len = (start, i), i - start
            start = None
    return best[0] + offset, best[1] + offset
