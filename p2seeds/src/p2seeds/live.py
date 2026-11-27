"""Proof of concept: find sublevel seeds from a stream of frames, as they happen.

    python -m p2seeds.live VIDEO [--feed x0,y0,x1,y1] [--speed 1] [--double] [--render DIR]

Frames are read from a video file and paced to the wall clock (`--speed 1` = real time),
which stands in for a live capture (OBS virtual camera, window capture, NDI: any source
that hands over frames one at a time). Nothing looks ahead: every decision is made from
frames already "received", kept in a short ring buffer.

Per frame the loop only runs the cheap entry-screen check (events.is_entry_screen). When
a run of entry-screen frames has lasted long enough for the letters to land, it reads the
cave name on the newest frame (calibrate) and, once FALL_TAIL frames after the landing are
in, hands the buffered fall to a worker thread that runs the offline analysis
(analyze._analyze_entry: tracking, fit, lattice search, the same fallbacks). The seed is
printed with its timing: when the letters landed, when the seed was ready, and how long the
screen stayed up after that. With `--render`, CaveGen3 draws the layout too.

`--double` repeats every frame, simulating a 60 fps capture of the 30 fps game.
`--feed` is the game picture inside the frame; the default is a run's seeds.json feed when
`--seeds` is given, else the whole frame (an OBS source that is the game capture itself).
"""

from __future__ import annotations

import argparse
import collections
import json
import queue
import threading
import time
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from . import analyze, events, rng, views
from .calibrate import calibrate
from .caves import CAVES
from .feed import Feed
from .search import search_near

RING = 400                 # frames kept (13 s at 30 fps): the fall lead plus a long title
MIN_RUN = 6                # as analyze.entry_runs
CAL_AFTER = 8              # frames into the settled run before reading the name (bubbles fade)
WORKERS = 3
NEAR = 2_000_000           # RNG steps searched after the previous layout seed (chaining)


@dataclass
class Pending:
    a: int                 # absolute frame index where the settled run started
    submitted: bool = False
    t_land: float = 0.0    # wall time when frame a was received


def fmt_t(frame: int, fps: float) -> str:
    s = frame / fps
    return f"{int(s // 60)}:{s % 60:05.2f}"


