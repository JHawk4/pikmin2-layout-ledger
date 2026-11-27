"""Time each stage of the offline pipeline on a few known entry screens (docs/realtime-obs.md).

    python p2seeds/scripts/profile_realtime.py data/output/01_JackDraz_mewq470m [more run dirs] [--per-run N]

For each picked entry (from the run's seeds.json) it re-detects the event around the
recorded frame, then runs analyze_event with every stage wrapped in a timer, and also
times one CaveGen3 layout render. It also reports the entry screen's timeline: when the
screen goes dark, when the letters land (settled run start), when the seed could be
fitted, and when the screen fades out.
"""

from __future__ import annotations

import argparse
import json
import statistics
import subprocess
import tempfile
import time
from collections import defaultdict
from pathlib import Path

import numpy as np

from p2seeds import analyze, events, lattice, views
from p2seeds.feed import Feed
from p2seeds.video import Video

T: dict[str, float] = defaultdict(float)
N: dict[str, int] = defaultdict(int)


def timed(mod, name, key):
    fn = getattr(mod, name)

    def wrap(*a, **kw):
        t = time.perf_counter()
        try:
            return fn(*a, **kw)
        finally:
            T[key] += time.perf_counter() - t
            N[key] += 1
    setattr(mod, name, wrap)


timed(analyze, "calibrate", "name recognition (calibrate)")
timed(analyze, "track_all", "letter tracking")
timed(analyze, "fit", "velocity fit")
timed(analyze, "_search", "seed search (lattice)")
timed(analyze, "_fit_with_step", "timing-step refits")
timed(analyze, "game_times", "repeat-frame timing")
timed(analyze, "entry_runs", "screen detection (per frame, window)")
timed(analyze, "_read_sublevel", "sublevel digit")
timed(Video, "frames", "decode (video file)")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("runs", nargs="+")
    ap.add_argument("--per-run", type=int, default=4)
    ap.add_argument("--json", default=None)
    args = ap.parse_args()
    rows = []
    root = Path(__file__).resolve().parents[2]
    for run in args.runs:
        run = Path(run)
        d = json.loads((run / "seeds.json").read_text())
        meta = d["meta"]
        video_path = Path(meta["video"])
        if not video_path.is_absolute():
            video_path = Path.cwd() / video_path
        feed = Feed(*meta["feed"])
        entries = [e for e in d["entries"] if e.get("frame")]
        pick = [entries[int(i)] for i in np.linspace(0, len(entries) - 1, args.per_run)]
        with Video(str(video_path)) as video:
            for e in pick:
                f = int(e["frame"])
                T.clear(); N.clear()
                # detection pass over ~20 s around the entry, at the offline step (10)
                t0 = time.perf_counter()
                evs = events.detect(video, feed, step=10, start=max(0, f - 450), stop=f + 150)
                t_detect = time.perf_counter() - t0
                ev = min(evs, key=lambda x: abs(x.last - f)) if evs else events.Event(f, f, 1)
                t0 = time.perf_counter()
                res = analyze.analyze_event(video, feed, ev)
                t_total = time.perf_counter() - t0
                r = min(res, key=lambda r: abs((r.settled_frame or 0) - f))
                # timeline of this entry screen
                start = max(0, f - 300)
                frames = [feed.crop(g) for g in video.frames(start, f + 200)]
                flags = [events.is_entry_screen(x) for x in frames]
                means = [float(x.mean()) for x in frames]
                runs = analyze.entry_runs(frames)
                run_ab = min(runs, key=lambda ab: abs(start + ab[1] - f)) if runs else None
                # the per-frame screen check, timed alone (what a live loop pays every frame)
                t0 = time.perf_counter()
                for x in frames[:100]:
                    events.is_entry_screen(x)
                t_check = (time.perf_counter() - t0) / min(100, len(frames))
                # fall start: first frame in the run's lead with bright text (templates level) after dark
                fall_start = None
                if run_ab:
                    a = run_ab[0]
                    for j in range(max(0, a - analyze.FALL_LEAD), a):
                        if means[j] < 60 and analyze.templates.bright_level(frames[j]) >= 25:
                            fall_start = j
                            break
                # layout render
                t_render = None
                if r.layout_seed is not None and views.cavegen3_exe():
                    with tempfile.TemporaryDirectory() as tmp:
                        t0 = time.perf_counter()
                        try:
                            views.render(r.cave_id, int(e["sublevel"] or 1), r.layout_seed, Path(tmp) / "l.png")
                            t_render = time.perf_counter() - t0
                        except Exception as exc:  # noqa
                            t_render = f"fail {exc}"
                fps = video.fps
                row = dict(run=run.name, frame=f, cave=e["cave"], sub=e["sublevel"], feed=f"{feed.width}x{feed.height}",
                           conf=r.confidence, expected=e["letter_seed"],
                           got=f"0x{r.letter_seed:08X}" if r.letter_seed is not None else None,
                           note=r.note, t_total=t_total, t_detect_window=t_detect, t_check_per_frame=t_check,
                           t_render=t_render, stages={k: (round(v, 4), N[k]) for k, v in T.items()},
                           fall_start_s=None if fall_start is None or not run_ab else (run_ab[0] - fall_start) / fps,
                           settled_s=None if not run_ab else (run_ab[1] - run_ab[0]) / fps)
                rows.append(row)
                print(json.dumps(row, default=str), flush=True)
    if args.json:
        Path(args.json).write_text(json.dumps(rows, indent=1, default=str))
    tot = [r["t_total"] for r in rows]
    print(f"\n{len(rows)} entries; analyze_event median {statistics.median(tot):.2f}s, max {max(tot):.2f}s")
    print("seed matches recorded:", sum(r["got"] == r["expected"] for r in rows), "/", len(rows))


if __name__ == "__main__":
    main()
