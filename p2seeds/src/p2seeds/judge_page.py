"""The "How the judge works" page (how-judge.html; each run folder has its own judge.html, the
run's layouts): a short, plain description of judge2, with collapsed sections for the details."""

from __future__ import annotations

from pathlib import Path

from . import treasures


def _fc6(runs: list[dict]) -> tuple[int, int]:
    """(plays of FC 6 with a confident seed, how many of them took a chess piece)."""
    from .judge_report import trusted
    n = took = 0
    for r in runs:
        tre = treasures.load(Path(r["dir"]))
        for e in r["entries"]:
            if e.get("cave") == "FC" and e.get("sublevel") == 6 and trusted(e):
                t = tre.get(str(e["frame"]))
                if t is None:
                    continue
                n += 1
                took += bool([c for c in t.get("collected", []) if c])
    return n, took


def page(runs: list[dict], cal: dict) -> str:
    n6, took6 = _fc6(runs)
    fit = (f"Across {cal['n']:,} sublevel plays on this site, one second the judge predicts is worth "
           f"{cal['slope']:.2f} real seconds (1 would be perfect), and its estimates correlate "
           f"{cal['corr']:.2f} with the real times.") if cal.get("slope") else ""
    return f'''
<h1>How the judge works</h1>
<p class="intro">The judge looks at a sublevel's layout (where the ship, the treasures, the enemies and the hole are)
and estimates how many seconds a good runner needs to clear it in Pay Off Debt. It never watches the run: it only
sees the layout, so it can say how kind the layout was, apart from how well it was played.</p>

<ul class="legend-list">
<li><b>Estimate</b>: the time to walk the route, plus the time Pikmin spend carrying each treasure back to the ship,
plus extra time for enemies near a carry path and for gates in the way, plus a fixed cost per treasure.</li>
<li><b>Layout luck</b>: the same estimate for 1000 random layouts of the sublevel. This layout against the median one
is its luck (negative = faster), and the share of random layouts it beats is its percentile.</li>
<li><b>Runner</b>: the real time from the video, with pokos counted (2 pokos = 1 s), minus what the judge says the
layout was worth. What is left is the runner's own doing.</li>
</ul>
<p>{fit} See <a href="accuracy.html">Judge accuracy</a> for the checks.</p>

<details><summary>What goes into the estimate</summary>
<ul>
<li><b>Walking</b>: the shortest tour from the ship over the treasures, then on to the hole.</li>
<li><b>Carrying</b>: for each treasure, the time to gather carriers, dig it up if it is buried, and carry it home
at a speed set by its weight and how many Pikmin fit on it.</li>
<li><b>Hazards</b>: enemies within reach of a carry path, by how dangerous they are.</li>
<li><b>Gates</b>: gates on a carry path or on the way to the hole, by their health.</li>
<li><b>Pokos</b>: if the treasures it expects you to take are worth fewer pokos than usual, the shortfall counts
against the layout at 2 pokos per second, the same rate the runner numbers use.</li>
<li><b>10 seconds per treasure</b> taken, for picking it up and the collection cutscene.</li>
</ul>
<p>Each part has its own weight, fitted to real times (below): walking ×1.22, carrying ×0.78, hazards ×0.60,
gates ×0.58.</p>
</details>

<details><summary>Which treasures it expects the runner to take</summary>
<p>Runners skip a treasure when it costs more time than its pokos are worth. The judge tries every take/skip choice
(every combination of up to four treasures) and scores each. It doesn't simply pick the fastest; it averages the
choices, leaning heavily on the fast ones, because runners don't always make the best call. When one choice is clearly
best (about 80% of the weight) the run pages name the treasure it expects to be skipped.</p>
<p><b>Optional treasures are assumed left behind.</b> Six treasures that runners almost never collect get no time
and no pokos in the estimate: the chess pieces on FC 6, the locket, the gum tape on SCx 1, the leaf on CoS 1 and
the queen on SH 6. On FC 6, {took6} of {n6} runs here took a chess piece. When a runner does take one, its pokos still
count in the runner's number (2 pokos = 1 s), so the detour is judged on whether it paid for itself. About 15
low-value treasures are ignored altogether.</p>
</details>

<details><summary>Special cases</summary>
<ul>
<li><b>SH 6</b>: if the Dwarf Bulborb carrying the lens would have to cross water, the lens counts as so costly that
the judge expects runners to skip it, which they do.</li>
<li><b>GK</b>: CaveGen's own adjustments for Glutton's Kitchen are kept, with a fitted weight (×0.54).</li>
<li><b>Fixed floors</b> (the same layout for every seed, such as boss floors) have no luck: they are shown but
never counted.</li>
</ul>
</details>

<details><summary>How it was made and checked</summary>
<p>It starts from CaveGen's Pay Off Debt judge, rebuilt in CaveGen3. The original treated every
treasure as taken, gave credit for optional treasures and for creature pokos, and overstated layout differences by
about a fifth. This version ("judge2") changes those rules and refits the weights on the real sublevel times in
these runs.</p>
<p>To avoid tuning it to the runs it is then judged on, the weights were fitted on some runners' runs and tested on
the others. On the held-out runners, it explained about 47% of the differences in time between layouts, against
36% for the original.</p>
<p>The comparison works within each sublevel and each runner, so it asks only: when the same runner meets a
different layout of the same sublevel, does the time move as the judge says?</p>
</details>

<details><summary>What it can't see</summary>
<ul>
<li>Execution: deaths, misplays, lucky enemy behaviour, how well a runner manages Pikmin.</li>
<li>Route habits beyond the take/skip choice, and tricks the base judge doesn't model.</li>
<li>It is an estimate. Single sublevels can be off by several seconds; totals over a run are much steadier.</li>
</ul>
</details>
'''


