"""A Gecko code that replays a run's layouts: when the game generates a cave sublevel the run
has a trusted seed for, the code sets the RNG to that seed first (docs/gecko-code.md).

The hook is in Game::Cave::MapUnitGenerator::createMapPartsList, right after its prologue and
before its first rand() call (the shuffle of the map unit lists). Nothing draws from the RNG
between the start of map generation (the MapUnitGenerator constructor) and that point in story
mode, so the RNG state there is the seed CaveGen means (CaveGen's readme: "corresponds to Meeo's
setseed code", which hooks the same instruction on the USA demo build).

There the code reads Game::gameSystem->mSection; if it is the story mode section (its vtable is
SingleGameSection's), it calls SingleGameSection::getCaveID and ::getCurrFloor and looks up
(cave, floor) in a table placed inside the code; on a hit it stores the seed into rand()'s state.
Then it runs the instruction it replaced (li r26, 0) and returns.

Table entry: key, seed. key = the cave's ID32 (e.g. 'f_03') with its second byte replaced by
the floor index (0-based), so one word identifies the sublevel. A zero key ends the table.
"""

from __future__ import annotations

from dataclasses import dataclass

# Cave abbreviation (CaveGen) -> the game's cave ID (user/Abe/stages.txt; order as CaveGen's Parser).
CAVE_IDS = {
    "EC": "t_01", "SCx": "t_02", "FC": "t_03",
    "HoB": "f_01", "WFG": "f_02", "BK": "f_03", "SH": "f_04",
    "CoS": "y_01", "GK": "y_02", "SR": "y_03", "SC": "y_04",
    "CoC": "l_01", "HoH": "l_02", "DD": "l_03",
}
ORIGINAL = 0x3B400000          # li r26, 0 : the instruction at the hook, in every build


@dataclass(frozen=True)
class Version:
    key: str                   # the decomp's name for the build
    label: str
    game_id: str
    create_map_parts_list: int  # Game::Cave::MapUnitGenerator::createMapPartsList
    game_system: int           # Game::gameSystem (pointer)
    single_vtable: int         # __vt__Q24Game17SingleGameSection
    get_cave_id: int           # Game::SingleGameSection::getCaveID
    get_curr_floor: int        # Game::SingleGameSection::getCurrFloor
    rand_next: int             # rand()'s state (MSL rand.c `next`)
    checked: bool              # addresses and the hooked instruction read from a real copy of the game

    @property
    def hook(self) -> int:
        return self.create_map_parts_list + 0x2C


# Addresses from the projectPiki/pikmin2 decomp's symbol maps (config/<version>/symbols.txt).
VERSIONS = [
    Version("GPVE01", "USA (GPVE01)", "GPVE01", 0x8024C10C, 0x80515A68, 0x804B1350, 0x80153118, 0x80155F54, 0x805148A8, True),
    Version("GPVP01", "Europe / PAL (GPVP01)", "GPVP01", 0x8024C0F0, 0x80516768, 0x804B1EE0, 0x80153284, 0x801560C0, 0x805155A0, False),
    Version("GPVJ01", "Japan (GPVJ01)", "GPVJ01", 0x8024C770, 0x80517568, 0x804B2DB0, 0x8015310C, 0x80156388, 0x805163A8, False),
    Version("GPVE01_D17", "USA demo 1 (GPVE01, demo build 17)", "GPVE01", 0x8024C0EC, 0x805159A8, 0x804B1290, 0x801530F8, 0x80155F34, 0x805147E0, True),
    Version("GPVE01_D18", "USA demo 2 (GPVE01, demo build 18)", "GPVE01", 0x8024C0EC, 0x805158A8, 0x804B1190, 0x801530F8, 0x80155F34, 0x805146E0, False),
]
BY_KEY = {v.key: v for v in VERSIONS}

UNSUPPORTED = [
    ("Wii New Play Control! (R92E01, R92P01, R92J01)", "no symbol map yet, so no addresses to hook"),
    ("Any other build or a romhack", "the addresses differ; the code would do nothing or crash"),
]


# ---- a small PowerPC assembler: just what the code needs ----

def _ha(x: int) -> int:
    return ((x + 0x8000) >> 16) & 0xFFFF


def _lo(x: int) -> int:
    return x & 0xFFFF


def _d(op, rt, ra, imm):
    return (op << 26) | (rt << 21) | (ra << 16) | (imm & 0xFFFF)


def addi(rt, ra, imm): return _d(14, rt, ra, imm)
def li(rt, imm): return addi(rt, 0, imm)
def lis(rt, imm): return _d(15, rt, 0, imm)
def lwz(rt, off, ra): return _d(32, rt, ra, off)
def stw(rs, off, ra): return _d(36, rs, ra, off)
def cmpwi(ra, imm): return _d(11, 0, ra, imm)
def cmpw(ra, rb): return (31 << 26) | (ra << 16) | (rb << 11)
def mr(ra, rs): return (31 << 26) | (rs << 21) | (ra << 16) | (rs << 11) | (444 << 1)
def mflr(rt): return (31 << 26) | (rt << 21) | (8 << 16) | (339 << 1)
def mtctr(rs): return (31 << 26) | (rs << 21) | (9 << 16) | (467 << 1)
def rlwimi(ra, rs, sh, mb, me): return (20 << 26) | (rs << 21) | (ra << 16) | (sh << 11) | (mb << 6) | (me << 1)


BCTRL = 0x4E800421
NOP = 0x60000000


def b(off: int, link: bool = False) -> int:
    return (18 << 26) | (off & 0x03FFFFFC) | int(link)


