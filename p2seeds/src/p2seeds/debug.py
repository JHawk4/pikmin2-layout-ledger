"""Debug images for one sublevel entry: what the letter tracker saw and how the fall fit went.

    python -m p2seeds debug data/videos/<run>.mp4 --frame 29159 [--feed x0,y0,x1,y1] [--out file.png]

`--frame` is any frame inside the entry screen (the "frame" of a seeds.json entry works).
The image has three parts:
  1. a filmstrip of the fall, each tracked letter boxed where the tracker matched it
     (green: used in the fit, orange: matched but not used, e.g. bouncing), with the
     fitted position as a red tick;
  2. every letter's height over game time: dots measured, lines fitted;
  3. the fit residual per letter in pixels.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import cv2
import numpy as np

from . import analyze, letters_model
from .calibrate import calibrate
from .events import Event
from .feed import Feed, find_feed
from .fit import fit
from .track import track_all
from .video import Video

PALETTE = [(214, 120, 42), (52, 104, 235), (122, 175, 27), (0, 161, 237), (164, 123, 232),
           (0, 131, 0), (214, 80, 98), (72, 73, 227), (130, 130, 130), (180, 150, 0)]   # BGR


def _model_y(fr, i, v, n, F0, s, y_floor):
    f = fr - letters_model.delay_frames(i, n) - F0
    return y_floor - s * letters_model.pos(v, f)


def render(video_path: str, frame: int, feed: Feed | None = None, out: str | Path | None = None,
           weak: bool = False, wall: bool = False, compact: bool = False, video: Video | None = None) -> Path:
    """`weak` / `wall`: the variants the detector may have used (weaker letter matches allowed;
    timing by the video clock), so the picture shows what the detector actually saw.
    `compact`: a smaller picture for the detection page (4 frames of the fall, shorter plots)."""
    video = video or Video(video_path)
    feed = feed or find_feed(video)
    ev = Event(frame, frame, 1)
    start = max(0, frame - 150 - analyze.FALL_LEAD)
    frames = [feed.crop(g) for g in video.frames(start, min(video.frame_count, frame + 60))]
    runs = analyze.entry_runs(frames)
    near = [r for r in runs if r[0] - 5 <= frame - start <= r[1] + 5] or runs
    if not near:
        raise ValueError("no settled entry screen near that frame")
    a, b = near[0]
    k = max(a, b - 3)
    cal = calibrate(frames[k])
    if cal is None:
        raise ValueError("cave name not recognized")
    n = cal.cave.num_chars
    clip = frames[max(0, a - analyze.FALL_LEAD): min(len(frames), a + analyze.FALL_TAIL)]
    fall, times = analyze.game_times(clip, wall=wall)
    raw = track_all(fall, cal, min_score=analyze.LOW_MATCH) if weak else track_all(fall, cal)
    tracks = [replace(t, frames=times[t.frames.astype(int)]) for t in raw]
    try:
        f = fit(tracks, n, s_guess=feed.height / 480.0, **({"min_score": analyze.LOW_MATCH} if weak else {}))
    except ValueError as exc:
        f = None
        note = f"fit failed: {exc}"
    cands, conf = analyze._search(f) if f is not None else ([], "none")
    if f is not None:
        note = (f"{int(np.isfinite(f.v).sum())} letters fitted, rms {f.rms_px:.2f} px, "
                f"search: {conf}" + (f", seed 0x{cands[0].letter_seed:08X}, score {cands[0].score:.1f}" if cands else ""))

    # --- 1. filmstrip ----------------------------------------------------------------
    # game times each letter contributed to the fit (residual frames are relative to the letter's start)
    used = {i: set(np.round(fr + letters_model.delay_frames(i, n)).astype(int)) for i, (fr, _) in (f.residuals.items() if f else [])}
    # frames of the fall the fit used (else any frame a letter was matched in)
    used_t = sorted(t for ts in used.values() for t in ts)
    if used_t:
        seen = [i for i, t in enumerate(times) if used_t[0] - 2 <= t <= used_t[-1] + 6]
    else:
        seen = sorted({int(x) for t in raw for x in t.frames})
    picks = np.linspace(seen[0], seen[-1], 4 if compact else 6).round().astype(int) if seen else []
    scale = 1 if compact else (2 if feed.height < 400 else 1)
    tiles = []
    for p in picks:
        img = cv2.cvtColor(fall[p], cv2.COLOR_GRAY2BGR)
        for t in raw:
            hit = np.nonzero(t.frames == p)[0]
            box = next(bx for bx in cal.letters if bx.index == t.index)
            h, w = box.template.shape
            gt = times[p]
            if len(hit):
                y = t.y[hit[0]]
                ok = int(round(gt)) in used.get(t.index, ())
                col = (60, 200, 60) if ok else (0, 150, 255)
                cv2.rectangle(img, (int(box.x), int(round(y))), (int(box.x + w), int(round(y + h))), col, 1)
            if f is not None and np.isfinite(f.v[t.index]) and gt - letters_model.delay_frames(t.index, n) - f.F0 >= 0:
                ym = min(_model_y(gt, t.index, f.v[t.index], n, f.F0, f.s, f.y_floor), f.y_floor)
                cv2.line(img, (int(box.x), int(round(ym))), (int(box.x + w), int(round(ym))), (40, 40, 230), 1)
        img = cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_NEAREST)
        cv2.putText(img, f"clip frame {p}  game t {times[p]:.0f}", (6, 18), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
        tiles.append(img)
    per_row = 4 if compact else 3
    rows = [cv2.hconcat(tiles[i:i + per_row]) for i in range(0, len(tiles), per_row)]
    strip = cv2.vconcat(rows) if rows else np.zeros((10, 10, 3), np.uint8)

    # --- 2. heights over game time, 3. residuals --------------------------------------
    W, H, R = strip.shape[1], (220 if compact else 360), (120 if compact else 200)
    plot = np.full((H + R, W, 3), 255, np.uint8)
    if used_t:                                   # plot only around the fall the fit used
        lo_t, hi_t = used_t[0] - 10, used_t[-1] + 25
        tracks = [replace(tr, frames=tr.frames[m], y=tr.y[m], score=tr.score[m])
                  for tr in tracks for m in [(tr.frames >= lo_t) & (tr.frames <= hi_t)]]
    all_t = np.concatenate([tr.frames for tr in tracks]) if tracks else np.array([0.0, 1.0])
    all_y = np.concatenate([tr.y for tr in tracks]) if tracks else np.array([0.0, 1.0])
    if len(all_t) == 0:
        all_t, all_y = np.array([0.0, 1.0]), np.array([0.0, 1.0])
    t0, t1 = float(all_t.min()) - 2, float(all_t.max()) + 2
    y0, y1 = float(all_y.min()) - 10, float(all_y.max()) + 10
    X = lambda t: int(50 + (t - t0) / (t1 - t0) * (W - 70))
    Y = lambda y: int(20 + (y - y0) / (y1 - y0) * (H - 50))
    cv2.putText(plot, "glyph top (px, down) vs game frame: dots measured, lines fitted", (50, 14),
                cv2.FONT_HERSHEY_SIMPLEX, 0.45, (40, 40, 40), 1)
    for j, tr in enumerate(tracks):
        col = PALETTE[j % len(PALETTE)]
        for t, y in zip(tr.frames, tr.y):
            cv2.circle(plot, (X(t), Y(y)), 2, col, -1)
        if f is not None and np.isfinite(f.v[tr.index]):
            ts = np.linspace(tr.frames.min(), tr.frames.max(), 80)
            ym = _model_y(ts, tr.index, f.v[tr.index], n, f.F0, f.s, f.y_floor)
            ym = np.minimum(ym, f.y_floor)
            pts = np.array([[X(t), Y(y)] for t, y in zip(ts, ym)], np.int32)
            cv2.polylines(plot, [pts], False, col, 1)
        if len(tr.frames):
            cv2.putText(plot, tr.ch, (X(tr.frames[0]) - 12, Y(tr.y[0]) + 4), cv2.FONT_HERSHEY_SIMPLEX, 0.45, col, 1)
    # residuals
    top = H
    cv2.putText(plot, "fit residual per letter (px), +-1 px band", (50, top + 14), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (40, 40, 40), 1)
    mid = top + R // 2 + 5
    py = lambda r: int(mid - np.clip(r, -4, 4) * (R / 10))
    cv2.rectangle(plot, (50, py(1)), (W - 20, py(-1)), (235, 235, 235), -1)
    cv2.line(plot, (50, mid), (W - 20, mid), (150, 150, 150), 1)
    if f is not None:
        for j, tr in enumerate(tracks):
            if tr.index in f.residuals:
                fr, r = f.residuals[tr.index]
                col = PALETTE[j % len(PALETTE)]
                for t, rv in zip(fr + letters_model.delay_frames(tr.index, n), r):
                    cv2.circle(plot, (X(t), py(rv)), 2, col, -1)

    head = np.full((48, W, 3), 255, np.uint8)
    cv2.putText(head, f"{cal.cave.label} (score {cal.score:.2f}) entry near frame {frame} of {Path(video_path).name}",
                (8, 18), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1)
    cv2.putText(head, note, (8, 38), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1)
    img = cv2.vconcat([head, strip, plot])
    out = Path(out or f"debug_{Path(video_path).stem}_{frame}.png")
    if compact and img.shape[1] > 1200:
        img = cv2.resize(img, (1200, int(img.shape[0] * 1200 / img.shape[1])), interpolation=cv2.INTER_AREA)
    cv2.imwrite(str(out), img, [cv2.IMWRITE_JPEG_QUALITY, 82] if str(out).lower().endswith(".jpg") else [])
    return out