class Live:
    def __init__(self, feed: Feed | None, fps: float, render_dir: Path | None = None, log=print,
                 caves: list | None = None):
        self.feed = feed
        self.caves = caves
        self.fps = fps
        self.buf: collections.deque = collections.deque(maxlen=RING)   # (index, gray feed crop)
        self.flags: collections.deque = collections.deque(maxlen=RING)
        self.pending: Pending | None = None
        self.run_start: int | None = None
        self.found: list[tuple[str, int]] = []  # (cave, run start) of every seed found
        self.jobs: queue.Queue = queue.Queue()
        self.render_dir = render_dir
        self.log = log
        self.prev_layout: int | None = None
        self.results: list[dict] = []
        self.t_check = 0.0
        self.n = 0
        # a few workers: dark text screens that are not cave names (menus, the screens just before
        # an entry) must not hold up the entry screen behind them; matchTemplate releases the GIL
        self.workers = [threading.Thread(target=self._work, daemon=True) for _ in range(WORKERS)]
        for w in self.workers:
            w.start()

    # ---- capture side: one call per received frame --------------------------------------
    def push(self, index: int, bgr: np.ndarray, t_recv: float) -> None:
        gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
        if self.feed is not None:
            gray = self.feed.crop(gray)
        if gray.shape[0] > 480:    # a 1080p capture: the detector is tuned for <= 480 lines
            s = 480 / gray.shape[0]
            gray = cv2.resize(gray, (round(gray.shape[1] * s), 480), interpolation=cv2.INTER_AREA)
        t0 = time.perf_counter()
        flag = events.is_entry_screen(gray)
        self.t_check += time.perf_counter() - t0
        self.n += 1
        self.buf.append((index, gray))
        self.flags.append(flag)

        if flag:
            if self.run_start is None:
                self.run_start = index
        else:
            if self.pending is not None and not self.pending.submitted:
                self._submit(index - 1, t_recv)          # screen faded before FALL_TAIL frames came in
            self.run_start = None
            self.pending = None
            return
        run_len = index - self.run_start + 1
        if self.pending is None and run_len >= MIN_RUN:
            self.pending = Pending(self.run_start, t_land=t_recv - (run_len - 1) / self.fps)
        if self.pending is not None and run_len >= analyze.FALL_TAIL:
            self._submit(index, t_recv)

    def _submit(self, b: int, t_recv: float) -> None:
        p = self.pending
        if p is None or p.submitted:
            return
        p.submitted = True
        frames = [g for _, g in self.buf]
        first = self.buf[0][0]
        self.jobs.put((p, frames, first, b, t_recv))

    # ---- worker side ---------------------------------------------------------------------
    def _work(self) -> None:
        while True:
            job = self.jobs.get()
            if job is None:
                return
            p, frames, first, b, t_sub = job
            t0 = time.perf_counter()
            h, w = frames[-1].shape
            feed = Feed(0, 0, w, h)
            a = p.a - first
            if a < analyze.FALL_LEAD:
                self.log(f"  [{fmt_t(p.a, self.fps)}] entry screen too soon after the stream started; skipped")
                continue
            # the cave name, on the newest settled frames (bubbles fade during the first second)
            cal, k = None, None
            for j in [j for j in (len(frames) - 1, len(frames) - 9, len(frames) - 17) if j >= a + CAL_AFTER]:
                c = calibrate(frames[j], caves=self.caves)
                if c is not None and (cal is None or c.score > cal.score):
                    cal, k = c, j
                margin = cal.score - (cal.runner_up[1] if cal.runner_up else 0.0) if cal else 0.0
                if cal and cal.score >= analyze.MIN_CAVE_SCORE and margin >= analyze.MIN_CAVE_MARGIN:
                    break
            else:
                cal = None
            t_cal = time.perf_counter()
            if cal is None:
                self.log(f"  [{fmt_t(p.a, self.fps)}] dark text screen, not a cave name ({t_cal - t0:.2f}s)")
                continue
            if any(c == cal.cave.cavegen and 0 < p.a - a0 < 5 * self.fps for c, a0 in self.found):
                continue      # a flicker split one entry screen in two (analyze_event merges these too)
            ev = events.Event(p.a, b, 1)
            try:
                r = analyze._analyze_entry(None, feed, ev, frames, first, cal, a, b - first, k)
            except Exception as exc:  # noqa: BLE001 - a PoC keeps going
                self.log(f"  analysis failed: {exc!r}")
                continue
            t_seed = time.perf_counter()
            if r.letter_seed is not None:
                self.found.append((cal.cave.cavegen, p.a))
            how = r.confidence
            if r.confidence not in ("high",) and self.prev_layout is not None and r.fit is not None:
                # chaining: the next letter seed sits a bounded number of RNG steps after the
                # previous sublevel's layout seed, so a short scan settles a weak fit
                try:
                    c = search_near(r.fit.v, r.fit.sigma, self.prev_layout, NEAR, top=2)
                except ValueError:
                    c = []
                if c and (len(c) < 2 or c[1].score - c[0].score > 15):
                    r.letter_seed = c[0].letter_seed
                    r.layout_seed = rng.next_seed(c[0].letter_seed, cal.cave.num_chars) & rng.MASK31
                    how = f"{r.confidence}+chained ({c[0].distance} steps)"
            t_chain = time.perf_counter()
            if r.layout_seed is not None and (r.confidence in ("high", "medium") or "chained" in how):
                self.prev_layout = r.layout_seed
            img = None
            if self.render_dir is not None and r.layout_seed is not None and r.digit_value:
                try:
                    img = views.render(r.cave_id, r.digit_value, r.layout_seed,
                                       self.render_dir / f"{r.cave_id}-{r.digit_value}_{r.layout_seed:08X}.jpg")
                except Exception as exc:  # noqa: BLE001
                    self.log(f"  render failed: {exc!r}")
            t_img = time.perf_counter()
            landed_ago = time.time() - p.t_land
            row = dict(cave=r.cave_id, sublevel=r.digit_value, conf=how,
                       letter_seed=None if r.letter_seed is None else f"0x{r.letter_seed:08X}",
                       layout_seed=None if r.layout_seed is None else f"0x{r.layout_seed:08X}",
                       landed=fmt_t(p.a, self.fps), queued_after_s=round(t_sub - p.t_land, 2),
                       name_s=round(t_cal - t0, 2), analyze_s=round(t_seed - t_cal, 2), chain_s=round(t_chain - t_seed, 2),
                       render_s=round(t_img - t_chain, 2) if img else None,
                       ready_after_landing_s=round(landed_ago, 2), note=r.note, image=str(img) if img else None)
            if any((x["cave"], x["sublevel"], x["letter_seed"]) == (row["cave"], row["sublevel"], row["letter_seed"])
                   for x in self.results):
                continue           # the same screen split in two by a flicker
            self.results.append(row)
            self.log(f"[{row['landed']}] {r.cave_id}-{r.digit_value}  seed {row['letter_seed']} -> layout "
                     f"{row['layout_seed']}  ({how})  ready {row['ready_after_landing_s']:.1f}s after the letters "
                     f"landed (queued +{row['queued_after_s']:.1f}s, name {row['name_s']:.2f}s, analysis {row['analyze_s']:.2f}s"
                     + (f", render {row['render_s']:.2f}s" if img else "") + ")")

    def close(self) -> None:
        for _ in self.workers:
            self.jobs.put(None)
        for w in self.workers:
            w.join()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("video")
    ap.add_argument("--feed", help="x0,y0,x1,y1 of the game picture")
    ap.add_argument("--seeds", help="a run's seeds.json: its feed, and its seeds to compare against")
    ap.add_argument("--start", type=float, default=0.0, help="seconds into the video")
    ap.add_argument("--duration", type=float, default=None, help="seconds to play")
    ap.add_argument("--speed", type=float, default=1.0, help="playback speed; 0 = as fast as possible")
    ap.add_argument("--double", action="store_true", help="repeat each frame (a 60 fps capture)")
    ap.add_argument("--render", help="directory for layout images (CaveGen3)")
    ap.add_argument("--json", help="write the results here")
    ap.add_argument("--caves", choices=("all", "pod", "pod-ja"), default="all",
                    help="names to recognize: every story cave in both languages (as offline), or only the "
                         "Pay Off Debt caves in English / Japanese (what a runner's category and region allow)")
    args = ap.parse_args(argv)

    known = {}
    feed = None
    if args.seeds:
        d = json.loads(Path(args.seeds).read_text())
        feed = Feed(*d["meta"]["feed"])
        known = {e["frame"]: e for e in d["entries"] if e.get("frame")}
    if args.feed:
        feed = Feed(*map(int, args.feed.split(",")))
    cap = cv2.VideoCapture(args.video)
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    cap.set(cv2.CAP_PROP_POS_FRAMES, int(args.start * fps))
    out_fps = fps * (2 if args.double else 1)
    render_dir = Path(args.render) if args.render else None
    if render_dir:
        render_dir.mkdir(parents=True, exist_ok=True)
    caves = None
    if args.caves != "all":
        lang = "ja" if args.caves == "pod-ja" else "en"
        caves = [c for c in CAVES if c.cavegen in analyze.POD_CAVES and c.lang == lang]
    live = Live(feed, out_fps, render_dir, caves=caves)
    i0 = int(args.start * fps)
    n_in = 0
    t_start = time.time()
    max_lag = 0.0
    idx = 0
    stop = None if args.duration is None else int(args.duration * fps)
    while stop is None or n_in < stop:
        ok, frame = cap.read()
        if not ok:
            break
        n_in += 1
        for _ in range(2 if args.double else 1):
            due = t_start + idx / out_fps / args.speed if args.speed > 0 else None
            if due is not None:
                now = time.time()
                if now < due:
                    time.sleep(due - now)
                else:
                    max_lag = max(max_lag, now - due)
            live.push(idx, frame, time.time())
            idx += 1
    # let the worker finish the last job
    live.close()
    wall = time.time() - t_start
    print(f"\n{n_in} frames ({n_in / fps:.0f} s of video) in {wall:.0f} s; entry-screen check "
          f"{1000 * live.t_check / max(1, live.n):.2f} ms/frame; capture loop fell behind by at most {max_lag:.2f} s")
    if known:
        mult = 2 if args.double else 1
        ok = 0
        for r in live.results:
            f_land = i0 + _parse(r["landed"], out_fps) / mult
            e = min(known.values(), key=lambda e: abs(e["frame"] - f_land))
            same = abs(e["frame"] - f_land) < 30 * 30 and e["letter_seed"] == r["letter_seed"]
            ok += same
            r["offline"] = e["letter_seed"]
        print(f"seeds equal to the offline result: {ok} / {len(live.results)}")
    if args.json:
        Path(args.json).write_text(json.dumps(live.results, indent=1))
    return 0


def _parse(t: str, fps: float) -> float:
    m, s = t.split(":")
    return (int(m) * 60 + float(s)) * fps


if __name__ == "__main__":
    raise SystemExit(main())
