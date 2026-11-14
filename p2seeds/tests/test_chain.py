"""Window search, RNG distance, chain links, Japanese names and two-digit sublevels."""

import numpy as np

from p2seeds import caves, chain, letters_model, rng, search, templates
from p2seeds.analyze import split_digits


def test_forward_states_and_distance():
    s0 = 0x12345678
    st = rng.forward_states(s0, 1000)
    assert int(st[0]) == rng.next_seed(s0, 1)
    assert int(st[999]) == rng.next_seed(s0, 1000)
    assert rng.distance(s0, rng.next_seed(s0, 777_777)) == 777_777
    assert rng.distance(s0, rng.next_seed(s0, 5_000_000), limit=1_000_000) is None


def _measured(letter_seed, n, keep, noise=0.004, bias=0.03, seed=0):
    rs = np.random.default_rng(seed)
    v = np.array(rng.letter_velocities(letter_seed, n), float) + bias + rs.normal(0, noise, n)
    sig = np.full(n, np.nan)
    sig[keep] = 0.01
    v[[i for i in range(n) if i not in keep]] = np.nan
    return v, sig


def test_search_near_finds_the_next_sublevel_from_few_letters():
    prev_layout = 0x2F00BEEF
    truth = rng.next_seed(prev_layout, 61_234)
    v, sig = _measured(truth, 6, keep=[2, 3, 4, 5])
    cands = search.search_near(v, sig, prev_layout, 300_000)
    assert cands[0].letter_seed == truth & rng.MASK31
    assert cands[0].distance == 61_234
    # a link that close, with 4 letters, is very unlikely to be chance
    assert chain.link_chance(cands[0], sig) < 1e-2


def test_link_chance_grows_with_distance_and_noise():
    v, sig = _measured(0x1111, 6, keep=[1, 2, 3, 4])
    c = search.Candidate(0x1111, 1.0, 0.0, np.where(np.isfinite(sig), 0.0, np.nan), distance=20_000)
    near = chain.link_chance(c, sig)
    c.distance = 900_000
    assert chain.link_chance(c, sig) > 40 * near
    assert chain.link_chance(c, sig * 10) > chain.link_chance(c, sig)


def test_chain_links_three_entries_with_short_names():
    """Three Japanese-style entries with 3-4 letters each: no global search could settle
    them, but each sits a short RNG distance after the previous one."""

    class R:
        def __init__(self, seed, n, keep, s):
            self.num_chars, self.cave, self.sublevel = n, "EC", 1
            v, sig = _measured(seed, n, keep, seed=s)

            class F:
                pass
            self.fit = F()
            self.fit.v, self.fit.sigma, self.fit.rms_px = v, sig, 0.06
            self.letter_seed = self.layout_seed = None
            self.confidence, self.note = "low", ""
            self.candidates = [search.Candidate(seed & rng.MASK31, 0.5, 0.0,
                                                np.where(np.isfinite(sig), 0.0, np.nan))]

    s1 = 0x0ABC1234
    s2 = rng.next_seed(letters_model.layout_seed(s1, 6), 25_000)
    s3 = rng.next_seed(letters_model.layout_seed(s2, 6), 40_000)
    results = [R(s1, 6, [1, 2, 3, 4], 1), R(s2, 6, [2, 3, 4, 5], 2), R(s3, 6, [1, 3, 4, 5], 3)]
    chain.link(results)
    assert [r.letter_seed for r in results] == [s & rng.MASK31 for s in (s1, s2, s3)]
    assert all(r.confidence in ("high", "medium") for r in results)
    assert results[1].chain_dist == 25_000 and results[2].chain_dist == 40_000


def test_japanese_names_have_glyphs():
    assert len(caves.CAVES_JA) == 14
    for c in caves.CAVES_JA:
        for ch in c.name:
            assert templates.raw_glyph(ch).shape[0] == 40
    assert caves.CAVES_JA[0].label == "Emergence Cave"


def test_split_digits_two_and_one():
    one = np.zeros((20, 10), np.float32)
    one[:, 4:6] = 1
    two = np.zeros((20, 30), np.float32)
    two[:, 3:6] = 1
    two[:, 15:25] = 1
    assert len(split_digits(one)) == 1
    assert len(split_digits(two)) == 2


def test_neighbors_found_separately_promote_each_other():
    class R:
        def __init__(self, seed, conf):
            self.num_chars, self.cave, self.sublevel, self.fit = 6, "BK", 1, None
            self.letter_seed = seed & rng.MASK31
            self.layout_seed = letters_model.layout_seed(seed, 6)
            self.confidence, self.note, self.candidates = conf, "", []

    a = R(0x05A5A5A5, "medium")
    b = R(rng.next_seed(a.layout_seed, 900), "medium")
    far = R(0x7123_4567, "medium")
    results = [a, b, far]
    chain.link(results)
    assert b.chain_dist == 900
    assert a.confidence == b.confidence == "high"
    assert far.confidence == "medium" and far.chain_dist is None


def test_digit_crop_keeps_a_leading_one_in_japanese():
    img = np.zeros((100, 200), np.uint8)
    img[55:65, 20:60] = 255          # a wide glyph (下)
    img[52:68, 100:104] = 255        # "1"
    img[52:68, 112:126] = 255        # "2", further from the "1" than the grouping gap
    from p2seeds.analyze import digit_crop
    ja, en = digit_crop(img, "ja"), digit_crop(img, "en")
    assert ja.shape[1] > en.shape[1] >= 10
    assert len(split_digits(ja)) == 2


def test_cavegen_region_follows_the_run_language():
    from p2seeds import cavegen
    cavegen.set_region_for([{"lang": "ja"}, {"lang": "ja"}])
    assert cavegen._region_args() == ["-region", "jpn"]
    cavegen.set_region_for([{"lang": "en"}])
    assert cavegen._region_args() == []