def page_at(runs: list[dict], cal: dict) -> str:
    """The All Treasures judge (judge2's at2; judge2/LOG_AT.md)."""
    fit = (f"Across {cal['n']:,} sublevel plays on this site, one second the judge predicts is worth "
           f"{cal['slope']:.2f} real seconds (1 would be perfect), and its estimates correlate "
           f"{cal['corr']:.2f} with the real times.") if cal.get("slope") else ""
    return f'''
<h1>How the judge works</h1>
<p class="intro">The judge looks at a sublevel's layout (where the ship, the treasures, the enemies and the hole are)
and estimates how many seconds a good runner needs to collect every treasure on it and leave. It never watches the
run: it only sees the layout, so it can say how kind the layout was, apart from how well it was played.</p>

<ul class="legend-list">
<li><b>Estimate</b>: the time to walk the route, plus the time Pikmin spend carrying each treasure back to the ship,
plus extra time for enemies near a carry path and for gates in the way, plus a fixed cost per treasure.</li>
<li><b>Missing treasures and purple flowers</b>: a quirk of the spawning sometimes leaves a treasure out of the layout,
or fewer purple flowers than usual where runners pick purples. Both cost the runner a lot of time; the judge adds
300 s when a treasure is missing and 60 s per missing purple flower, as CaveGen's All Treasures judge does.</li>
<li><b>Layout luck</b>: the same estimate for 1000 random layouts of the sublevel. This layout against the median one
is its luck (negative = faster), and the share of random layouts it beats is its percentile.</li>
<li><b>Runner</b>: the real time from the video minus what the judge says the layout was worth. What is left is the
runner's own doing.</li>
</ul>
<p>{fit} See <a href="accuracy.html">Judge accuracy</a> for the checks.</p>

<details><summary>How it was made and checked</summary>
<p>It is CaveGen's All Treasures judge, rebuilt in CaveGen3, with the Japanese release's treasure weights for Japanese
runs. Its parts are weighted as the Pay Off Debt judge's, which were fitted on that category's real times: walking
×1.22, carrying ×0.78, hazards ×0.60, gates ×0.58. On the All Treasures runs here those weights come out right (a
predicted second is worth about one real second), while CaveGen's own weights overstate layout differences by about a
fifth. A fit on these runs alone could not do better: with a handful of runs, every reasonable set of weights
explains about as much.</p>
<p>The missing-treasure and missing-purple costs could not be checked yet: none of these runs met a missing treasure,
and only two met missing purple flowers, both on the same sublevel. Missing purple flowers are common on a few
sublevels (about a third of random BK 4 and FC 4 layouts, two thirds of SR 5), so more runs will tell.</p>
<p>The comparison works within each sublevel and each runner, so it asks only: when the same runner meets a
different layout of the same sublevel, does the time move as the judge says?</p>
</details>

<details><summary>What it can't see</summary>
<ul>
<li>Execution: deaths, misplays, lucky enemy behaviour, how well a runner manages Pikmin.</li>
<li>Route habits and tricks the base judge doesn't model.</li>
<li>It is an estimate. Single sublevels can be off by several seconds; totals over a run are much steadier.</li>
</ul>
</details>
'''
