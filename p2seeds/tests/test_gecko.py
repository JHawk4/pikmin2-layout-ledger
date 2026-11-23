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
        assert v.hook == v.create_map_parts_list + (0x30 if v.game_id.startswith("R92") else 0x2C)
    assert gecko.BY_KEY["R92E01"].hook == 0x802D0F00 and gecko.body(gecko.BY_KEY["R92E01"])[-1] == gecko.LI_R27_0
    assert gecko.BY_KEY["GPVE01_D17"].hook == 0x8024C118        # where Meeo's set-seed code hooks
    assert USA.hook == 0x8024C138


def test_keys_put_the_floor_in_the_cave_id():
    assert gecko.key("BK", 1) == 0x66003033          # 'f_03', floor 0
    assert gecko.key("SCx", 9) == 0x74083032         # 't_02', floor 8
    assert len({gecko.key(c, s) for c in gecko.CAVE_IDS for s in range(1, 16)}) == 14 * 15


def _e(cave, sub, seed, conf="high"):
    return {"cave": cave, "sublevel": sub, "layout_seed": seed, "letter_seed": seed, "confidence": conf}


def test_table_takes_each_sublevels_first_trusted_visit():
    es = [_e("BK", 1, "0x80000001"), _e("BK", 2, "0x2", "low"), _e("BK", 1, "0x3"), _e("BK", 2, "0x4"),
          _e("SH", 1, "0x5", "medium"), {"cave": None, "sublevel": None}, _e("XX", 1, "0x6")]
    # bit 31 dropped; BK 2's first visit unread, so its second; lone medium SH 1 and unknown caves left out
    assert gecko.table(es) == [(gecko.key("BK", 1), 1), (gecko.key("BK", 2), 4)]


def test_code_layout():
    pairs = [(gecko.key("EC", 1), 0x1234), (gecko.key("EC", 2), 0x7FFFFFFF)]
    w = gecko.words(USA, pairs)
    lines = gecko.code(USA, pairs).splitlines()
    assert lines[0] == f"C224C138 {len(w) // 2:08X}" and len(lines) == len(w) // 2 + 1
    assert w[-1] == 0 and len(w) % 2 == 0
    assert w[0] == 0x48000001 | (4 + 4 * 5)          # bl over 2 entries and the end marker
    assert w[1:6] == [pairs[0][0], 0x1234, pairs[1][0], 0x7FFFFFFF, 0]
    assert w[6:6 + len(gecko.body(USA))] == gecko.body(USA)
    assert gecko.body(USA)[-1] == gecko.LI_R26_0
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


