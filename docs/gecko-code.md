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
   (key, seed) words; on a match store the seed into `rand()`'s state (MSL `rand.c` `next`), then,
   if `PSSystem::spSysIF` is set, call `spSysIF->playSystemSe(0x183C, 0)`: the sound
   `PSSE_SY_2PSLOT_GO` (the 2-player card slot's "GO"), which Meeo's set-seed code also plays. A
   moderator asked for it, so a recording shows when the code set a layout. No sound when nothing is
   set.
5. `li r26, 0` (the replaced instruction; `li r27, 0` on the Wii); the code handler adds the branch back.

Only volatile registers are used (r3, r9–r12, ctr, cr0); the prologue has already saved the link
register and nothing after the hook reads r4–r12 before setting them. Cave IDs come from the game's
`user/Abe/stages.txt`: EC `t_01`, SCx `t_02`, FC `t_03`, HoB `f_01`, WFG `f_02`, BK `f_03`, SH `f_04`,
CoS `y_01`, GK `y_02`, SR `y_03`, SC `y_04`, CoC `l_01`, HoH `l_02`, DD `l_03`.

A run's table has one entry per sublevel with a trusted seed (`judge_report.trusted`: high
confidence, or medium in order with its high neighbours), in the order first played. All Treasures
runs make some sublevels more than once (BK purple farms, EC twice); the table takes the first
visit's seed, or the first visit with a trusted seed. The layout is set every time the sublevel is
made, so re-entering gives the same layout. 8 bytes per sublevel; the fixed part is 46 instructions
plus the `bl`, the end marker and the return slot.

## Addresses per version

| Version | Hook | `gameSystem` | `SingleGameSection` vtable | `getCaveID` | `getCurrFloor` | `rand` state | `playSystemSe` | `spSysIF` | Checked on a real DOL |
|---|---|---|---|---|---|---|---|---|---|
| USA GPVE01 | 8024C138 | 80515A68 | 804B1350 | 80153118 | 80155F54 | 805148A8 | 80338630 | 80515ED8 | yes |
| USA demo 17 (GPVE01, "Demo1 (USA)") | 8024C118 | 805159A8 | 804B1290 | 801530F8 | 80155F34 | 805147E0 | 80338664 | 80515E18 | yes |
| USA demo 18 (GPVE01) | 8024C118 | 805158A8 | 804B1190 | 801530F8 | 80155F34 | 805146E0 | 80338610 | 80515D18 | no |
| PAL GPVP01 | 8024C11C | 80516768 | 804B1EE0 | 80153284 | 801560C0 | 805155A0 | 803387BC | 80516BD8 | no |
| JPN GPVJ01 | 8024C79C | 80517568 | 804B2DB0 | 8015310C | 80156388 | 805163A8 | 80338C48 | 805179D8 | no |
| Wii USA R92E01 | 802D0F00 (`li r27, 0`) | 8066C9F0 | 80590E00 | 801E63AC | 801E92A4 | 8066AAA0 | 803B8384 | 8066CE70 | yes (RAM dump + clean DOL) |

GameCube addresses are from the decomp's `config/<version>/symbols.txt`. Not supported: the Wii
New Play Control! Europe and Japan versions (R92P01, R92J01: no copy to search) and romhacks. No
Korean GameCube release is known to the decomp.

### Wii (R92E01)

