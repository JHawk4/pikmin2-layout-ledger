from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field


@dataclass
class VideoLink:
    url: str              # as written on speedrun.com
    canonical_url: str    # tracking params stripped, host normalized
    host: str             # "youtube", "twitch", or "other"
    video_id: str | None


@dataclass
class Player:
    id: str | None
    name: str


@dataclass
class Run:
    id: str
    place: int
    players: list[Player]
    time_seconds: float
    date: str | None
    weblink: str
    game_id: str
    category_id: str
    platform: str | None = None
    region: str | None = None
    emulated: bool = False
    videos: list[VideoLink] = field(default_factory=list)
    values: dict[str, str] = field(default_factory=dict)
    series: str | None = None   # None: a leaderboard place; "wr": position in the world-record history

    @property
    def player_names(self) -> str:
        return ",".join(p.name for p in self.players)

    def slug(self) -> str:
        """Filesystem-safe name, stable across runs: `03_playername_runid`."""
        name = re.sub(r"[^A-Za-z0-9_-]+", "-", self.player_names).strip("-") or "unknown"
        prefix = f"{self.series}{self.place:02d}" if self.series else f"{self.place:02d}"
        return f"{prefix}_{name}_{self.id}"

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(d: dict) -> "Run":
        d = dict(d)
        d["players"] = [Player(**p) for p in d.get("players", [])]
        d["videos"] = [VideoLink(**v) for v in d.get("videos", [])]
        return Run(**d)
