"""Leaderboard resolution against canned API responses (no network)."""

import pytest

from srcom_videos.api import SrcomError
from srcom_videos.download import DownloadOptions
from srcom_videos.leaderboard import top_runs


class FakeClient:
    def __init__(self, responses):
        self.responses = responses
        self.calls = []

    def get_data(self, path, params=None):
        self.calls.append((path, params))
        if path == "games" and (params or {}).get("abbreviation") == "pikmin2":
            return [GAME]
        if path == "games":
            return []
        return self.responses[path]


GAME = {"id": "g1", "abbreviation": "pikmin2", "names": {"international": "Pikmin 2"}}
CATS = [{"id": "c1", "name": "Pay Off Debt"}, {"id": "c2", "name": "All Treasures"}]
VARS = [
    {"id": "v1", "name": "Console (PoD)", "category": "c1",
     "values": {"values": {"gc": {"label": "GC"}, "sw": {"label": "Switch"}}}},
    {"id": "v2", "name": "Console (AT)", "category": "c2",
     "values": {"values": {"gc2": {"label": "GC"}}}},
]


def _run(rid, place_time, players, links):
    return {
        "id": rid, "weblink": f"https://speedrun.com/run/{rid}", "game": "g1", "category": "c1",
        "date": "2024-01-01", "times": {"primary_t": place_time}, "players": players,
        "system": {"platform": "p1", "region": "r1", "emulated": False},
        "values": {"v1": "gc"}, "videos": {"links": [{"uri": u} for u in links]} if links else None,
    }


BOARD = {
    "runs": [
        {"place": 2, "run": _run("b", 5500, [{"rel": "guest", "name": "Guesty"}], [])},
        {"place": 1, "run": _run("a", 5425, [{"rel": "user", "id": "u1"}], ["https://youtu.be/k0n-_1TBMoM?si=x"])},
    ],
    "players": {"data": [{"rel": "user", "id": "u1", "names": {"international": "JackDraz"}}]},
    "platforms": {"data": [{"id": "p1", "name": "GameCube"}]},
    "regions": {"data": [{"id": "r1", "name": "USA / NTSC"}]},
}


def make_client():
    return FakeClient({
        "games/g1/categories": CATS,
        "games/g1/variables": VARS,
        "leaderboards/g1/category/c1": BOARD,
    })


def test_top_runs_resolves_names_and_sorts():
    client = make_client()
    runs = top_runs(client, "pikmin2", "pay off debt", {"Console (PoD)": "gc"}, n=5)
    assert [r.id for r in runs] == ["a", "b"]
    first = runs[0]
    assert first.player_names == "JackDraz"
    assert first.platform == "GameCube" and first.region == "USA / NTSC"
    assert first.videos[0].canonical_url == "https://www.youtube.com/watch?v=k0n-_1TBMoM"
    assert runs[1].videos == [] and runs[1].player_names == "Guesty"
    board_params = client.calls[-1][1]
    assert board_params["var-v1"] == "gc" and board_params["top"] == 5


def test_variable_from_other_category_is_rejected():
    with pytest.raises(SrcomError):
        top_runs(make_client(), "pikmin2", "Pay Off Debt", {"Console (AT)": "GC"})


def test_slug_is_filesystem_safe():
    runs = top_runs(make_client(), "pikmin2", "c1")
    assert runs[0].slug() == "01_JackDraz_a"


def test_format_selector_caps_height_and_fps():
    sel = DownloadOptions(max_height=240, max_fps=30).format_selector()
    assert sel.split("/")[0] == "bv*[height<=240][fps<=30][vcodec^=avc1]"
    assert all("[height<=240]" in part for part in sel.split("/"))