There is no Wii decomp. The addresses were found in a Dolphin RAM dump of the USA Wii game
(`Documents/Dolphin Emulator/Dump/mem1.raw`, made from the user's `Pikmin2Wii_practice.iso`):

- `rand` at 80109DC4 (the `0x41C64E6D` / `0x3039` update), its state at `r13-0x7D60`; r13 is
  80672800 (`lis r13 / ori r13` at 80006314), so the state is at 8066AAA0.
- `createMapPartsList` at 802D0ED0: the string "RandMapMgr" leads to the `RandMapMgr` constructor
  (802C9240); the next function is `loadResource` (802C92CC), whose first constructor call is
  `MapUnitGenerator`'s (802D0898); that calls `createEditMapInfo`, `createMemList`,
  `memMapListSorting`, then `createMapPartsList`, as on GameCube. Its first `rand` call
  (802D0F88) comes after the hook.
- The practice build already hooks 802D0F00 (`bl 80688794`): its routine either writes a stored
  seed to 8066AAA0 or saves the current one, then runs `li r27, 0` and returns. So the hook is the
  same spot, the RNG state address is confirmed, and the replaced instruction is `li r27, 0`.
- `gameSystem` at `r13-0x5E10` = 8066C9F0: the game's own `getCaveID() == 'y_04'` checks
  (`addis r0, r3, -0x795F; cmplwi r0, 0x3034`) load it, then `mSection` at +0x58, then call vtable
  slot 0x7C (0x78 on GameCube).
- `SingleGameSection`'s vtable is 80590E00: slot 0x7C is `lwz r3, 0x23C(r3); blr` (801E63AC) and
  slot 0x5C is `lwz r3, 0x24C(r3); blr` (801E92A4), the GameCube fields (0x238 / 0x248) moved by 4,
  and a constructor that first calls the base section constructor stores it at offset 0.
- After the hook, nothing reads r3–r12 before setting it, and only nonvolatile float registers
  (f30, f31) are live, so the sound call can clobber the volatile ones.
- Sound: `spSysIF` at `r13-0x5990` = 8066CE70 and `playSystemSe` at 803B8384 are the pair most
  calls with a constant 0x18xx sound ID go through (190 sites; the same search on USA retail finds
  its known pair, 199 sites). Callers pass (spSysIF, id, 0) as on GameCube. The Wii version also
  sends a few sounds to the Wii Remote speaker; 0x183C isn't one of them. Both games play 0x183C
  from the 2-player card-slot code (802BABF8 on Wii, 8023676C on GameCube).

Checked afterwards on a clean Wii `main.dol` (SHA-1 d69f9083b7c47665a4f701099ec029176f2e3aeb, the
user's `Hack/ckit_wii_base/ckit/pikmin.dol`): 802D0F00 is `li r27, 0` (`3B600000`), `rand`, both
getters and the vtable slot are as above, and the user's Wii symbol map
(`symbolmap/symbol_map_wii1.MAP`) names 802D0ED0 `createMapPartsList`. The Wii practice build patches
both getters with branches into its own code; the Gecko code still calls them. Seeds read from Wii runs replay on the Wii version; GameCube runs' seeds on the Wii give the layout
the Wii's cave files make from that seed (the same where the files match).

## What is verified

- On the USA retail DOL and the USA demo 17 DOL (both match the decomp's SHA-1s): the instruction at
  the hook is `li r26, 0` (`3B400000`) and is followed by the shuffle; `srand` and `rand` read and
  write the `rand` state address above (r13 base 8051C680 / 8051C5C0); vtable +0x78 and +0x58 are
  `getCaveID` and `getCurrFloor`; both getters are `lwz r3, x(r3); blr` (x = 0x238 / 0x248 on retail,
  0x25C / 0x26C on demo 17, which is why the code calls them instead of reading fields);
  `gameSystem` +0x58 is among the most read fields right after loading `gameSystem`, as `mSection`.
- The demo 17 hook equals Meeo's set-seed code (`C224C118`, ends with `li r26, 0`), and its sound
  call is the same as ours there: `lwz r3, -0x67A8(r13)` (spSysIF, 80515E18), `li r4, 0x183C`,
  `li r5, 0`, call 80338664 (`playSystemSe`). On the retail
  build 0x8024C118 is a prologue instruction (`stfd f31`), so a set-seed code at that address is for
  the demo build only.
- Tests: the assembler's encodings against words read from the game; the body disassembled with
  capstone; table rules; the page's script against the Python reference (node); and the whole code
  run, for every version, on a small PowerPC model (instructions decoded by capstone, fake game
  memory): the run's seed for its sublevels (first trusted visit) with one sound call per seed set
  (right arguments), none on a miss or outside story mode, and the seed still set without a sound system.
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