def _run(v, pairs, cave, floor, mem, story=True, sound=True, played=None):
    """Run the code once on a tiny PowerPC model (instructions decoded by capstone), as at the
    hook: returns the rand state afterwards. `mem` (address -> word) carries the table between
    calls, as the game's RAM does."""
    capstone = pytest.importorskip("capstone")
    md = capstone.Cs(capstone.CS_ARCH_PPC, capstone.CS_MODE_32 | capstone.CS_MODE_BIG_ENDIAN)
    base, section = 0x80001800, 0x81000000
    w = gecko.words(v, pairs)
    for i, x in enumerate(w[:-1]):
        mem.setdefault(base + 4 * i, x)
    mem.update({v.game_system: 0x80F00000, 0x80F00000 + 0x58: section,
                section: v.single_vtable if story else 0x80400000, v.rand_next: 0xDEAD,
                v.sys_if: 0x80E00000 if sound else 0})
    played = [] if played is None else played
    getters = {v.get_cave_id: int.from_bytes(gecko.CAVE_IDS[cave].encode(), "big"), v.get_curr_floor: floor}
    r, lr, ctr, cr, pc = [0] * 32, 0, 0, 0, base
    reg = lambda t: int(t.strip().lstrip("r"))
    for _ in range(10000):
        if pc == base + 4 * (len(w) - 1):
            return mem[v.rand_next]
        x = mem[pc]
        ins = next(md.disasm(x.to_bytes(4, "big"), pc))
        op, a = ins.mnemonic, [t.strip() for t in ins.op_str.split(",")] if ins.op_str else []
        nxt = pc + 4
        if op == "nop": pass
        elif op == "bl": lr, nxt = pc + 4, int(a[0], 0)
        elif op == "b": nxt = int(a[0], 0)
        elif op == "mflr": r[reg(a[0])] = lr
        elif op == "lis": r[reg(a[0])] = (int(a[1], 0) << 16) & 0xFFFFFFFF
        elif op == "li": r[reg(a[0])] = int(a[1], 0) & 0xFFFFFFFF
        elif op == "addi": r[reg(a[0])] = (r[reg(a[1])] + int(a[2], 0)) & 0xFFFFFFFF
        elif op in ("lwz", "stw"):
            off, ra = a[1].rstrip(")").split("(")
            addr = (r[reg(ra)] + int(off, 0)) & 0xFFFFFFFF
            if op == "lwz": r[reg(a[0])] = mem.get(addr, 0)
            else: mem[addr] = r[reg(a[0])]
        elif op in ("cmpwi", "cmpw"):
            s32 = lambda y: y - (1 << 32) if y & 0x80000000 else y
            lhs, rhs = s32(r[reg(a[0])]), (int(a[1], 0) if op == "cmpwi" else s32(r[reg(a[1])]))
            cr = 0 if lhs < rhs else 1 if lhs > rhs else 2
        elif op in ("beq", "bne"):
            if (cr == 2) == (op == "beq"): nxt = int(a[0], 0)
        elif op == "mr": r[reg(a[0])] = r[reg(a[1])]
        elif op == "mtctr": ctr = r[reg(a[0])]
        elif op == "bctrl":
            if ctr == v.play_system_se:
                played.append((r[3], r[4], r[5]))
                r[3:13] = [0x5EAD] * 10                 # a real call clobbers the volatile registers
            else:
                r[3] = getters[ctr]
        elif op == "rlwimi":
            ra, rs, sh, mb, me = reg(a[0]), reg(a[1]), *(int(t, 0) for t in a[2:])
            rot = ((r[rs] << sh) | (r[rs] >> (32 - sh))) & 0xFFFFFFFF if sh else r[rs]
            mask = sum(1 << (31 - i) for i in range(mb, me + 1))
            r[ra] = (rot & mask) | (r[ra] & ~mask & 0xFFFFFFFF)
        else:
            raise AssertionError(f"unexpected {op} {ins.op_str}")
        pc = nxt
    raise AssertionError("no return")


def test_simulated_code_sets_the_runs_seed_and_plays_the_sound():
    pairs = gecko.table([_e("BK", 1, "0x11"), _e("BK", 2, "0x12", "low"), _e("BK", 2, "0x22"), _e("BK", 1, "0x21"),
                         _e("SH", 3, "0x33")])
    for v in gecko.VERSIONS:
        mem, played = {}, []
        assert _run(v, pairs, "BK", 0, mem, played=played) == 0x11     # first visit's seed
        assert played == [(0x80E00000, gecko.SOUND, 0)]                # spSysIF->playSystemSe(0x183C, 0)
        assert _run(v, pairs, "BK", 1, mem, played=played) == 0x22     # first trusted visit
        assert _run(v, pairs, "BK", 0, mem, played=played) == 0x11     # and again on every later visit
        assert _run(v, pairs, "SH", 2, mem, played=played) == 0x33
        assert len(played) == 4
        assert _run(v, pairs, "SH", 3, mem, played=played) == 0xDEAD   # not in the run: no seed, no sound
        assert _run(v, pairs, "CoS", 0, mem, played=played) == 0xDEAD
        assert _run(v, pairs, "SH", 2, mem, story=False, played=played) == 0xDEAD     # not story mode
        assert _run(v, [], "SH", 2, {}, played=played) == 0xDEAD       # empty table
        assert len(played) == 4
        assert _run(v, pairs, "SH", 2, mem, sound=False, played=played) == 0x33   # no sound system: seed only
        assert len(played) == 4
