"""Download videos small with yt-dlp: capped resolution and frame rate, no audio.

YouTube serves its 480p-and-below renditions at 30 fps even for 60 fps uploads,
and Twitch offers 480p30/360p30/160p30, so normally a stream is picked that
already fits and nothing is re-encoded. ffmpeg (bundled by imageio-ffmpeg) is
only used to drop audio from combined streams, to lower the frame rate when no
fitting stream exists, and to cut clips.
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path

import imageio_ffmpeg
import yt_dlp


def ffmpeg_exe() -> str:
    return shutil.which("ffmpeg") or imageio_ffmpeg.get_ffmpeg_exe()


@dataclass
class DownloadOptions:
    max_height: int = 480
    max_fps: int = 30
    video_only: bool = True
    prefer_codec: str = "avc1"           # H.264 decodes everywhere, including OpenCV
    max_filesize: int | None = None      # bytes; yt-dlp skips anything larger
    js_runtime: str | None = "node"      # yt-dlp needs a JS runtime for YouTube
    quiet: bool = True

    def format_selector(self) -> str:
        h, f = self.max_height, self.max_fps
        fit = f"[height<={h}][fps<={f}]"
        choices = [
            f"bv*{fit}[vcodec^={self.prefer_codec}]" if self.prefer_codec else None,
            f"bv*{fit}",
            f"b{fit}",               # combined audio+video (e.g. Twitch); audio dropped afterwards
            f"bv*[height<={h}]",     # frame rate too high; re-encoded afterwards
            f"b[height<={h}]",
        ]
        return "/".join(c for c in choices if c)


@dataclass
class DownloadResult:
    path: str
    source_url: str
    format_id: str | None
    width: int | None
    height: int | None
    fps: float | None
    vcodec: str | None
    filesize: int
    postprocessed: list[str]

    def to_dict(self) -> dict:
        return asdict(self)


def download_video(url: str, out_dir: str | Path, stem: str, opts: DownloadOptions | None = None) -> DownloadResult:
    """Download `url` to `out_dir/stem.<ext>` (skipped if it already exists)."""
    opts = opts or DownloadOptions()
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    existing = [p for p in out_dir.glob(f"{stem}.*") if p.suffix not in (".part", ".ytdl", ".json")]
    if existing:
        return _describe(existing[0], url, None, [])

    ydl_opts = {
        "format": opts.format_selector(),
        "outtmpl": str(out_dir / f"{stem}.%(ext)s"),
        "ffmpeg_location": ffmpeg_exe(),
        "quiet": opts.quiet,
        "noprogress": opts.quiet,
        "continuedl": True,
        "retries": 10,
        "fragment_retries": 10,
        "noplaylist": True,
    }
    if opts.max_filesize:
        ydl_opts["max_filesize"] = opts.max_filesize
    if opts.js_runtime:
        ydl_opts["js_runtimes"] = {opts.js_runtime: {}}

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
    dl = (info.get("requested_downloads") or [info])[0]
    path = Path(dl.get("filepath") or dl["_filename"])

    done = []
    has_audio = (dl.get("acodec") or info.get("acodec") or "none") != "none"
    fps = dl.get("fps") or info.get("fps")
    too_fast = fps is not None and fps > opts.max_fps + 0.5
    if too_fast or (opts.video_only and has_audio):
        path = _postprocess(path, opts, reencode=too_fast)
        done.append(f"fps->{opts.max_fps}" if too_fast else "drop-audio")
        if too_fast:
            fps = opts.max_fps
    return _describe(path, url, dl.get("format_id"), done, dl, fps)


def _postprocess(path: Path, opts: DownloadOptions, reencode: bool) -> Path:
    out = path.with_name(path.stem + ".tmp.mp4")
    cmd = [ffmpeg_exe(), "-y", "-loglevel", "error", "-i", str(path)]
    if opts.video_only:
        cmd += ["-an"]
    if reencode:
        cmd += ["-vf", f"fps={opts.max_fps}", "-c:v", "libx264", "-preset", "veryfast", "-crf", "23"]
    else:
        cmd += ["-c:v", "copy"]
    subprocess.run(cmd + [str(out)], check=True)
    final = path.with_suffix(".mp4")
    path.unlink()
    out.replace(final)
    return final


def _describe(path: Path, url: str, format_id, done, dl: dict | None = None, fps=None) -> DownloadResult:
    dl = dl or {}
    return DownloadResult(
        path=str(path),
        source_url=url,
        format_id=format_id,
        width=dl.get("width"),
        height=dl.get("height"),
        fps=fps if fps is not None else dl.get("fps"),
        vcodec=dl.get("vcodec"),
        filesize=path.stat().st_size,
        postprocessed=done,
    )


def cut_clip(src: str | Path, start: float, end: float, dst: str | Path, reencode: bool = False) -> Path:
    """Copy the [start, end] seconds of `src` to `dst`.

    Without re-encoding the cut snaps to the keyframe before `start`, so the
    clip may begin slightly early; that is fine when padding with margins.
    """
    dst = Path(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    cmd = [ffmpeg_exe(), "-y", "-loglevel", "error", "-ss", f"{max(0.0, start):.3f}", "-to", f"{end:.3f}", "-i", str(src)]
    cmd += ["-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "18"] if reencode else ["-c", "copy"]
    subprocess.run(cmd + [str(dst)], check=True)
    return dst
