"""Normalize and classify video URLs found on speedrun.com runs."""

from __future__ import annotations

import re
from urllib.parse import parse_qs, urlparse

from .models import VideoLink

_YT_ID = r"[A-Za-z0-9_-]{11}"


def parse_video_url(url: str) -> VideoLink:
    raw = url.strip()
    fixed = raw if re.match(r"^[a-z]+://", raw, re.I) else "https://" + raw
    u = urlparse(fixed)
    host = (u.hostname or "").lower().removeprefix("www.").removeprefix("m.")
    path = u.path.rstrip("/")
    query = parse_qs(u.query)

    yt_id = None
    if host == "youtu.be":
        yt_id = path.lstrip("/")
    elif host in ("youtube.com", "music.youtube.com"):
        if path == "/watch":
            yt_id = (query.get("v") or [None])[0]
        else:
            m = re.match(rf"^/(?:live|shorts|embed|v)/({_YT_ID})$", path)
            if m:
                yt_id = m.group(1)
    if yt_id and re.fullmatch(_YT_ID, yt_id):
        return VideoLink(raw, f"https://www.youtube.com/watch?v={yt_id}", "youtube", yt_id)

    if host.endswith("twitch.tv"):
        m = re.match(r"^(?:/[^/]+)?/(?:videos|v)/(\d+)$", path)
        if m:
            vid = m.group(1)
            return VideoLink(raw, f"https://www.twitch.tv/videos/{vid}", "twitch", vid)

    return VideoLink(raw, fixed, "other", None)
