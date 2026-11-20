"""Probe: run the story-mode letter pipeline on a Challenge Mode floor title.

Adds the 30 challenge stage names (English, as CaveGen3 lists them) as candidate caves,
recognizes the title on a settled frame, tracks each letter through the title animation
and tries the letter fit. See docs/challenge-mode-seeds.md for what this shows.

    .venv/Scripts/python docs/challenge_mode_probe.py data/challenge/clips/clip.mp4 FRAME_SETTLED [x0,y0,x1,y1]
"""
from __future__ import annotations

import sys

import numpy as np

from p2seeds import analyze
from p2seeds.calibrate import calibrate
from p2seeds.caves import Cave
from p2seeds.feed import Feed, find_feed
from p2seeds.fit import fit
from p2seeds.track import track_all
from p2seeds.video import Video

CHALLENGE = ["Explorer's Cave", "Novice Training", "Lost Toy Box", "Creator's Garden", "Green Hole", "Hot House",
             "Brawny Abyss", "Red Chasm", "Trampled Garden", "Twilight Garden", "Cryptic Cavern", "Concrete Maze",
             "Collector's Room", "Dweevil Nest", "Cavernous Abyss", "Snack Pit", "Three Color Training",
             "Hazard Training", "Cave of Snarls", "Giant's Bath", "Rumbling Grotto", "Subterranean Lair",
             "Hidden Garden", "Abduction Den", "Secret Testing Range", "Breeding Ground", "Cave of Pain",
             "Bully Den", "Sniper Room", "Emperor's Realm"]
CM_CAVES = [Cave(name, f"CH{i + 1}", 1) for i, name in enumerate(CHALLENGE)]


def main(path: str, settled: int, feed_box: str | None = None) -> None:
    video = Video(path)
    if feed_box:
        x0, y0, x1, y1 = (int(v) for v in feed_box.split(","))
        feed = Feed(x0, y0, x1, y1)
    else:
        feed = find_feed(video)
    print("feed", feed)
    start = max(0, settled - 150)
    frames = [feed.crop(g) for g in video.frames(start, settled + 30)]
    cal = calibrate(frames[settled - start], caves=CM_CAVES)
    if cal is None:
        print("calibrate: no text found")
        return
    print(f"recognized {cal.cave.name!r} ({cal.cave.cavegen}) score {cal.score:.2f} runner-up {cal.runner_up}")
    tracks = track_all(frames, cal)
    for t in tracks:
        ok = t.score >= 0.55
        if not ok.any():
            print(f"  {t.ch!r}: never matched")
            continue
        y = t.y[ok]
        print(f"  {t.ch!r}: matched {ok.sum():3d}/{len(t.y)} frames, rest_y {t.rest_y:6.1f}, "
              f"y range {y.min():6.1f}..{y.max():6.1f} (moved {y.max() - y.min():4.1f} px)")
    try:
        f = fit(tracks, cal.cave.num_chars, s_guess=feed.height / 480.0)
        print("fit: v =", np.round(f.v, 2), "rms px", round(f.rms_px, 2))
    except ValueError as exc:
        print("fit failed:", exc)


if __name__ == "__main__":
    main(*sys.argv[1:2], int(sys.argv[2]), *(sys.argv[3:4]))
