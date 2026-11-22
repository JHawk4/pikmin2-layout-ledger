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


def test_linked_seed_out_of_order_is_dropped():
    """A seed linking filled in must sit between its settled neighbors in the RNG sequence."""
    from types import SimpleNamespace
    from p2seeds import chain, rng

    a = 0x1234567
    b = rng.next_seed(a, 100_000)
    good = rng.next_seed(a, 40_000)          # between a and b: kept
    bad = rng.next_seed(b, 50_000)           # past b: dropped

    def entry(seed, conf):
        return SimpleNamespace(letter_seed=seed, layout_seed=seed, confidence=conf, note="", candidates=[])

    for linked, kept in ((good, True), (bad, False)):
        rs = [entry(a, "high"), entry(None, "none"), entry(b, "high")]
        before = [(r.letter_seed, r.layout_seed, r.confidence, r.note, r.candidates) for r in rs]
        rs[1].letter_seed = rs[1].layout_seed = linked
        rs[1].confidence = "high"
        chain._check_order(rs, before, [0, 2])
        assert (rs[1].letter_seed == linked) is kept
        assert rs[1].confidence == ("high" if kept else "none")


def test_index_matches_stepping():
    """rng.index (CaveGen's nth_inv) gives exact distances; brute force agrees."""
    import random
    from p2seeds import rng
    rnd = random.Random(7)
    for _ in range(100):
        s, n = rnd.getrandbits(32), rnd.randrange(1, 5_000_000)
        assert rng.distance(s, rng.next_seed(s, n), limit=1 << 31) == n
        assert rng.index(rng.next_seed(0, n)) == n
    for _ in range(5):
        s, t = rnd.getrandbits(32), rnd.getrandbits(32)
        assert rng.distance(s, t, limit=1 << 21) == rng.distance_brute(s, t, limit=1 << 21)
    s = rnd.getrandbits(32)
    assert rng.distance(s, rng.next_seed(s, 1000), limit=999) is None


class _Entry:
    """A linking input: either a known seed, or a measured short name with no seed yet."""

    def __init__(self, seed, n, keep=None, s=0, known=False):
        self.num_chars, self.cave, self.sublevel = n, "SC", 1
        v, sig = _measured(seed, n, keep if keep is not None else list(range(n)), seed=s)

        class F:
            pass
        self.fit = F()
        self.fit.v, self.fit.sigma, self.fit.rms_px = v, sig * 1.1, 0.07
        self.candidates = []
        if known:
            self.letter_seed = seed & rng.MASK31
            self.layout_seed = letters_model.layout_seed(self.letter_seed, n)
            self.confidence, self.note = "high", ""
        else:
            self.letter_seed = self.layout_seed = None
            self.confidence, self.note = "low", ""


def test_bridge_fills_a_gap_of_weak_links():
    """Submerged Castle style: 4-letter names whose single links are a few percent likely to be
    chance (above WEAK_LINK), between two known seeds. Together the path is convincing."""
    a = 0x01234567
    seeds = [a]
    for d in (330_000, 140_000, 150_000, 120_000):
        seeds.append(rng.next_seed(letters_model.layout_seed(seeds[-1], 4), d))
    seeds.append(rng.next_seed(letters_model.layout_seed(seeds[-1], 4), 300_000))
    results = [_Entry(seeds[0], 7, known=True)] + \
              [_Entry(s, 4, s=i) for i, s in enumerate(seeds[1:-1])] + [_Entry(seeds[-1], 7, known=True)]
    results[1].num_chars = 4
    results[0].layout_seed = letters_model.layout_seed(results[0].letter_seed, 4)
    chain.link(results)
    got = [r.letter_seed for r in results[1:-1]]
    assert got == [s & rng.MASK31 for s in seeds[1:-1]]
    assert all("following the gap" in r.note for r in results[1:-1])


