"""The Gecko code generator (gecko.py) and its page's script (gecko_page.JS)."""

import json
import shutil
import struct
import subprocess

import pytest

from p2seeds import gecko, gecko_page, theme

USA = gecko.BY_KEY["GPVE01"]


def test_encodings_match_instructions_read_from_the_game():
    # words read from the USA DOL (rand, srand, createMapPartsList) and from Meeo's set-seed code
    assert gecko.li(26, 0) == 0x3B400000
    assert gecko.mflr(0) == 0x7C0802A6
    assert gecko.mtctr(4) == 0x7C8903A6
    assert gecko.stw(3, -0x7DD8, 13) == 0x906D8228
    assert gecko.lwz(4, -0x7DD8, 13) == 0x808D8228
    assert gecko.lis(29, 0x4330) == 0x3FA04330
    assert gecko.mr(31, 3) == 0x7C7F1B78
    assert gecko.addi(0, 3, 0x4E6D) == 0x38034E6D
    assert gecko.b(-0x28) == 0x4BFFFFD8


def test_hook_is_createMapPartsList_after_its_prologue():
    for v in gecko.VERSIONS:
        assert v.hook == v.create_map_parts_list + 0x2C
    assert gecko.BY_KEY["GPVE01_D17"].hook == 0x8024C118        # where Meeo's set-seed code hooks
    assert USA.hook == 0x8024C138


def test_keys_put_the_floor_in_the_cave_id():
    assert gecko.key("BK", 1) == 0x66003033          # 'f_03', floor 0
    assert gecko.key("SCx", 9) == 0x74083032         # 't_02', floor 8
    assert len({gecko.key(c, s) for c in gecko.CAVE_IDS for s in range(1, 16)}) == 14 * 15


def _e(cave, sub, seed, conf="high"):
    return {"cave": cave, "sublevel": sub, "layout_seed": seed, "letter_seed": seed, "confidence": conf}


def test_table_keeps_trusted_seeds_and_the_last_visit():
    es = [_e("BK", 1, "0x1"), _e("BK", 2, "0x2", "low"), _e("BK", 1, "0x80000003"), _e("SH", 1, "0x4", "medium"),
          {"cave": None, "sublevel": None}, _e("XX", 1, "0x5")]
    t = gecko.table(es)
    assert t == [(gecko.key("BK", 1), 3)]            # bit 31 dropped; low, lone medium and unknown caves left out


def test_code_layout():
    pairs = [(gecko.key("EC", 1), 0x1234), (gecko.key("EC", 2), 0x7FFFFFFF)]
    w = gecko.words(USA, pairs)
    lines = gecko.code(USA, pairs).splitlines()
    assert lines[0] == f"C224C138 {len(w) // 2:08X}" and len(lines) == len(w) // 2 + 1
    assert w[-1] == 0 and len(w) % 2 == 0
    assert w[0] == 0x48000001 | (4 + 4 * 5)          # bl over 2 entries and the end marker
    assert w[1:6] == [pairs[0][0], 0x1234, pairs[1][0], 0x7FFFFFFF, 0]
    assert w[6:6 + len(gecko.body(USA))] == gecko.body(USA)
    assert gecko.body(USA)[-1] == gecko.ORIGINAL
    assert len(gecko.words(USA, [])) % 2 == 0


def test_body_disassembles_as_intended():
    capstone = pytest.importorskip("capstone")
    md = capstone.Cs(capstone.CS_ARCH_PPC, capstone.CS_MODE_32 | capstone.CS_MODE_BIG_ENDIAN)
    body = gecko.body(USA)
    ins = list(md.disasm(b"".join(struct.pack(">I", x) for x in body), 0))
    assert len(ins) == len(body)
    text = [f"{i.mnemonic} {i.op_str}".strip() for i in ins]
    assert text[0] == "mflr r11" and text[-1] == "li r26, 0"
    assert "lwz r12, 0x5a68(r12)" in text and "lwz r10, 0x58(r12)" in text and "stw r12, 0x48a8(r11)" in text
    end = 4 * (len(body) - 1)
    for i in ins:            # every branch lands inside the body
        if i.mnemonic in ("b", "beq", "bne"):
            assert 0 <= int(i.op_str.split()[-1], 16) <= end


def test_page_script_matches_python():
    node = shutil.which("node")
    if not node:
        pytest.skip("node not installed")
    pairs = [[gecko.key("HoB", 3), 0x23A06B6B], [gecko.key("DD", 14), 0x5]]
    vs = gecko_page.versions_data()
    script = gecko_page.JS.replace("JSON.parse(document.getElementById('gecko-versions').textContent)", json.dumps(vs)) \
        .replace("JSON.parse(document.getElementById('gecko-runs').textContent)", "[]") \
        .replace("const $ = id => document.getElementById(id);", "")
    script += f"\nfor (const v of V) console.log(JSON.stringify(code(v, {json.dumps([[0, 0, k, s] for k, s in pairs])})));"
    out = subprocess.run([node, "-e", script], capture_output=True, text=True, check=True).stdout.splitlines()
    assert [json.loads(x) for x in out] == [gecko.code(v, [tuple(p) for p in pairs]) for v in gecko.VERSIONS]


def test_nav_has_the_gecko_tab_at_the_site_root():
    h = theme.header("../", "x", "judge", "at")
    assert 'href="../../gecko.html"' in h
    assert 'href="gecko.html" aria-current=page' in theme.header("", None, "gecko", "pod")
