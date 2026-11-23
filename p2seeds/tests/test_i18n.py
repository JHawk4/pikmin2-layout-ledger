"""The Japanese pages: the table is complete and well formed, and i18n.js reads the pages as i18n.py does."""

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from p2seeds import i18n, ja_table, theme

PAGES = Path(__file__).resolve().parents[2] / "data" / "pages"      # the built site, when there is one


def _tags(s):
    return sorted(re.findall(r"</?[a-z]+>", s))


def test_every_entry_keeps_its_placeholders_and_tags():
    for en, ja in ja_table.T.items():
        assert set(re.findall(r"\{\d+\}", ja)) <= set(re.findall(r"\{\d+\}", en)), en
        assert _tags(en) == _tags(ja), en           # i18n.js reuses the page's own tags in the same order
        assert not re.search(r"[A-Za-z]{4,}", re.sub(r"<[^>]*>|\{\d+\}|CaveGen3?|Gecko|Dolphin|Nintendont|speedrun\.com|"
                                                       r"GameCube|Wii U?|Google|Discord|Meeo|Cheats|USB Loader GX|Gecko OS|"
                                                       r"GPV\w+|R92\w+|github\.com\S*|docs/\S*|Properties|Codes|Add New Code|"
                                                       r"judge2|Total|Ctrl|PAL", " ", ja)), (en, ja)


def test_keys_are_written_as_the_pages_template_them():
    for en in ja_table.T:
        assert i18n.template(en)[0] == en or "{" in en, en      # no stray numbers or names left in a key


def test_template_turns_numbers_names_codes_and_seeds_into_placeholders():
    lex = i18n.Lexicon(["JackDraz"])
    key, parts = lex.template("280 pokos (+0 vs median): Rubber Ugly (180), medama yaki (100)")
    assert key == "{0} pokos ({1} vs median): {2} ({3}), {4} ({5})"
    assert parts == ["280", "+0", "Rubber Ugly", "180", "medama yaki", "100"]
    assert lex.template("SH 6 · JackDraz 1:30:25 · seed 0x1A2B3C4D")[0] == "{0} {1} · {2} {3} · seed {4}"
    assert lex.template("fire geysers and water")[1] == []          # internal names only before " (12)"
    assert lex.template("the judge2 score")[1] == []


def test_the_header_has_the_switch_and_finds_i18n_js_from_every_depth():
    assert 'id="lang-toggle"' in theme.header("", None, "runs", "pod")
    assert 'src="i18n.js"' in theme.header("", None, "runs", "pod")
    assert 'src="../i18n.js"' in theme.header("", None, "runs", "at")
    assert 'src="../../i18n.js"' in theme.header("../", "x", "judge", "wii")
    assert 'src="../i18n.js"' in theme.header("../", "x", "judge", "pod")


def test_fixed_pages_are_fully_translated():
    pages = [theme.apply(theme.suggest_page(), active="suggest"),
             theme.apply("<html><head><style></style></head><body><main></main></body></html>", category="at")]
    assert i18n.missing(pages) == []


@pytest.mark.skipif(not (PAGES / "index.html").exists(), reason="no built site in data/pages")
def test_the_built_site_is_fully_translated():
    # every section's pages and one run of each, as published (python -m p2seeds i18n data/pages checks it all)
    picks = []
    for sec in (PAGES, PAGES / "at", PAGES / "wii"):
        if not sec.exists():
            continue
        picks += sorted(sec.glob("*.html"))
        run = next((d for d in sorted(sec.iterdir()) if (d / "judge.html").exists()), None)
        if run:
            picks += [run / "judge.html", run / "report.html"]
    js = PAGES / "i18n.js"
    lex = i18n.Lexicon(i18n.js_data(js)["runners"]) if js.exists() else None
    missing = i18n.missing([p.read_text(encoding="utf-8") for p in picks if p.exists()], lex=lex)
    assert missing == [], "\n".join(missing[:40])


@pytest.mark.skipif(shutil.which("node") is None, reason="needs node")
def test_i18n_js_templates_and_translates_like_python(tmp_path):
    lex = i18n.Lexicon(["JackDraz", "iid01"])
    samples = ["280 pokos: Rubber Ugly (180) + about 12 from creatures (estimated)",
               "SH 6 · JackDraz 1:30:25 · 12:04", "layout seed 0x1A2B3C4D", "Took 61.2 s (median run 58.0)",
               "chess queen black or Sunseed Berry (30)", "iid01 (45 plays)", "Seed 7ADF15EE · video 0:12:01",
               "timed by the video clock, timing step of 1 frame at fall frame 9 seed confirmed by its neighbor's",
               "the judge2 score of Bulblax Kingdom, −3.5 s"]
    (tmp_path / "i18n.js").write_text(i18n.js(lex=lex), encoding="utf-8")
    (tmp_path / "run.js").write_text("""
globalThis.window = globalThis;
globalThis.location = { search: "" }; globalThis.navigator = { language: "en" };
globalThis.localStorage = { getItem: () => null, setItem() {} };
globalThis.document = { readyState: "complete", getElementById: () => null,
  documentElement: { lang: "", classList: { remove() {}, add() {} } } };
require("./i18n.js");
const samples = JSON.parse(require("fs").readFileSync(0, "utf8"));
console.log(JSON.stringify(samples.map(s => [window.ledgerI18n.template(s), window.ledgerI18n.tr(s)])));
""", encoding="utf-8")
    out = subprocess.run(["node", str(tmp_path / "run.js")], input=json.dumps(samples), capture_output=True, text=True,
                         encoding="utf-8", check=True).stdout
    table = i18n.load()["t"]
    for s, ((key, parts), ja) in zip(samples, json.loads(out)):
        assert [key, parts] == list(lex.template(s)), s
        if key in table:
            assert ja and not re.search(r"\{\d+\}", ja), (s, ja)
    by = {s: ja for s, (_, ja) in zip(samples, json.loads(out))}
    assert by["280 pokos: Rubber Ugly (180) + about 12 from creatures (estimated)"] == "280ポコ：天下一ブサイク（180） ＋原生生物から約12（推定）"
    assert by["SH 6 · JackDraz 1:30:25 · 12:04"] is None            # nothing to translate: names, codes and times stay
    assert by["timed by the video clock, timing step of 1 frame at fall frame 9 seed confirmed by its neighbor's"] == \
        "動画の時刻で計時、落下9フレーム目で1フレームのずれ、前後の階でシードを確認"
