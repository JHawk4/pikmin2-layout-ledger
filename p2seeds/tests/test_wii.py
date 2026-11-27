"""Wii / Wii U VC captures: the 4:3 picture stretched to 16:9, and a title that fades soon after landing."""

import cv2
import numpy as np

from p2seeds.story import templates
from p2seeds.story.calibrate import calibrate
from p2seeds.story.events import is_wide, normalize
from p2seeds.feed import Feed
from p2seeds.story.synth import render_fall


def _wide(frame: np.ndarray) -> np.ndarray:
    h = frame.shape[0]
    return cv2.resize(frame, (h * 16 // 9, h), interpolation=cv2.INTER_AREA)


def test_is_wide():
    assert is_wide(Feed(0, 0, 640, 360))
    assert not is_wide(Feed(0, 0, 480, 360))


def test_calibrates_a_stretched_name():
    frames = render_fall("White Flower Garden", 0x34759EF6, feed_h=360, feed_w=480)
    cal = calibrate(_wide(frames[-1]))
    assert cal is not None and cal.cave.name == "White Flower Garden"
    assert cal.sx > 1.15 * cal.sy          # the stretch is found, glyphs included
    assert cal.score - cal.runner_up[1] > 0.1


def test_normalize_restores_a_fading_title():
    frame = render_fall("Snagret Hole", 0x01234567, feed_h=360, feed_w=480)[-1]
    dim = (frame.astype(np.float32) * 0.6).astype(np.uint8)
    back = normalize(dim)
    assert abs(templates.bright_level(back) - templates.FULL_BRIGHT) < 0.05 * templates.FULL_BRIGHT
    assert normalize(np.zeros_like(frame)) is not None      # black stays black


def test_rescue_takes_a_cut_short_title_from_its_neighbours():
    from p2seeds.story.analyze import RESCUE_MARGIN_NEAR, EventResult, rescue_caves
    from p2seeds.story.events import Event

    def found(frame, cave):
        return EventResult(Event(frame, frame, 1), settled_frame=frame, cave_id=cave)

    hob2, hob4 = found(40261, "HoB"), found(43532, "HoB")
    cut = EventResult(Event(41110, 41270, 3), best_cave="HoB", cave_score=0.47, best_margin=0.04)
    assert rescue_caves([cut], [hob2, hob4]) == []                     # GameCube: margin too small
    assert rescue_caves([cut], [hob2, hob4], wide=True) == [(cut, "HoB", RESCUE_MARGIN_NEAR)]
    # not next to a HoB entry: no rescue
    assert rescue_caves([cut], [found(30000, "EC"), found(50000, "WFG")], wide=True) == []


def test_route_names_the_sublevels_between_two_entries():
    from p2seeds.story.analyze import EventResult
    from p2seeds.story.events import Event
    from p2seeds.story.route_rescue import _missing

    def at(cave, sub):
        return EventResult(Event(0, 0, 1), settled_frame=1, cave_id=cave, sublevel=sub)

    assert _missing(at("HoB", 4), at("WFG", 1)) == [("HoB", 5)]          # a final floor
    assert _missing(at("HoB", 1), at("HoB", 4)) == [("HoB", 2), ("HoB", 3)]
    assert _missing(at("HoB", 5), at("WFG", 2)) == [("WFG", 1)]
    assert _missing(None, at("EC", 2)) == [("EC", 1)]                    # from the surface
    assert _missing(at("WFG", 3), at("WFG", 1)) == []                    # a reset: nothing between
    # a cave with no entry in the run (mercysnow's HoB) may be in any gap
    assert _missing(at("EC", 2), at("WFG", 1), unseen=("HoB",)) == [("HoB", s) for s in range(1, 6)]
    # a sublevel number that is only a sequence guess does not bound the gap
    guess = at("BK", 1)
    guess.sublevel_source = "sequence"
    assert _missing(at("GK", 6), guess) == [("BK", s) for s in range(1, 8)]
    assert _missing(guess, at("BK", 7)) == [("BK", s) for s in range(1, 7)]


def test_rescued_sublevels_renumber_an_entry_whose_number_was_a_guess():
    from p2seeds.story.redo import resequence
    es = [{"frame": 100, "cave": "BK", "sublevel": 5, "sublevel_source": "digit"},
          {"frame": 900, "cave": "BK", "sublevel": 1, "sublevel_source": "sequence"},
          {"frame": 1500, "cave": "BK", "sublevel": 7, "sublevel_source": "digit (sequence said 2)"}]
    resequence(es)
    assert [e["sublevel"] for e in es] == [5, 6, 7]


def test_a_seedless_second_detection_does_not_split_a_sublevels_treasures():
    from p2seeds.story.treasures import sublevel_entries
    e = lambda f, c, s, seed=None: {"frame": f, "cave": c, "sublevel": s, "layout_seed": seed}
    entries = [e(1, "HoB", 4, "0x1"), e(2, "BK", 1), e(3, "HoB", 5, "0x2"),     # stray between 4 and 5
               e(4, "HoB", 6), e(5, "HoB", 7, "0x3")]                          # a real seedless sublevel
    assert [x["frame"] for x in sublevel_entries(entries)] == [1, 3, 4, 5]
