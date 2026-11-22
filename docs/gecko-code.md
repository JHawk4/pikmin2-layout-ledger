# The Gecko code page

`gecko.html` (the "Gecko code" tab) builds a Gecko code that replays a run's layouts: when the game
generates a cave sublevel that the chosen run has a trusted seed for, the code sets the RNG to that
seed first, so the layout matches the run. Other sublevels stay random. Story mode only.

Code: `p2seeds/src/p2seeds/gecko.py` (addresses, a small PowerPC assembler, the table),
`gecko_page.py` (the page; its script joins the parts in the browser), `site.write_gecko` (called by
`site.export`, over the Pay Off Debt and All Treasures sections). Tests: `p2seeds/tests/test_gecko.py`.

## Where the seed goes

Story mode makes a sublevel in `BaseGameSection::setupFloatMemory`:
`RoomMapMgr::createRandomMap(getCurrFloor())` → `nishimuraCreateRandomMap` →
`Cave::RandMapMgr::loadResource` → `new MapUnitGenerator(...)`. The constructor runs
`createEditMapInfo` (draws only with a versus-mode edit unit), `createMemList`, `memMapListSorting`
(no draws), then `createMapPartsList`, whose shuffle of the map unit lists is the first `rand()` call
of the layout. CaveGen's `createRandomMap` starts with the same shuffle (`mapUnitsInitialSorting`),
and its readme says its seed "corresponds to Meeo's setseed code", which writes the seed at this
same instruction on the USA demo build. So the seed CaveGen (and this site's `layout_seed`) means is
`rand()`'s state on entry to `createMapPartsList`, before any draw; the game's `rand()` advances the
state and then returns bits 16–30, as CaveGen's does.

The hook is `createMapPartsList + 0x2C`, the instruction `li r26, 0` right after the prologue (it
saves r23–r31, f30 and f31, loads two float constants and does `mr r31, r3`). The code is a `C2`
insert there:

1. `bl` over the table (link register = table address).
2. `gameSystem->mSection` (`GameSystem` +0x58); stop if null or if its vtable is not
   `SingleGameSection`'s (challenge mode and 2-player battle use other sections).
3. Call `SingleGameSection::getCaveID` and `::getCurrFloor` by address (each is `lwz r3, x(r3); blr`,
   so the field offsets, which differ between builds, don't matter).
4. Key = cave ID (`'f_03'` etc.) with its second byte replaced by the 0-based floor. Walk the table of
   (key, seed) words; on a match store the seed into `rand()`'s state (MSL `rand.c` `next`).
5. `li r26, 0` (the replaced instruction); the code handler adds the branch back.

Only volatile registers are used (r3, r9–r12, ctr, cr0); the prologue has already saved the link
register and nothing after the hook reads r4–r12 before setting them. Cave IDs come from the game's
`user/Abe/stages.txt`: EC `t_01`, SCx `t_02`, FC `t_03`, HoB `f_01`, WFG `f_02`, BK `f_03`, SH `f_04`,
CoS `y_01`, GK `y_02`, SR `y_03`, SC `y_04`, CoC `l_01`, HoH `l_02`, DD `l_03`.

A run's table holds its trusted seeds (`judge_report.trusted`: high confidence, or medium in order
with its high neighbours), one per sublevel; when a cave was entered more than once (All Treasures
purple farms), the last trusted visit wins. 8 bytes per sublevel; the fixed part is 36 instructions plus the `bl`, the end marker and the return slot.

## Addresses per version

| Version | Hook | `gameSystem` | `SingleGameSection` vtable | `getCaveID` | `getCurrFloor` | `rand` state | Checked on a real DOL |
|---|---|---|---|---|---|---|---|
| USA GPVE01 | 8024C138 | 80515A68 | 804B1350 | 80153118 | 80155F54 | 805148A8 | yes |
| USA demo 17 (GPVE01, "Demo1 (USA)") | 8024C118 | 805159A8 | 804B1290 | 801530F8 | 80155F34 | 805147E0 | yes |
| USA demo 18 (GPVE01) | 8024C118 | 805158A8 | 804B1190 | 801530F8 | 80155F34 | 805146E0 | no |
| PAL GPVP01 | 8024C11C | 80516768 | 804B1EE0 | 80153284 | 801560C0 | 805155A0 | no |
| JPN GPVJ01 | 8024C79C | 80517568 | 804B2DB0 | 8015310C | 80156388 | 805163A8 | no |

All from the decomp's `config/<version>/symbols.txt`. Not supported: the Wii New Play Control!
versions (R92E01, R92P01, R92J01: no symbol map; the user has a Wii practice ISO to find them from)
and romhacks. No Korean GameCube release is known to the decomp.

## What is verified

- On the USA retail DOL and the USA demo 17 DOL (both match the decomp's SHA-1s): the instruction at
  the hook is `li r26, 0` (`3B400000`) and is followed by the shuffle; `srand` and `rand` read and
  write the `rand` state address above (r13 base 8051C680 / 8051C5C0); vtable +0x78 and +0x58 are
  `getCaveID` and `getCurrFloor`; both getters are `lwz r3, x(r3); blr` (x = 0x238 / 0x248 on retail,
  0x25C / 0x26C on demo 17, which is why the code calls them instead of reading fields);
  `gameSystem` +0x58 is among the most read fields right after loading `gameSystem`, as `mSection`.
- The demo 17 hook equals Meeo's set-seed code (`C224C118`, ends with `li r26, 0`). On the retail
  build 0x8024C118 is a prologue instruction (`stfd f31`), so a set-seed code at that address is for
  the demo build only.
- Tests: the assembler's encodings against words read from the game; the body disassembled with
  capstone; table rules; the page's script against the Python reference (node).
- PAL, JPN and demo 18 use the same function (same size, 0x14C) and the decomp's addresses, but
  were not checked against a disc.
- Not yet run in Dolphin or on Nintendont.

## Testing in Dolphin

1. Build the site (`python -m p2seeds publish --no-push`) and open `data/pages/gecko.html`, or use
   the live page.
2. Pick "USA (GPVE01)" and a Pay Off Debt run; copy the code. In Dolphin: Config → General → Enable
   Cheats; right-click the game → Properties → Gecko Codes → Add New Code, paste, save, tick it.
3. Start a story file and enter a cave in the run's table (the page lists them, with a CaveGen3 link
   for each seed). The first sublevel should match the CaveGen3 render; go down and compare the next.
   Re-entering the cave should give the same layouts again.
4. Optional check of the seed itself: Dolphin's memory view at the `rand` state address above should
   show the seed (bit 31 may differ) when the hook runs; a breakpoint at the hook shows it per floor.
5. A sublevel the run has no seed for (or challenge mode) should be random as usual.

## Sources

- projectPiki/pikmin2 decomp (github.com/projectPiki/pikmin2): `MapUnitGenerator.cpp`,
  `MapCreator.cpp`, `RandMapMgr.cpp`, `gameMapParts.cpp`, `baseGameSection.cpp`,
  `SingleGameSection.h`, `GameSystem.h`, `MSL_C/rand.c`, symbol maps.
- CaveGen (github.com/JHaack4/CaveGen): `CaveGen.java` (`createRandomMap`, `rand`), readme.
- Meeo's "set seed" and "get seed" codes (USA demo build), in the user's Dolphin `GPVE01.ini`;
  speedrun.com's Pikmin 2 "Set Seed Code" guide (speedrun.com/pikmin2/guides/lufb1) has codes for
  each region (not read here: the site refuses automated fetches).