def test_link_chance_rejects_matches_right_after_the_previous_floor():
    v, sig = _measured(0x1111, 6, keep=[1, 2, 3, 4])
    c = search.Candidate(0x1111, 1.0, 0.0, np.where(np.isfinite(sig), 0.0, np.nan), distance=41)
    assert chain.link_chance(c, sig) == float("inf")


def test_a_wrong_read_between_two_agreeing_seeds_does_not_hide_them():
    """CurtisDN's Subterranean Complex at 360p: floors 1 and 3 read right, floor 2 read a wrong
    seed with medium confidence. Floors 1 and 3 must still back each other up, and floor 2's
    stray read must be dropped rather than kept as medium."""

    class R:
        def __init__(self, seed, conf):
            self.num_chars, self.cave, self.sublevel, self.fit = 7, "SCx", 1, None
            self.letter_seed = seed & rng.MASK31
            self.layout_seed = letters_model.layout_seed(seed, 7)
            self.confidence, self.note, self.candidates = conf, "", []

    a = R(0x446210F6, "medium")
    stray = R(0x3BF1D30C, "medium")
    c = R(rng.next_seed(a.layout_seed, 200_376), "medium")
    chain.link([a, stray, c])
    assert a.confidence == c.confidence == "high"
    assert stray.confidence == "low"


def test_redo_refreshes_the_saved_read_so_linking_keeps_the_seed_that_links():
    """08_CurtisDN's Hole of Beasts 2: the run's saved per-entry read (fits.json, an older
    detector) was a wrong medium seed that neither neighbour reaches, and linking could not find
    the right one from those mistracked letters, so the final seed stayed wrong. The current
    detector reads the right seed with high confidence. `redo.refresh` puts that read into
    fits.json, and linking the run again keeps it (it sits 32k steps after floor 1 and 24k before
    floor 3); updating seeds.json alone would be undone by the next relink."""
    import json
    from types import SimpleNamespace
    from p2seeds import redo

    n = 14
    a = 0x09DAD0DD
    truth = rng.next_seed(letters_model.layout_seed(a, n), 32_484)
    c = rng.next_seed(letters_model.layout_seed(truth, n), 24_125)
    wrong = 0x543C6EFD

    def known(seed, frame):
        return {"frame": frame, "cave": "HoB", "sublevel": 1, "lang": "en", "num_chars": n,
                "confidence": "high", "note": "", "letter_seed": seed & rng.MASK31,
                "layout_seed": letters_model.layout_seed(seed & rng.MASK31, n), "fit": None, "candidates": []}

    def read(seed, conf, keep, s):
        v, sig = _measured(seed, n, keep, seed=s)
        fit = SimpleNamespace(v=v, sigma=sig, rms_px=0.1)
        cand = search.Candidate(seed & rng.MASK31, 3.0, 0.03, np.where(np.isfinite(sig), 0.0, np.nan))
        return SimpleNamespace(settled_frame=2, cave_id="HoB", sublevel=2, lang="en", num_chars=n, fit=fit,
                               candidates=[cand], letter_seed=seed & rng.MASK31,
                               layout_seed=letters_model.layout_seed(seed & rng.MASK31, n),
                               confidence=conf, note="")

    def final(rows):
        rs = [chain.Saved(json.loads(json.dumps(r))) for r in rows]
        chain.link(rs)
        return rs[1]

    stale = chain.row(read(wrong, "medium", [0, 2, 3, 5, 7, 9, 11, 12, 13], 1))
    rows = [known(a, 1), stale, known(c, 3)]
    assert final(rows).letter_seed != truth & rng.MASK31      # the old read is never put right

    rows[1] = dict(stale)
    assert redo.refresh(rows[1], read(truth, "high", list(range(n)), 2))
    assert rows[1]["frame"] == 2 and redo.REDONE in rows[1]["note"]
    got = final(rows)
    assert got.letter_seed == truth & rng.MASK31 and got.confidence == "high"
    assert got.chain_dist == 32_484

    # a newer read that is less confident than the saved one does not replace it
    row = dict(stale)
    assert not redo.refresh(row, read(truth, "low", [1, 4], 3))
    assert row["letter_seed"] == wrong
