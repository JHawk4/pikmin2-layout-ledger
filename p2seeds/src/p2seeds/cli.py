"""Command line.

  p2seeds analyze VIDEO [--url URL] [--out DIR]       one video file
  p2seeds run [--manifest data/videos/manifest.json]   every downloaded run in a manifest
  p2seeds judge OUT_DIR [--kind pod]                   judge a processed run's layouts with CaveGen
  p2seeds render OUT_DIR                               render layouts missing from img/ (after --no-render)
  p2seeds site [--root data/output]                    landing page + one page per judged run
                                                       (one category per root: data/output_at for All Treasures)
  p2seeds batch [--manifest ...] [--jobs 4]            run + judge + treasures for every new run, then site
  p2seeds treasures OUT_DIR                            count treasure panels per sublevel (for calibration)
  p2seeds redo OUT_DIR                                 re-run a run's non-high sublevels with the current detector
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

    results, rejected = [], []

    def show(r, e):
        seed = f"0x{r.layout_seed:08X}" if r.layout_seed is not None else "-"
        sub = r.digit_value if r.digit_value is not None else "?"
        log(f"  {r.settled_frame or e.first:>7} {r.cave_id or '-':<4} {sub!s:<2} {r.confidence:<6} {seed} {r.note}")

    for e in events:
        for r in analyze_event(video, feed, e):
            show(r, e)
            (results if r.cave_id else rejected).append(r)
    # second pass: on blurry captures a whole cave can match just under the threshold
    from .analyze import RESCUE_MARGIN_NEAR, rescue_caves
    from .events import is_wide
    for r0, cave, margin in rescue_caves(rejected + [r for r in results if r.near], results, wide=is_wide(feed)):
        for r in analyze_event(video, feed, r0.event, only=cave, only_margin=margin):
            if r.cave_id and not any(x.cave_id == r.cave_id and abs((x.settled_frame or 0) - (r.settled_frame or 0)) < 90
                                     for x in results):
                why = ("title cut short, cave as its neighbour's" if margin == RESCUE_MARGIN_NEAR
                       else "cave name matched weakly (blurry capture)")
                r.note = ", ".join(x for x in (r.note, why) if x)
                show(r, r0.event)
                results.append(r)
    results.sort(key=lambda r: r.settled_frame or r.event.first)

    # one entry can yield two events (before/after a stutter); keep the first of identical seeds
    dedup = []
    for r in results:
        if dedup and r.letter_seed is not None and r.letter_seed == dedup[-1].letter_seed:
            continue
        dedup.append(r)
    results = dedup
    sublevels.assign(results)
    if is_wide(feed):
        # Wii U VC: titles cut to black before the name lands, found from the route (route_rescue)
        from . import route_rescue
        extra = route_rescue.rescue(video, feed, results, log=log)
        for r in extra:
            show(r, r.event)
        if extra:
            results = route_rescue.replaced(results, extra)
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
    rd.add_argument("--redraw", action="store_true", help="draw every layout again, not only missing ones")
    tr = sub.add_parser("treasures", help="count treasures collected per sublevel from the treasure panel")
    tr.add_argument("out_dir")
    tr.add_argument("--rescan", action="store_true", help="scan the video for panels again")
    tr.add_argument("--bugs-only", action="store_true",
                    help="only recompute creature caps and the split of creature pokos (no video)")
    bt = sub.add_parser("batch", help="process every downloaded run not done yet (run, judge, treasures), then the site")
    bt.add_argument("--manifest", default="data/videos/manifest.json")
    bt.add_argument("--out", default="data/output")
    bt.add_argument("--jobs", type=int, default=4, help="runs processed at the same time")
    bt.add_argument("--kind", default="pod", help="judge type for new runs")
    st = sub.add_parser("site", help="write index.html over every judged run, and refresh each run's page")
    st.add_argument("--root", default="data/output")
    dt = sub.add_parser("details", help="rebuild a run's detection page with tracking pictures, the comedown and landing views, and the layout with them outlined")
    dt.add_argument("out_dir")
    dt.add_argument("--force", action="store_true", help="redo pictures that already exist")
    rd = sub.add_parser("redo", help="re-read a finished run's non-high sublevels with the current detector and link the run again")
    rd.add_argument("out_dir")
    rd.add_argument("--frames", default=None, help="only these entries (comma-separated seeds.json frames)")
    rd.add_argument("--redraw", action="store_true", help="draw every layout again, not only missing ones")
    pb = sub.add_parser("publish", help="copy the built site into data/pages and push it to the gh-pages branch")
    pb.add_argument("--root", default="data/output")
    pb.add_argument("--at-root", default="data/output_at", help="the All Treasures section's runs (built with site --root), published under at/")
    pb.add_argument("--wii-root", default="data/output_wii", help="the Wii Pay Off Debt section's runs (built with site --root), published under wii/")
    pb.add_argument("--out", default="data/pages")
    pb.add_argument("--no-push", action="store_true", help="only copy the files")
    ja = sub.add_parser("i18n", help="list the English on a built site (e.g. data/pages) that the Japanese table lacks")
    ja.add_argument("site_dir", nargs="?", default="data/pages")
    dg = sub.add_parser("debug", help="debug image of the letter tracking and fall fit for one entry screen")
    dg.add_argument("video")
    dg.add_argument("--frame", type=int, required=True, help="a frame inside the entry screen (seeds.json 'frame')")
    dg.add_argument("--feed", default=None, help="x0,y0,x1,y1 (default: detect)")
    dg.add_argument("--out", default=None)
    args = ap.parse_args(argv)

    if args.cmd == "redo":
        from . import redo
        frames = {int(f) for f in args.frames.split(",")} if args.frames else None

        def progress(e, r, ok):
            if e is None:            # a message from the route rescue
                return log(r)
            log(f"  {e['cave']} {e['sublevel']}: {e['confidence']} -> {r.confidence}"
                + (" (kept)" if ok else " (not kept)"))
        changed = redo.redo(args.out_dir, frames=frames, progress=progress)
        log(f"{len(changed)} sublevel(s) changed; run judge, treasures and details next")
        return 0

    if args.cmd == "details":
        from . import details
        out = Path(args.out_dir)
        cavegen.set_region_for(json.loads((out / "seeds.json").read_text(encoding="utf-8"))["entries"])
        page = details.write(out, force=args.force,
                             progress=lambda i, n, r: log(f"  {i}/{n} {r['cave']} {r.get('sublevel')}"))
        log(f"details: {page}")
        return 0

    if args.cmd == "publish":
        from . import site
        out = site.export(args.root, args.out, args.at_root, args.wii_root)
        log(f"exported: {out}")
        if not args.no_push:
            site.publish(out)
            log("pushed to gh-pages")
        return 0

    if args.cmd == "i18n":
        from . import i18n
        missing = i18n.check(Path(args.site_dir))
        for k in missing:
            print(k)
        log(f"{len(missing)} missing; add them to ja_table.py (or its KEEP list)")
        return 1 if missing else 0

    if args.cmd == "debug":
        from . import debug
        feed = Feed(*map(int, args.feed.split(","))) if args.feed else None
        log(f"debug: {debug.render(args.video, args.frame, feed, args.out)}")
        return 0

    if args.cmd == "treasures":
        from . import treasures
        out = Path(args.out_dir)
        if args.bugs_only:
            counts = treasures.refresh_bugs(out)
            clipped = sum(v.get("bug_clipped") or 0 for v in counts.values())
            log(f"  creature pokos {sum(v.get('bug_pokos') or 0 for v in counts.values()):.0f}, clipped {clipped}")
            return 0
        have = treasures.load(out)
        # older scans only looked between sublevels of one cave (no final floors, no surface)
        # rescan when the entries moved (a re-detect can shift entry frames, and the scan is keyed by them)
        frames = {str(e["frame"]) for e in json.loads((out / "seeds.json").read_text(encoding="utf-8"))["entries"] if e.get("cave")}
        stale = frames != {k for k, v in (have or {}).items() if v.get("cave") not in (None, "surface")}
        if args.rescan or not have or stale or any("window" not in v and v.get("cave") != "surface" for v in have.values()):
            treasures.count_run(out, progress=lambda i, n: log(f"  scanning {100 * i / max(n, 1):4.1f}%"))
        treasures.read_values(out, progress=lambda i, n, v: log(
            f"  {v['cave']} {v['sublevel']}: treasures {[c[0] if c else '?' for c in v['collected']]}"))
        counts = treasures.read_totals(out)
        for v in counts.values():
            if v.get("window"):
                log(f"  {v['cave']} {v['sublevel']}: {v.get('pokos')} pokos "
                    f"({v.get('treasure_pokos')} treasure + {v.get('bug_pokos')} creature)")
        return 0

    if args.cmd == "batch":
        return _batch(args)

    if args.cmd == "site":
        from . import site
        log(f"site: {site.build(args.root)}")
        return 0

    if args.cmd == "render":
        out = Path(args.out_dir)
        entries = json.loads((out / "seeds.json").read_text(encoding="utf-8"))["entries"]
        cavegen.set_region_for(entries)
        for e in entries:
            dest = out / "img" / f"layout_{e['frame']}_{e['cave']}-{e['sublevel']}.png"
            seeded = e.get("layout_seed") and e.get("sublevel") and e.get("confidence") in ("high", "medium")
            if seeded and (args.redraw or not dest.exists()):
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
                  meta={"run": run}, render=not args.no_render,
                  # a manifest entry may pin the game area ("feed": [x0, y0, x1, y1]) when
                  # detection gets it wrong, e.g. a wide splits panel next to a 4:3 game
                  feed=Feed(*entry["feed"]) if entry.get("feed") else None)
    return 0


def _batch(args) -> int:
    """One subprocess per run (isolated, parallel): detect seeds, judge, count treasures."""
    import subprocess
    from concurrent.futures import ThreadPoolExecutor

    manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))["runs"]
    todo = []
    for run_id, entry in manifest.items():
        if entry.get("status") != "ok":
            continue
        out = Path(args.out) / Path(entry["download"]["path"]).stem
        if not (out / "seeds.json").exists() or not (out / "judge.json").exists() or not (out / "treasures.json").exists():
            todo.append((run_id, out))
    log(f"{len(todo)} run(s) to process with {args.jobs} job(s)")
    py = [sys.executable, "-m", "p2seeds"]

    def one(item):
        run_id, out = item
        logf = out.parent / f"{out.name}.log"
        out.parent.mkdir(parents=True, exist_ok=True)
        steps = []
        if not (out / "seeds.json").exists():
            steps.append(py + ["run", "--manifest", args.manifest, "--out", args.out, "--only", run_id])
        steps.append(py + ["judge", str(out), "--kind", args.kind])
        steps.append(py + ["treasures", str(out)])
        with open(logf, "a", encoding="utf-8") as fh:
            for cmd in steps:
                if subprocess.run(cmd, stdout=fh, stderr=subprocess.STDOUT).returncode != 0:
                    return run_id, f"failed at `{' '.join(cmd[2:4])}` (see {logf})"
        return run_id, "ok"

    failed = 0
    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        for run_id, status in pool.map(one, todo):
            log(f"  {run_id}: {status}")
            failed += status != "ok"
    from . import site
    log(f"site: {site.build(args.out)}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
