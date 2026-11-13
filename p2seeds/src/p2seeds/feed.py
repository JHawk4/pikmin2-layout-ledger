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
    ys, xs = np.nonzero(labels == big)
    # trim ragged edges: keep rows/cols that are mostly active
    rows = (labels == big).mean(axis=1)
    cols = (labels == big).mean(axis=0)
    y_on = np.nonzero(rows > 0.5 * rows.max())[0]
    x_on = np.nonzero(cols > 0.5 * cols.max())[0]
    return Feed(int(x_on[0]), int(y_on[0]), int(x_on[-1]) + 1, int(y_on[-1]) + 1)
