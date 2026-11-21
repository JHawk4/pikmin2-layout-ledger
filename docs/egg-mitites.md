# Can a runner make an egg hatch Mitites (or not)?

**Short answer:** in real time, no. The egg's contents come from one draw of the global RNG on the
frame the egg breaks. Dozens of Pikmin, enemies and Captains draw from that RNG every frame, and the
number of draws depends on what they are doing. Nothing on screen tells the player the RNG state at
that moment. Timing the break to the frame does not help. A TAS, which can redo inputs and look at
memory, can get Mitites almost at will by breaking the egg a frame earlier or later.
There is one rule a real-time runner can use: if the Mitite pool is full, a Mitite roll gives a nectar
drop instead. Above ground that takes only one live Mitite group.

## 1. How the drop is decided

Decompilation: [projectPiki/pikmin2](https://github.com/projectPiki/pikmin2).

- `Egg::StateWait::exec` (`src/plugProjectMorimuraU/eggState.cpp`) checks `mHealth <= 0.0f` each
  update. On the first frame that is true it calls `Egg::Obj::genItem()`, plays the break effects
  and kills the egg. The egg draws nothing before this (`Obj::onInit` and `birth` have no `rand`).
  So the contents are **decided on break**, not when the egg spawns or the area loads. Pikipedia
  says the same.
- `Egg::Obj::genItem()` (`src/plugProjectMorimuraU/egg.cpp`, `0x8034C2AC`) draws one
  `randFloat()` = `rand() / 32768.0f` (`include/Dolphin/rand.h`; `RAND_MAX` is `SHORT_FLOAT_MAX` =
  32768.0f in `include/types.h`). It then walks the cumulative parameters `fp01..fp05`
  (`include/Game/Entities/Egg.h`, `Egg::Parms::ProperParms`):

  | parm | outcome | rate (enemyparm.txt) | `rand()` values |
  |---|---|---|---|
  | fp01 | 1 nectar | 0.50 | 0–16383 |
  | fp02 | 2 nectar | 0.35 | 16384–27852 |
  | fp03 | 10 Mitites | 0.05 | **27853–29491** (1639 values, 5.00%) |
  | fp04 | ultra-spicy spray | 0.05 | 29492–31129 |
  | fp05 | ultra-bitter spray | 0.05 | 31130–32767 |

  The rates are the disc values in `/enemy/parm/enemyParms.szs/egg/enemyparm.txt`, as given on
  [Pikipedia's Nectar egg page](https://www.pikminwiki.com/Nectar_egg). The header defaults are all
  1.0 and are overwritten by the file. `rand()` is the MSL LCG
  (`src/Dolphin/MSL_C/MSL_Common/rand.c`), the same one as `p2seeds/src/p2seeds/rng.py`.
  `p2seeds/src/p2seeds/egg.py` maps a state or a `rand()` value to an outcome.
- Two fallbacks come after the roll:
  - `mDoCheckHasSpray` (on by default): a spicy or bitter roll becomes 1 nectar until that spray has
    been made in story mode. Mitites are not affected.
  - Mitites: `TamagoMushi::Mgr::createGroup(birthArg, 10, …)` (`tamagoMushiMgr.cpp`) returns
    `nullptr` if the pool has fewer than 10 free slots. Then `genItem` births **1 nectar** instead.
    The pool is 10 Mitites above ground and 30 (`TAMAGOMUSHI_GROUP_COUNT`) in caves
    (`generalEnemyMgr.cpp`, `case EnemyID_TamagoMushi`). So above ground one live Mitite group
    blocks every further Mitite roll; in a cave it takes three. A group frees its slots when the
    Mitites are killed or burrow back (`StateHide::exec` → `kill`, after `mSurvivalTime` scaled by
    0.8–1.0).
- Eggs that fall from cave ceilings break on landing. They use the same `genItem` path at that
  moment.

## 2. The RNG path to the draw

The roll is "the next draw from the global LCG when the egg's update runs on the break frame". Its
outcome is a 5% window on that one draw, so the question is whether the player can control the
state at that draw.

- **Draws between a known state and the break.** The last state this project can read is the
  sublevel entry screen's falling letters. Between those and gameplay, cave generation draws a
  fixed number of steps for a given seed (CaveGen reproduces it). After that, gameplay draws from
  the same RNG all the time, and many of these draws depend on what is happening. From the decomp:
  - Pikmin: each fleeing Pikmin draws about 3 per frame (up to 6) (`PikiEscapeState::exec`, `pikiState.cpp`).
    Trips (`PikiKokeState`) draw. So do many state `init`s (wait timers, knockback, flower fall,
    drowning, death), `Piki::startMotion` (20% branch), and the look-at target choice (`piki.cpp`).
  - Enemies: `EnemyBase` draws on birth, on Purple-Pikmin stun checks (`enemyBase.cpp`,
    `mPurplePikiStunChance`) and in many idle/turn choices. So do Mitites once they are out
    (`tamagoMushi.cpp`).
  - Particles use their own `JPARandom` (`JPAMath.h`), so they do **not** consume the global RNG.
  - The number of draws per frame depends on how many Pikmin are in which state, which animations
    start, enemy AI timers, and each Purple landing. All of these follow player input and physics.
    It is not a fixed count that a runner can count off.
- **Order within the break frame.** The egg's own update runs partway through the frame. Draws by
  objects updated earlier that frame (Pikmin attacking the egg, other enemies) come first.
  The breaking hit itself can add draws (for example a Purple's stun check).
- **How a 5% window behaves along the stream.** On a sample LCG stream (200,000 draws from
  `423CDA79`), 5.03% of draws fall in the Mitite window. Mitite draws come in runs of 1.06 on
  average (at most 4), and the gap between them averages 20 draws (longest 153). Moving the break
  by a frame moves the roll by tens of draws, so each frame is a fresh, roughly independent 5% chance.

## 3. Evidence from the community and this project

- Pikipedia ([Nectar egg](https://www.pikminwiki.com/Nectar_egg),
  [Randomization](https://www.pikminwiki.com/Randomization)) documents the 50/35/5/5/5 table and
  the on-break timing. Neither page mentions any manipulation of egg contents.
- [TASVideos' Pikmin 2 resource page](https://tasvideos.org/GameResources/GC/Pikmin2) has an RNG
  section with "Cave Generation" and "Spicy and Bitter Sprays" headings but no written content.
  Web searches turned up no RTA egg manip (speedrun.com forum posts and guides were not read in full). What runners do is handle the
  outcome: throw a Purple onto the egg, which kills any Mitites as they come out.
- Our seed data (`data/output/*/seeds.json`) cannot test this. Every recovered state is at a
  sublevel entry screen or a Challenge Mode results roll. Any egg break is cave generation plus
  seconds to minutes of gameplay draws later. The only gameplay draw count we have is from
  Challenge Mode: two 2P results screens 28,058 draws apart across a 5-floor stage. That rules out
  counting draws by hand. No VOD frame shows a readable RNG state near an egg.

## 4. Verdict

| approach | feasible? |
|---|---|
| Deterministic RTA setup (do X, then break on frame N) | **No.** The per-frame draw count depends on Pikmin and enemy behaviour, so no setup gives a repeatable state at the break. |
| Frame-perfect break timing in RTA | **No.** Without knowing the state, every frame is another independent ~5% roll. |
| Few-percent improvement | **No** by timing. **Avoidance only:** keep one Mitite group alive above ground (three in a cave) and later eggs cannot hatch Mitites. A Mitite roll becomes 1 nectar. This is rarely worth doing. |
| TAS (inputs replayable, RAM visible) | **Yes, easily.** Delay or advance the final hit by a frame, or change Pikmin activity, until the roll lands in 27853–29491 for Mitites (or outside it to avoid them). About 1 in 20 frame choices works. `p2seeds.egg.outcome_after(state)` checks a state. |

**What a runner would actually do:** treat every egg as a 5% Mitite risk. Break eggs with Purples
(this kills Mitites as they hatch), or skip eggs on routes where Mitites would cost time. Do not try to
manipulate them.

## 5. Open questions

- Confirm the disc rates directly. They come from Pikipedia's reading of `enemyparm.txt`; the
  decomp has only the header defaults (1.0).
- `mSurvivalTime` on disc (header default 300) sets how long one group blocks the pool above ground.
  Units and disc value are unchecked.
- Is there any gameplay situation with an almost fixed per-frame draw count (no Pikmin out, no
  active enemies, for example a Captain alone breaking a ceiling-fall egg)? If so, a state read at
  sublevel entry plus a frame-exact route might in theory pin the roll. It would still need a frame
  count from load that RTA cannot hit. Worth checking only with a Dolphin RAM watch on the LCG state
  (`next`, set by `srand` at `0x800C9598`).
- Lower priority: whether Honeywisp-dropped eggs run the same `genItem` path at the same point.
  Pikipedia says they can contain Mitites.
