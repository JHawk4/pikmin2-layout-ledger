"""Command line.

  p2seeds analyze VIDEO [--url URL] [--out DIR]       one video file
  p2seeds run [--manifest data/videos/manifest.json]   every downloaded run in a manifest
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import cv2

from . import cavegen, digits, report, sublevels
from .analyze import analyze_event
from .events import detect
from .feed import Feed, find_feed
from .video import Video


def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def run_video(path: str, out_dir: Path, video_url: str | None = None, title: str | None = None,
              meta: dict | None = None, feed: Feed | None = None, render: bool = True) -> list:
    t0 = time.time()
    video = Video(path)
    feed = feed or find_feed(video)
    log(f"feed: x {feed.x0}-{feed.x1}, y {feed.y0}-{feed.y1} ({feed.width}x{feed.height})")
    events = detect(video, feed, progress=lambda i, n: log(f"  scanning {100 * i / n:4.1f}%"))
    log(f"{len(events)} candidate entry screens")

    results = []
    for e in events:
        r = analyze_event(video, feed, e)
        if r.cave_id:
            r.digit_value, r.digit_score = digits.read(r.digit_crop)
        seed = f"0x{r.layout_seed:08X}" if r.layout_seed is not None else "-"
        log(f"  {r.settled_frame or e.first:>7} {r.cave_id or '-':<4} {r.confidence:<6} {seed} {r.note}")
        if r.cave_id:
            results.append(r)

    # one entry can yield two events (before/after a stutter); keep the first of identical seeds
    dedup = []
    for r in results:
        if dedup and r.letter_seed is not None and r.letter_seed == dedup[-1].letter_seed:
            continue
        dedup.append(r)
    results = dedup
    sublevels.assign(results)

    out_dir.mkdir(parents=True, exist_ok=True)
    thumbs, layouts = {}, {}
    cap = cv2.VideoCapture(path)
    for r in results:
        cap.set(cv2.CAP_PROP_POS_FRAMES, r.settled_frame)
        ok, frame = cap.read()
        if ok:
            thumbs[r.settled_frame] = frame[feed.y0:feed.y1, feed.x0:feed.x1]
        if r.digit_crop is not None:
            (out_dir / "digits").mkdir(exist_ok=True)
            cv2.imwrite(str(out_dir / "digits" / f"{r.settled_frame}_{r.cave_id}{r.sublevel}.png"),
                        (r.digit_crop * 255).astype("uint8"))
        if render and r.layout_seed is not None and r.sublevel:
            dest = out_dir / "img" / f"layout_{r.settled_frame}_{r.cave_id}-{r.sublevel}.png"
            try:
                layouts[r.settled_frame] = cavegen.render(r.cave_id, r.sublevel, r.layout_seed, dest)
            except Exception as exc:  # keep the report even if one render fails
                r.note = (r.note + f" render failed: {exc}").strip()
    cap.release()

    counts = {c: sum(r.confidence == c for r in results) for c in ("high", "medium", "low", "none")}
    meta = dict(meta or {})
    meta.update({"video": str(path), "fps": video.fps, "feed": [feed.x0, feed.y0, feed.x1, feed.y1],
                 "seconds": round(time.time() - t0, 1), "counts": counts})
    meta.setdefault("summary", f"{len(results)} sublevel entries · {counts['high']} high, {counts['medium']} medium, "
                                f"{counts['low']} low, {counts['none']} no seed · processed in {meta['seconds']:.0f} s")
    page = report.write(out_dir, title or Path(path).stem, results, video.fps, video_url, thumbs, layouts, meta)
    log(f"report: {page}")
    return results


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="p2seeds")
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("analyze")
    a.add_argument("video")
    a.add_argument("--url", default=None, help="original video URL, for timestamped links")
    a.add_argument("--out", default=None)
    a.add_argument("--title", default=None)
    a.add_argument("--feed", default=None, help="x0,y0,x1,y1 to skip feed detection")
    a.add_argument("--no-render", action="store_true")
    r = sub.add_parser("run")
    r.add_argument("--manifest", default="data/videos/manifest.json")
    r.add_argument("--out", default="data/output")
    r.add_argument("--only", default=None, help="run id or slug substring")
    r.add_argument("--no-render", action="store_true")
    args = ap.parse_args(argv)

    if args.cmd == "analyze":
        out = Path(args.out or f"data/output/{Path(args.video).stem}")
        feed = Feed(*map(int, args.feed.split(","))) if args.feed else None
        run_video(args.video, out, args.url, args.title, feed=feed, render=not args.no_render)
        return 0

    manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))["runs"]
    for run_id, entry in manifest.items():
        if entry.get("status") != "ok":
            continue
        run = entry["run"]
        slug = Path(entry["download"]["path"]).stem
        if args.only and args.only not in run_id and args.only not in slug:
            continue
        players = ",".join(p["name"] for p in run["players"])
        title = f"#{run['place']} {players} — {run['weblink']}"
        log(f"== {title}")
        run_video(entry["download"]["path"], Path(args.out) / slug, entry.get("video"), title,
                  meta={"run": run}, render=not args.no_render)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
