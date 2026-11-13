"""Command line: list a leaderboard's top runs, or download their videos.

Examples:
  python -m srcom_videos list --game pikmin2 --category "Pay Off Debt" --var "Console (PoD)=GC" --top 5
  python -m srcom_videos download --game pikmin2 --category "Pay Off Debt" --var "Console (PoD)=GC" \\
      --top 5 --out data/videos --height 480 --fps 30
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .api import SrcomClient
from .download import DownloadOptions, download_video
from .leaderboard import top_runs
from .manifest import Manifest


def _parse_vars(pairs: list[str]) -> dict[str, str]:
    out = {}
    for p in pairs or []:
        name, sep, value = p.partition("=")
        if not sep:
            raise SystemExit(f"--var expects NAME=VALUE, got {p!r}")
        out[name.strip()] = value.strip()
    return out


def _fmt_time(sec: float) -> str:
    h, rem = divmod(int(round(sec)), 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="srcom_videos")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("list", "download"):
        p = sub.add_parser(name)
        p.add_argument("--game", required=True)
        p.add_argument("--category", required=True)
        p.add_argument("--var", action="append", default=[], help="NAME=VALUE, repeatable")
        p.add_argument("--top", type=int, default=5)
        p.add_argument("--cache", default="data/cache/srcom")
    d = sub.choices["download"]
    d.add_argument("--out", default="data/videos")
    d.add_argument("--height", type=int, default=480)
    d.add_argument("--fps", type=int, default=30)
    d.add_argument("--keep-audio", action="store_true")
    d.add_argument("--max-mb", type=int, default=None)
    d.add_argument("--manifest", default=None, help="default: <out>/manifest.json")
    args = ap.parse_args(argv)

    client = SrcomClient(cache_dir=args.cache)
    runs = top_runs(client, args.game, args.category, _parse_vars(args.var), args.top)

    if args.cmd == "list":
        for r in runs:
            links = " ".join(v.canonical_url for v in r.videos) or "(no video)"
            print(f"{r.place:>3}  {r.player_names:<20} {_fmt_time(r.time_seconds):>9}  {r.date}  {r.platform}/{r.region}  {links}")
        return 0

    out = Path(args.out)
    manifest = Manifest(args.manifest or out / "manifest.json")
    opts = DownloadOptions(
        max_height=args.height, max_fps=args.fps, video_only=not args.keep_audio,
        max_filesize=args.max_mb * 1024 * 1024 if args.max_mb else None, quiet=False,
    )
    failures = 0
    for r in runs:
        video = next((v for v in r.videos if v.host in ("youtube", "twitch")), None) or (r.videos[0] if r.videos else None)
        if video is None:
            manifest.update(r, status="no_video")
            print(f"[skip] #{r.place} {r.player_names}: no video")
            continue
        print(f"[get ] #{r.place} {r.player_names}: {video.canonical_url}")
        try:
            res = download_video(video.canonical_url, out, r.slug(), opts)
        except Exception as exc:  # yt-dlp raises many types; record and keep going
            failures += 1
            manifest.update(r, status="error", error=str(exc)[:500], video=video.canonical_url)
            print(f"[fail] #{r.place} {r.player_names}: {exc}", file=sys.stderr)
            continue
        manifest.update(r, status="ok", video=video.canonical_url, download=res.to_dict())
        print(f"[ ok ] {res.path}  {res.height}p {res.fps}fps {res.filesize / 1e6:.0f} MB")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
