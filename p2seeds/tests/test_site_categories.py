"""The site's categories: All Treasures under at/, purple-farm visits left out of totals."""

import re

from p2seeds.ledger import judge_report, theme


def _e(cave, sub):
    return {"cave": cave, "sublevel": sub}


def test_only_the_last_visit_to_a_cave_counts():
    # a purple farm: BK 1-3, out, then the real descent BK 1-7; another cave in between
    es = [_e("SH", 6), _e("BK", 1), _e("BK", 2), _e("BK", 3), _e("BK", 1), _e("BK", 2), _e("BK", 7), _e("SCx", 1)]
    judge_report.mark_revisits(es)
    assert [bool(e.get("revisit")) for e in es] == [False, True, True, True, False, False, False, False]


def test_a_run_that_never_goes_back_has_no_revisits():
    es = [_e("EC", 1), _e("EC", 2), _e("HoB", 1), _e("HoB", 3), _e("HoB", 4)]     # HoB 2 unread: still one visit
    judge_report.mark_revisits(es)
    assert not any(e.get("revisit") for e in es)


def _links(h):
    return dict((label, href) for href, label in re.findall(r'<a href="([^"]+)"[^>]*>([^<]+)</a>', h))


def test_header_links_reach_both_sections_from_every_depth():
    # Pay Off Debt at the site root, All Treasures under at/
    pod_index = _links(theme.header("", None, "runs", "pod"))
    at_index = _links(theme.header("", None, "runs", "at"))
    at_run = _links(theme.header("../", "x", "judge", "at"))
    assert pod_index["All Treasures"] == "at/index.html" and pod_index["Pay Off Debt"] == "index.html"
    assert at_index["Pay Off Debt"] == "../index.html" and at_index["All Treasures"] == "../at/index.html"
    assert at_run["Pay Off Debt"] == "../../index.html" and at_run["All runs"] == "../index.html"
    assert at_run["Suggestion box"] == "../../suggest.html"
    assert "Pokos" in pod_index and "Pokos" not in at_index


def test_reheader_swaps_only_the_header():
    page = theme.apply("<html><head><style></style></head><body><main>x</main></body></html>", category="pod")
    again = theme.reheader(page, category="at")
    assert again.count('class="site-header"') == 1 and "<main>x</main>" in again
    assert 'aria-current=page>All Treasures' in again


def test_wii_section_has_its_own_folder_and_pokos(tmp_path):
    wii_index = _links(theme.header("", None, "runs", "wii"))
    wii_run = _links(theme.header("../", "x", "judge", "wii"))
    assert wii_index["Pay Off Debt (Wii)"] == "../wii/index.html" and wii_index["Pay Off Debt"] == "../index.html"
    assert wii_run["All Treasures"] == "../../at/index.html" and "Pokos" in wii_index
    # Wii runs are judged as Pay Off Debt; the section root's section.txt puts them in their own section
    (tmp_path / "section.txt").write_text("wii\n")
    (tmp_path / "run").mkdir()
    assert theme.category_of("pod", tmp_path) == "wii" and theme.category_of("pod", tmp_path / "run") == "wii"
    assert theme.category_of("pod") == "pod" and theme.category_of("at", tmp_path.parent) == "at"
