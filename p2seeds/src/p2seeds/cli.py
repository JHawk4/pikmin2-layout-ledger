"""Command line.

  p2seeds analyze VIDEO [--url URL] [--out DIR]       one video file
  p2seeds run [--manifest data/videos/manifest.json]   every downloaded run in a manifest
  p2seeds judge OUT_DIR [--kind pod]                   judge a processed run's layouts with CaveGen
  p2seeds render OUT_DIR                               render layouts missing from img/ (after --no-render)
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import cv2

from . import cavegen, chain, report, sublevels
from .analyze import analyze_event
from .events import detect
from .feed import Feed, find_feed
from .video import Video


def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def run_video(path: str, out_dir: Path, video_url: str | None = None, title: str | None = None,
              meta: dict | None = None, feed: Feed | None = None, render: bool = True,
              start_s: float | None = None, stop_s: float | None = None) -> list:
    t0 = time.time()
    video = Video(path)
    feed = feed or find_feed(video)
    log(f"feed: x {feed.x0}-{feed.x1}, y {feed.y0}-{feed.y1} ({feed.width}x{feed.height})")
    start = int(start_s * video.fps) if start_s else 0
    stop = int(stop_s * video.fps) if stop_s else None
    events = detect(video, feed, start=start, stop=stop, progress=lambda i, n: log(f"  scanning {100 * i / n:4.1f}%"))
    log(f"{len(events)} candidate entry screens")

    results = []
    for e in events:
        for r in analyze_event(video, feed, e):
            seed = f"0x{r.layout_seed:08X}" if r.layout_seed is not None else "-"
            sub = r.digit_value if r.digit_value is not None else "?"
            log(f"  {r.settled_frame or e.first:>7} {r.cave_id or '-':<4} {sub!s:<2} {r.confidence:<6} {seed} {r.note}")
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
    chain.dump(results, out_dir / "fits.json")      # pre-link state, for re-tuning chains offline
    chain.link(results)
    cavegen.set_region_for(results)

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
    a.add_argument("--start", type=float, default=None, help="seconds into the video to start scanning")
    a.add_argument("--stop", type=float, default=None, help="seconds into the video to stop scanning")
    r = sub.add_parser("run")
    r.add_argument("--manifest", default="data/videos/manifest.json")
    r.add_argument("--out", default="data/output")
    r.add_argument("--only", default=None, help="run id or slug substring")
    r.add_argument("--no-render", action="store_true")
    j = sub.add_parser("judge", help="score each recovered layout with CaveGen's judge and write judge.html")
    j.add_argument("out_dir", help="a processed run folder (contains seeds.json and img/)")
    j.add_argument("--kind", default="pod", help="CaveGen judge type: pod, at, key, cmat, score, attk")
    rd = sub.add_parser("render", help="render every seeded layout missing from OUT_DIR/img")
    rd.add_argument("out_dir")
    args = ap.parse_args(argv)

    if args.cmd == "render":
        out = Path(args.out_dir)
        entries = json.loads((out / "seeds.json").read_text(encoding="utf-8"))["entries"]
        cavegen.set_region_for(entries)
        for e in entries:
            dest = out / "img" / f"layout_{e['frame']}_{e['cave']}-{e['sublevel']}.png"
            seeded = e.get("layout_seed") and e.get("sublevel") and e.get("confidence") in ("high", "medium")
            if seeded and not dest.exists():
                cavegen.render(e["cave"], e["sublevel"], int(e["layout_seed"], 16), dest)
                log(f"  {dest.name}")
        return 0

    if args.cmd == "judge":
        from . import judge_report
        out = Path(args.out_dir)
        cavegen.set_region_for(json.loads((out / "seeds.json").read_text(encoding="utf-8"))["entries"])
        judge_report.judge_run(out, args.kind, progress=lambda i, n, r: log(
            f"  {i:>3}/{n} {r['cave']} {r['sublevel']} {r['layout_seed']} -> "
            + (f"{r['judge_score']:.2f} s ({r['judge_rank']:.1f}%)" if "judge_score" in r else "no judge")))
        log(f"report: {judge_report.write_page(out)}")
        return 0

    if args.cmd == "analyze":
        out = Path(args.out or f"data/output/{Path(args.video).stem}")
        feed = Feed(*map(int, args.feed.split(","))) if args.feed else None
        run_video(args.video, out, args.url, args.title, feed=feed, render=not args.no_render,
                  start_s=args.start, stop_s=args.stop)
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
