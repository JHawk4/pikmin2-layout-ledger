"""Thin wrapper over OpenCV video decoding."""

from __future__ import annotations

from collections.abc import Iterator

import cv2
import numpy as np


class Video:
    def __init__(self, path: str):
        self.path = str(path)
        self.cap = cv2.VideoCapture(self.path)
        if not self.cap.isOpened():
            raise OSError(f"cannot open video: {path}")
        self.fps = self.cap.get(cv2.CAP_PROP_FPS) or 30.0
        self.frame_count = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT))
        self.width = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        self.height = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    def sample(self, step: int, start: int = 0, stop: int | None = None) -> Iterator[tuple[int, np.ndarray]]:
        """Every `step`-th frame as (index, gray). Decodes sequentially (grab is cheap)."""
        stop = self.frame_count if stop is None else stop
        self.cap.set(cv2.CAP_PROP_POS_FRAMES, start)
        i = start
        while i < stop:
            if not self.cap.grab():
                break
            if (i - start) % step == 0:
                ok, frame = self.cap.retrieve()
                if ok:
                    yield i, cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            i += 1

    def frames(self, start: int, stop: int) -> list[np.ndarray]:
        """Consecutive gray frames [start, stop)."""
        return [g for _, g in self.sample(1, max(0, start), stop)]

    def frame_at(self, index: int) -> np.ndarray | None:
        self.cap.set(cv2.CAP_PROP_POS_FRAMES, index)
        ok, frame = self.cap.read()
        return cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY) if ok else None

    def close(self) -> None:
        self.cap.release()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
