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
Then it runs the instruction it replaced (li r26, 0; li r27, 0 on the Wii) and returns.

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
LI_R26_0 = 0x3B400000          # li r26, 0 : the instruction at the hook on every GameCube build
LI_R27_0 = 0x3B600000          # li r27, 0 : on the Wii build


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
    hook_offset: int = 0x2C    # into createMapPartsList: after the prologue, before the first rand()
    original: int = LI_R26_0   # the instruction the hook replaces (the code runs it before returning)
    cave_id_slot: int = 0x78   # vtable slots (documentation; the code calls the getters directly)
    floor_slot: int = 0x58

    @property
    def hook(self) -> int:
        return self.create_map_parts_list + self.hook_offset


# Addresses from the projectPiki/pikmin2 decomp's symbol maps (config/<version>/symbols.txt).
VERSIONS = [
    Version("GPVE01", "USA (GPVE01)", "GPVE01", 0x8024C10C, 0x80515A68, 0x804B1350, 0x80153118, 0x80155F54, 0x805148A8, True),
    Version("GPVP01", "Europe / PAL (GPVP01)", "GPVP01", 0x8024C0F0, 0x80516768, 0x804B1EE0, 0x80153284, 0x801560C0, 0x805155A0, False),
    Version("GPVJ01", "Japan (GPVJ01)", "GPVJ01", 0x8024C770, 0x80517568, 0x804B2DB0, 0x8015310C, 0x80156388, 0x805163A8, False),
    Version("GPVE01_D17", "USA demo 1 (GPVE01, demo build 17)", "GPVE01", 0x8024C0EC, 0x805159A8, 0x804B1290, 0x801530F8, 0x80155F34, 0x805147E0, True),
    Version("GPVE01_D18", "USA demo 2 (GPVE01, demo build 18)", "GPVE01", 0x8024C0EC, 0x805158A8, 0x804B1190, 0x801530F8, 0x80155F34, 0x805146E0, False),
    # No decomp for the Wii: found in a RAM dump of the USA game (docs/gecko-code.md).
    Version("R92E01", "Wii New Play Control! USA (R92E01)", "R92E01", 0x802D0ED0, 0x8066C9F0, 0x80590E00, 0x801E63AC, 0x801E92A4, 0x8066AAA0, True,
            hook_offset=0x30, original=LI_R27_0, cave_id_slot=0x7C, floor_slot=0x5C),
]
BY_KEY = {v.key: v for v in VERSIONS}

UNSUPPORTED = [
    ("Wii New Play Control! Europe and Japan (R92P01, R92J01)", "no copy of the game to find the addresses in yet"),
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
        ("hit:", lwz(12, 4, 11)),
        ("", lis(11, _ha(v.rand_next))), ("", stw(12, _lo(v.rand_next), 11)),   # rand state = seed
        ("done:", v.original),
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


def sublevels(entries) -> list[tuple[str, int, int, int]]:
    """(cave, sublevel, key, seed) for each sublevel of a run with a trusted seed, in the order
    first played. A sublevel made more than once (All Treasures purple farms: BK 1-3, out, then
    BK 1-7) gets the seed of its first visit, or of the first visit with a trusted seed.
    `entries` are a judge.json's entries after judge_report.mark_neighbors."""
    from .judge_report import trusted
    out: dict[int, tuple[str, int, int, int]] = {}
    for e in entries:
        if e.get("cave") in CAVE_IDS and e.get("sublevel") and e.get("layout_seed") and trusted(e):
            sub = int(e["sublevel"])
            k = key(e["cave"], sub)
            out.setdefault(k, (e["cave"], sub, k, int(str(e["layout_seed"]), 16) & 0x7FFFFFFF))
    return list(out.values())


def table(entries) -> list[tuple[int, int]]:
    """The code's table: (key, seed) per sublevel (see sublevels)."""
    return [(k, s) for _, _, k, s in sublevels(entries)]


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
