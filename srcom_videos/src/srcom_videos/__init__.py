"""Fetch top runs from speedrun.com and download their videos small.

Nothing in this package is specific to one game.
"""

from .api import SrcomClient, SrcomError
from .download import DownloadOptions, DownloadResult, cut_clip, download_video
from .leaderboard import top_runs
from .links import parse_video_url
from .manifest import Manifest
from .models import Player, Run, VideoLink

__all__ = [
    "SrcomClient",
    "SrcomError",
    "DownloadOptions",
    "DownloadResult",
    "cut_clip",
    "download_video",
    "top_runs",
    "parse_video_url",
    "Manifest",
    "Player",
    "Run",
    "VideoLink",
]
