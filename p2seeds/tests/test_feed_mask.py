import numpy as np

from p2seeds.feed import Feed


def test_mask_blanks_rectangle_in_crop():
    gray = np.full((360, 640), 200, np.uint8)
    feed = Feed(0, 0, 640, 360, [[0, 70, 120, 300]])
    out = feed.crop(gray)
    assert out[100, 50] == 0 and out[50, 50] == 200 and out[100, 200] == 200
    assert gray[100, 50] == 200            # the frame itself is untouched


def test_mask_relative_to_feed_and_round_trip():
    gray = np.full((100, 200), 9, np.uint8)
    feed = Feed(50, 10, 150, 90, [[40, 0, 60, 20]])
    out = feed.crop(gray)
    assert out.shape == (80, 100)
    assert out[5, 5] == 0 and out[5, 10] == 9 and out[15, 5] == 9
    assert Feed(*feed.to_list()) == feed
    assert Feed(1, 2, 3, 4).to_list() == [1, 2, 3, 4]