def bc(bo: int, bi: int, off: int) -> int:
    return (16 << 26) | (bo << 21) | (bi << 16) | (off & 0xFFFC)


def beq(off): return bc(12, 2, off)
def bne(off): return bc(4, 2, off)


def body(v: Version) -> list[int]:
    """The code after the table (fixed for a version). It starts at the `bl` target, so the
    link register holds the table's address."""
    prog = [
        ("", mflr(11)),                                  # r11 = table
        ("", lis(12, _ha(v.game_system))), ("", lwz(12, _lo(v.game_system), 12)),
        ("", cmpwi(12, 0)), ("beq", "done"),
        ("", lwz(10, 0x58, 12)),                         # r10 = gameSystem->mSection
        ("", cmpwi(10, 0)), ("beq", "done"),
        ("", lwz(12, 0, 10)),                            # its vtable: story mode only
        ("", lis(9, _ha(v.single_vtable))), ("", addi(9, 9, _lo(v.single_vtable))),
        ("", cmpw(12, 9)), ("bne", "done"),
        ("", mr(3, 10)),
        ("", lis(12, _ha(v.get_cave_id))), ("", addi(12, 12, _lo(v.get_cave_id))),
        ("", mtctr(12)), ("", BCTRL),                    # getCaveID: lwz r3, x(r3); blr
        ("", mr(9, 3)),
        ("", mr(3, 10)),
        ("", lis(12, _ha(v.get_curr_floor))), ("", addi(12, 12, _lo(v.get_curr_floor))),
        ("", mtctr(12)), ("", BCTRL),                    # getCurrFloor: lwz r3, x(r3); blr
        ("", rlwimi(9, 3, 16, 8, 15)),                   # key: floor into the ID's second byte
        ("loop:", lwz(12, 0, 11)),
        ("", cmpwi(12, 0)), ("beq", "done"),
        ("", cmpw(12, 9)), ("beq", "hit"),
        ("", addi(11, 11, 8)),
        ("b", "loop"),
        ("hit:", lwz(12, 4, 11)),                       # r12 = seed
        ("", addi(8, 11, 8)),                            # a later visit of the same sublevel?
        ("scan:", lwz(7, 0, 8)),
        ("", cmpwi(7, 0)), ("beq", "use"),               # no: keep this entry for re-entries
        ("", cmpw(7, 9)), ("beq", "spend"),
        ("", addi(8, 8, 8)),
        ("b", "scan"),
        ("spend:", li(7, -1)), ("", stw(7, 0, 11)),      # yes: this visit's entry is used up
        ("use:", cmpwi(12, -1)), ("beq", "done"),        # a visit without a trusted seed: random
        ("", lis(11, _ha(v.rand_next))), ("", stw(12, _lo(v.rand_next), 11)),   # rand state = seed
        ("done:", ORIGINAL),
    ]
    labels = {tag[:-1]: 4 * i for i, (tag, _) in enumerate(prog) if tag.endswith(":")}
    out = []
    for i, (tag, x) in enumerate(prog):
        if tag in ("beq", "bne", "b"):
            off = labels[x] - 4 * i
            x = {"beq": beq, "bne": bne, "b": b}[tag](off)
        out.append(x)
    return out


def key(cave: str, sublevel: int) -> int:
    """Table key for a sublevel (1-based, as on the site)."""
    cid = int.from_bytes(CAVE_IDS[cave].encode("ascii"), "big")
    return (cid & 0xFF00FFFF) | (((sublevel - 1) & 0xFF) << 16)


RANDOM = 0xFFFFFFFF            # table seed for a visit with no trusted seed: leave the RNG alone
SPENT = 0xFFFFFFFF             # what the code writes over a used entry's key (never a real key)


def visits(entries) -> list[tuple[str, int, int, int]]:
    """(cave, sublevel, key, seed) for every visit of a sublevel, in the order played, for the
    sublevels with at least one trusted seed. A sublevel made more than once (All Treasures purple
    farms: BK 1-3, out, then BK 1-7) has one entry per visit; the code uses them in turn and keeps
    the last for any later visit. A visit without a trusted seed gets RANDOM, so the next visit
    still gets its own seed. `entries` are a judge.json's entries after judge_report.mark_neighbors."""
    from .judge_report import trusted
    out = []
    for e in entries:
        if e.get("cave") in CAVE_IDS and e.get("sublevel"):
            ok = e.get("layout_seed") and trusted(e)
            sub = int(e["sublevel"])
            out.append((e["cave"], sub, key(e["cave"], sub), int(str(e["layout_seed"]), 16) & 0x7FFFFFFF if ok else RANDOM))
    keep = {k for _, _, k, s in out if s != RANDOM}
    return [v for v in out if v[2] in keep]


def table(entries) -> list[tuple[int, int]]:
    """The code's table: (key, seed) per visit (see visits)."""
    return [(k, s) for _, _, k, s in visits(entries)]


def words(v: Version, pairs: list[tuple[int, int]]) -> list[int]:
    """The whole C2 payload: bl over the table, the table, its end, the body, and the slot the
    code handler fills with the branch back."""
    tab = [w for kv in pairs for w in kv] + [0]
    out = [b(4 + 4 * len(tab), link=True)] + tab + body(v)
    if len(out) % 2 == 0:
        out.append(NOP)
    return out + [0]


def code(v: Version, pairs: list[tuple[int, int]]) -> str:
    w = words(v, pairs)
    lines = [f"C2{v.hook & 0x01FFFFFF:06X} {len(w) // 2:08X}"]
    lines += [f"{w[i]:08X} {w[i + 1]:08X}" for i in range(0, len(w), 2)]
    return "\n".join(lines)
