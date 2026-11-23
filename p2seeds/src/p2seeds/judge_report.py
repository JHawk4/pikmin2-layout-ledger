"""Judge every recovered layout of a run with CaveGen and write a one-file page.

The page shows each sublevel's layout render next to CaveGen's judge verdict:
its estimated clear time, where that falls among 1000 random layouts of the
same sublevel, and the difference from the median layout. Images are embedded
so the page can be opened or shared on its own.
"""

from __future__ import annotations

import base64
import html
import json
from pathlib import Path

import numpy as np

from . import cavegen, charts, luck, rng, treasures
from .caves import CAVES

CAVE_NAMES = {c.cavegen: c.name for c in CAVES if getattr(c, "lang", "en") == "en"}


def judge_run(out_dir: Path, kind: str = "pod", progress=None) -> list[dict]:
    """Judge every entry with a layout seed in `out_dir/seeds.json`; saves judge.json."""
    data = json.loads((out_dir / "seeds.json").read_text(encoding="utf-8"))
    rows = []
    entries = [e for e in data["entries"] if e.get("cave") and e.get("layout_seed") and e.get("sublevel")]
    for i, e in enumerate(entries):
        j = cavegen.judge(e["cave"], e["sublevel"], int(e["layout_seed"], 16), kind)
        row = dict(e)
        if j is not None:
            row.update(judge_kind=kind, judge_score=j.score, judge_rank=j.rank, judge_median=j.median,
                       judge_vs_median=j.vs_median, judge_fixed=j.fixed)
        rows.append(row)
        if progress:
            progress(i + 1, len(entries), row)
    (out_dir / "judge.json").write_text(json.dumps({"meta": data.get("meta", {}), "kind": kind, "entries": rows},
                                                   indent=1), encoding="utf-8")
    return rows


def _img(path: Path) -> str:
    return "data:image/png;base64," + base64.b64encode(path.read_bytes()).decode("ascii")


def _signed(x: float) -> str:
    return f"{x:+.1f} s" if abs(x) >= 0.05 else "±0.0 s"


def _faster_than(row: dict) -> float:
    return 100.0 - row["judge_rank"]


def _beats(f: float) -> str:
    """'faster than 62% of layouts', with the ends said plainly."""
    if f >= 99.5:
        return "about the best of 1000 random layouts"
    if f <= 0.5:
        return "about the worst of 1000 random layouts"
    return f"faster than {f:.0f}% of layouts"


def _tone(delta: float | None) -> str:
    """Seconds against the median, negative = faster (as on splits): green, red, or neutral."""
    if delta is None:
        return "mid"
    return "good" if delta < -0.5 else "bad" if delta > 0.5 else "mid"


def _delta(r: dict) -> float:
    """The judge's estimate for this layout minus the median layout's (negative = faster)."""
    return r.get("judge_vs_median") or 0.0


def _num(delta: float | None, unit: str = "s") -> str:
    if delta is None:
        return '<span class="muted">–</span>'
    return f'<span class="{_tone(delta)}-text">{delta:+.1f} {unit}</span>' if unit else f'<span class="{_tone(delta)}-text">{delta:+g}</span>'


def cg3_url(r: dict) -> str:
    """This layout on the CaveGen3 web page (zoomable, with treasures, teki and judges)."""
    seed = r["layout_seed"][2:] if r["layout_seed"].lower().startswith("0x") else r["layout_seed"]
    # Pay Off Debt layouts open with judge2 selected, the judge the ledger scores them with.
    judge = "&judge=judge2" if r.get("judge2_score") is not None or r.get("judge_kind") == "pod" else ""
    return f"https://jhawk4.github.io/CaveGen3/?sublevel=pikmin2:{r['cave']}-{r['sublevel']}&seed={seed}{judge}"


NEIGHBOR_STEPS = 2_000_000    # a medium seed this few RNG steps from both high neighbours is in order


def mark_neighbors(entries: list[dict]) -> list[dict]:
    """Set `neighbor_ok` on medium-confidence entries whose letter seed falls in RNG order
    between the nearest high-confidence seeds before and after it (within NEIGHBOR_STEPS of
    each). A wrong read lands at a random place in the 2^32 cycle, so this is very unlikely by
    chance. Returns `entries`."""
    seeds = [int(e["letter_seed"], 16) if e.get("letter_seed") else None for e in entries]
    high = [i for i, e in enumerate(entries) if e.get("confidence") == "high" and seeds[i] is not None]
    for i, e in enumerate(entries):
        e.pop("neighbor_ok", None)
        if e.get("confidence") != "medium" or seeds[i] is None:
            continue
        before = [j for j in high if j < i][-1:]
        after = [j for j in high if j > i][:1]
        if not before and not after:
            continue
        ok = all(rng.distance(seeds[j], seeds[i], limit=NEIGHBOR_STEPS) is not None for j in before) and             all(rng.distance(seeds[i], seeds[j], limit=NEIGHBOR_STEPS) is not None for j in after)
        if ok:
            e["neighbor_ok"] = True
    return entries


def mark_revisits(entries: list[dict]) -> list[dict]:
    """Set `revisit` on every visit to a cave but the last (All Treasures runners farm purple
    Pikmin in Bulblax Kingdom: down a few floors, out, and in again). A visit ends where the cave
    changes or the sublevel stops going up. Those floors are shown but not timed or totalled.
    Returns `entries`."""
    visits: list[list[dict]] = []
    for e in entries:
        v = visits[-1] if visits else None
        if v and e.get("cave") and v[-1].get("cave") == e["cave"] and (e.get("sublevel") or 0) > (v[-1].get("sublevel") or 0):
            v.append(e)
        else:
            visits.append([e])
    last = {v[0].get("cave"): k for k, v in enumerate(visits)}
    for k, v in enumerate(visits):
        for e in v:
            e.pop("revisit", None)
            if v[0].get("cave") and last[v[0]["cave"]] != k:
                e["revisit"] = True
    return entries


def trusted(r: dict) -> bool:
    """High-confidence seeds, and medium ones in order with their high neighbours (see
    mark_neighbors), feed totals, charts and the calibration; the rest are shown on request,
    marked, since a wrong seed means a wrong layout, judge score and treasure list."""
    return r.get("confidence") == "high" or (r.get("confidence") == "medium" and bool(r.get("neighbor_ok")))


_NAMES: dict | None = None


def treasure_name(key: str) -> str:
    """In-game English name of a treasure (from CaveGen3's name list), else the internal name."""
    global _NAMES
    if _NAMES is None:
        try:
            _NAMES = json.loads((Path(__file__).parent / "data" / "treasure_names.json").read_text(encoding="utf-8"))
        except OSError:
            _NAMES = {}
    return _NAMES.get(key) or key.replace("_", " ")


def _pokos(t: dict | None) -> str:
    """'280 pokos: dia a red (180), tape yellow (100)' for a sublevel's treasure record."""
    if not t or t.get("pokos") is None:
        return ""
    picks = [c for c in t.get("collected", []) if c]
    names = ", ".join(f"{treasure_name(n)} ({p})" for n, p in picks)
    bug = t.get("bug_pokos")
    extra = f" + about {round(bug)} from creatures (estimated)" if bug and round(bug) else ""
    return f"{t['pokos']} pokos" + (f": {names}" if names else " (no treasure)") + extra


def chart_points(rows: list[dict], kind: str, tre: dict | None = None, actual: dict | None = None) -> list[dict]:
    """Per sublevel, in seconds against the median: judge2's estimate with how random layouts
    score, and the runner's actual net result when known."""
    pts = []
    for r in rows:
        label = f"{r['cave']} {r['sublevel']}"
        act = (actual or {}).get(str(r.get("frame")))
        pt = {"label": label, "anchor": f"{r['cave']}-{r['sublevel']}", "fixed": bool(r.get("judge_fixed")),
              "judge": None, "actual": act["net"] if act else None,
              "extra": _pokos((tre or {}).get(str(r.get("frame"))))}
        if luck.judged(r):
            ref = luck.reference(r, kind)
            pt.update(judge=luck.delta(r), beats=luck.faster_than(r, kind),
                      lo=float(np.percentile(ref, 5)), hi=float(np.percentile(ref, 95)), dist=ref.tolist())
        pts.append(pt)
    return pts


def _actual_html(a: dict | None, last: bool = False) -> str:
    if not a:
        why = ("last floor of the cave, and its results screen was not found in the video" if last
               else "no other high-confidence run of this sublevel to compare with")
        return f'<div class="verdict mid"><span class="lbl">Runner</span><span class="muted small">Not timed: {why}.</span></div>'
    rows = f'<dt>Time</dt><dd>{a["took"]:.1f} s <span class="muted">(median run {a["median_took"]:.1f} s)</span></dd>'
    if a.get("pokos") is not None:
        rows += f'<dt>Pokos</dt><dd>{a["pokos"]} <span class="muted">(median run {a["median_pokos"]:g})</span></dd>'
    if a.get("expected"):
        rows += (f'<dt>Layout</dt><dd>{a["expected"]:+.1f} s <span class="muted">(vs the median run\'s layout; '
                 f'{a["raw"]:+.1f} s vs the median run before allowing for it)</span></dd>')
    return (f'<div class="verdict {_tone(a["net"])}"><span class="lbl">Runner</span><span class="big">{a["net"]:+.1f} s</span>'
            f'<span>beyond the layout, pokos counted</span></div>'
            f'<dl>{rows}</dl>')


def write_page(out_dir: Path, rows: list[dict] | None = None, home: str | None = None,
               actual: dict | None = None) -> Path:
    """`actual`: entry frame -> the runner's measured result against the median run (see site.actuals)."""
    data = json.loads((out_dir / "judge.json").read_text(encoding="utf-8"))
    rows = mark_neighbors(rows if rows is not None else data["entries"])
    meta, kind = data.get("meta", {}), data.get("kind", "pod")
    run = meta.get("run", {})
    runner = ", ".join(p["name"] for p in run.get("players", [])) or out_dir.name
    t = run.get("time_seconds")
    run_time = f"{int(t // 3600)}:{int(t % 3600 // 60):02d}:{int(t % 60):02d}" if t else ""
    judged = [r for r in rows if luck.judged(r) and trusted(r)]
    n_fixed = sum(1 for r in rows if r.get("judge_fixed"))
    n_low = sum(1 for r in rows if not trusted(r))

    layouts = {p.name: p for p in (out_dir / "img").glob("layout_*.png")}

    def layout_for(r):
        return layouts.get(f"layout_{r['frame']}_{r['cave']}-{r['sublevel']}.png")

    actual = actual or {}
    total_luck = sum(luck.delta(r) for r in judged)
    measured = [actual[str(r["frame"])] for r in rows if str(r.get("frame")) in actual]
    total_actual = sum(a["net"] for a in measured) if measured else None
    beats = {r["frame"]: luck.faster_than(r, kind) for r in judged}
    best = max(judged, key=lambda r: beats[r["frame"]], default=None)
    worst = min(judged, key=lambda r: beats[r["frame"]], default=None)
    sims = luck.simulate(judged, kind) if judged else None
    pct = luck.percentile(total_luck, sims) if judged else None
    dist_chart = charts.distribution_chart(
        sims.tolist(), [{"x": total_luck, "main": True, "label": f"this run {total_luck:+.1f} s",
                         "tip": f"This run's layouts: {total_luck:+.1f} s against median layouts\n{luck.describe(pct)}"}],
        "This run's layout luck among random runs",
        "total seconds the layouts should save against median layouts (negative = luckier)",
        subtitle=f"{luck.SIMS:,} random runs, each with one random layout of each of the same {len(judged)} sublevels"
    ) if judged else ""

    def label(r):
        return f"{r['cave']} {r['sublevel']}"

    tre = treasures.load(out_dir)
    shown = [r if trusted(r) else {k: x for k, x in r.items() if not k.startswith("judge_")} for r in rows]
    chart = charts.timesave_chart(chart_points(shown, kind, tre, actual),
                                  "Layout luck and actual result per sublevel")

    sections = []
    for cave in dict.fromkeys(r["cave"] for r in rows):     # caves in the order they were played
        rs = [r for r in rows if r["cave"] == cave]
        if not rs:
            continue
        sub_judge = sum(luck.delta(r) for r in rs if luck.judged(r) and trusted(r))
        sub_act = [actual[str(r["frame"])]["net"] for r in rs if str(r.get("frame")) in actual]
        cards = []
        for n, r in enumerate(rs):
            p = layout_for(r)
            img = (f'<button class="shot" aria-label="Enlarge {html.escape(label(r))} layout">'
                   f'<img loading="lazy" src="img/{html.escape(p.name)}" alt="{html.escape(label(r))} layout"></button>'
                   if p else '<div class="shot empty">no render</div>')
            if r.get("judge_fixed"):
                verdict = (f'<div class="verdict fixed"><span class="big">Fixed floor</span></div>'
                           f'<p class="muted small">Every seed gives the same layout here, so there is no luck to measure.</p>')
            elif luck.judged(r):
                d = luck.delta(r)
                f = luck.faster_than(r, kind)
                est = r["judge2_score"] if luck.key(r) == "judge2" else r["judge_score"]
                med = r["judge2_median"] if luck.key(r) == "judge2" else r["judge_median"]
                skip = r.get("judge2_skip") or []
                verdict = (f'<div class="verdict {_tone(d)}"><span class="lbl">Layout</span>'
                           f'<span class="big">{d:+.1f} s</span><span>vs median layout</span></div>'
                           f'<div class="meter" title="{_beats(f)}"><span style="width:{f:.0f}%"></span></div>'
                           f'<dl><dt>Estimate</dt><dd>{est:.1f} s</dd>'
                           f'<dt>Median layout</dt><dd>{med:.1f} s</dd>'
                           f'<dt>Luck</dt><dd>{_beats(f)}</dd></dl>'
                           + ('<p class="muted small">Most layouts here are within a second of each other.</p>' if abs(d) < 1.0 else "")
                           + (f'<p class="muted small">The judge expects the runner to skip: '
                              f'{html.escape(", ".join(treasure_name(x) for x in skip))}</p>' if skip else ""))
            else:
                verdict = '<p class="muted">No judge for this sublevel.</p>'
            verdict += _actual_html(actual.get(str(r.get("frame"))), last=n == len(rs) - 1)
            pk = _pokos(tre.get(str(r.get("frame"))))
            body = img + verdict + (f'<p class="small">{html.escape(pk)}</p>' if pk else "")
            conf = "" if trusted(r) else ' <span class="tag">uncertain seed</span>'
            if not trusted(r):
                body = ('<p class="muted small hide-low">The seed could not be read with confidence, so this layout may be '
                        'wrong; it is left out of every total. Tick "show uncertain seeds" above to see it anyway.</p>'
                        f'<div class="low-only">{body}</div>')
            link = (f'<a href="{html.escape(r["link"])}" target="_blank" rel="noopener">{html.escape(r["time"])}</a>'
                    if r.get("link") else html.escape(r.get("time", "")))
            cards.append(f'''<article class="card{"" if trusted(r) else " low"}" id="{r["cave"]}-{r["sublevel"]}">
  <header><h3>{html.escape(label(r))}</h3><code>{html.escape(r["layout_seed"])}</code>{conf}</header>
  {body}
  <p class="muted small">Entered at {link} · <a href="{cg3_url(r)}" target="_blank" rel="noopener">open in CaveGen3</a>{"" if trusted(r) else " (may be wrong)"} · <a href="report.html#{r["cave"]}-{r["sublevel"] or 0}">how the seed was read</a></p>
</article>''')
        sections.append(f'''<section id="cave-{html.escape(cave)}">
  <h2>{html.escape(CAVE_NAMES.get(cave, cave))} <span class="muted">· {len(rs)} sublevels · layouts {_num(sub_judge)}{f" · runner {_num(sum(sub_act))}" if sub_act else ""}</span></h2>
  <div class="grid">{"".join(cards)}</div>
</section>''')

    title = f"{runner}{f' {run_time}' if run_time else ''} · layouts & luck"
    switch = ""
    jump = "".join(f'<a href="#cave-{html.escape(c)}">{html.escape(c)}</a>' for c in dict.fromkeys(r["cave"] for r in rows))
    page = f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(title)}</title>
<style>
:root {{ --bg:#f6f6f4; --fg:#1d1d1b; --muted:#6b6b66; --card:#fff; --line:#deded8;
        --good:#1f7a3a; --mid:#8a6a1f; --bad:#b42318; --goodbg:#e3f1e6; --midbg:#f3ecd9; --badbg:#f8e1df; --bar:#c9c9c2; }}
@media (prefers-color-scheme: dark) {{ :root {{ --bg:#161614; --fg:#ececea; --muted:#9a9a94; --card:#20201e; --line:#33332f;
        --good:#5cc27a; --mid:#d9b25a; --bad:#f0786d; --goodbg:#1d3324; --midbg:#352d19; --badbg:#3b2120; --bar:#3a3a36; }} }}
* {{ box-sizing:border-box; }}
body {{ background:var(--bg); color:var(--fg); font:15px/1.45 system-ui,sans-serif; margin:0; padding:24px 16px 48px; }}
main {{ max-width:1180px; margin:0 auto; }}
h1 {{ font-size:26px; margin:0 0 4px; }} h2 {{ font-size:19px; margin:36px 0 12px; }} h3 {{ font-size:16px; margin:0; }}
a {{ color:inherit; }} .muted {{ color:var(--muted); font-weight:400; }} .small {{ font-size:13px; }}
.lede {{ color:var(--muted); margin:0 0 20px; max-width:760px; }}
.stats {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(170px,1fr)); gap:10px; margin:18px 0; }}
.stat {{ background:var(--card); border:1px solid var(--line); border-radius:10px; padding:12px 14px; }}
.stat b {{ display:block; font-size:20px; font-weight:700; font-variant-numeric:tabular-nums; }} .stat > span {{ color:var(--muted); font-size:13px; }}
.stat.hero {{ grid-column:span 2; }} .stat.hero b {{ font-size:30px; }}
@media (max-width:480px) {{ .stat.hero {{ grid-column:span 2; }} }}
.dist {{ margin:0 0 18px; }}
@media (max-width:480px) {{ .stats {{ grid-template-columns:repeat(2,1fr); }} }}
.jump {{ position:sticky; top:0; z-index:5; display:flex; flex-wrap:wrap; gap:4px; padding:6px 0; margin:10px 0; background:var(--bg); }}
.jump a {{ font-size:13px; font-weight:600; text-decoration:none; padding:2px 10px; border-radius:999px;
  border:1px solid var(--line); background:var(--card); }}
section {{ scroll-margin-top:44px; }} .card {{ scroll-margin-top:48px; }}
.verdict.fixed {{ background:var(--bg); color:var(--muted); }}
.nav {{ font-size:14px; margin:0 0 14px; }}
.grid {{ display:grid; grid-template-columns:repeat(auto-fill,minmax(260px,1fr)); gap:14px; }}
.card {{ background:var(--card); border:1px solid var(--line); border-radius:12px; padding:12px; display:flex; flex-direction:column; gap:10px; }}
.card header {{ display:flex; gap:8px; align-items:baseline; flex-wrap:wrap; }}
code {{ font:13px ui-monospace,Consolas,monospace; color:var(--muted); }}
.tag {{ font-size:12px; border:1px solid var(--line); border-radius:999px; padding:0 8px; color:var(--mid); }}
.shot {{ display:block; padding:0; border:1px solid var(--line); border-radius:8px; background:#000; cursor:zoom-in;
         aspect-ratio:1; overflow:hidden; width:100%; }}
.shot img {{ width:100%; height:100%; object-fit:contain; display:block; }}
.shot.empty {{ display:grid; place-items:center; color:var(--muted); background:transparent; cursor:default; }}
.verdict {{ display:flex; align-items:baseline; gap:6px; border-radius:8px; padding:6px 10px; }}
.verdict .big {{ font-size:20px; font-weight:650; font-variant-numeric:tabular-nums; }}
.verdict.good {{ background:var(--goodbg); color:var(--good); }} .verdict.mid {{ background:var(--midbg); color:var(--mid); }}
.verdict.bad {{ background:var(--badbg); color:var(--bad); }}
.verdict .lbl {{ font-size:12px; font-weight:600; text-transform:uppercase; letter-spacing:.04em; min-width:38px; opacity:.8; }}
.verdict.mid {{ background:var(--bg); color:var(--muted); }}
.good-text {{ color:var(--good); }} .bad-text {{ color:var(--bad); }} .mid-text {{ color:var(--muted); }}
.meter {{ height:6px; background:var(--bar); border-radius:3px; overflow:hidden; }}
.meter span {{ display:block; height:100%; background:var(--fg); opacity:.7; }}
dl {{ display:grid; grid-template-columns:auto 1fr; gap:2px 12px; margin:0; font-size:13px; }}
dt {{ color:var(--muted); }} dd {{ margin:0; text-align:right; font-variant-numeric:tabular-nums; }}
.card p {{ margin:0; }}
.low-only {{ display:none; }} body.show-low .low-only {{ display:contents; }} body.show-low .hide-low {{ display:none; }}
.card.low {{ border-style:dashed; }}
.toggle {{ font-size:14px; margin:6px 0 0; display:flex; gap:6px; align-items:center; }}
dialog {{ border:none; padding:0; background:transparent; max-width:96vw; max-height:96vh; }}
dialog::backdrop {{ background:rgba(0,0,0,.8); }}
dialog img {{ max-width:96vw; max-height:92vh; display:block; border-radius:6px; }}
.note {{ font-size:13px; color:var(--muted); border-top:1px solid var(--line); margin-top:40px; padding-top:14px; max-width:820px; }}
{charts.CSS}
</style></head><body><main>
{switch}
<h1>{html.escape(title)}</h1>
<p class="lede">Pay Off Debt{f", {html.escape(run_time)}" if run_time else ""}{f", {html.escape(run.get('date', ''))}" if run.get('date') else ""}
{f' · <a href="{html.escape(run["weblink"])}" target="_blank" rel="noopener">speedrun.com</a>' if run.get("weblink") else ""}.
Every sublevel's layout was rebuilt from the seed read off the video and timed by a layout judge (CaveGen's judge,
re-tuned on these runs' real times), against the median of 1000 random layouts of the same sublevel: that is the
<b>layout luck</b>. <b>Runner</b> is what this run did against the median run, counting 2 pokos as 1 second, after taking out
what the layout alone should have changed.
Negative is faster, as on splits.</p>

{f'''<label class="toggle"><input type="checkbox" id="show-low"> Show uncertain seeds ({n_low} sublevel{"s" if n_low != 1 else ""};
  never counted in the totals or the chart)</label>''' if n_low else ""}
<div class="stats">
  <div class="stat hero"><b>{_num(total_luck)}</b><span>Layout luck over {len(judged)} sublevels{f": {luck.describe(pct)}" if pct is not None else ""}</span></div>
  {f'<div class="stat hero"><b>{_num(total_actual)}</b><span>Runner beyond the layouts over {len(measured)} sublevels, pokos counted</span></div>' if measured else ""}
  {f'<div class="stat"><b>{html.escape(label(best))}</b><span>luckiest: {_beats(beats[best["frame"]])}</span></div>' if best else ""}
  {f'<div class="stat"><b>{html.escape(label(worst))}</b><span>unluckiest: {_beats(beats[worst["frame"]])}</span></div>' if worst else ""}
  <div class="stat"><b>{len(rows) - n_low} of {len(rows)}</b><span>seeds read with confidence{f" ({n_fixed} fixed floors)" if n_fixed else ""}{f"; {n_low} uncertain" if n_low else ""}</span></div>
</div>
{dist_chart}

<nav class="jump" aria-label="Caves">{jump}</nav>
{chart}
<p class="legend muted small">Each dot is this run's layout; the grey shape is how 1000 random layouts of that sublevel
score, wider where more of them land, so a dot near the end of its shape is a big swing. Hover for details; click to
jump to the layout.</p>

{"".join(sections)}

<p class="note">The judge is CaveGen's Pay Off Debt heuristic (walking, carrying and fighting estimates), re-weighted
so that across these runs one predicted second is worth about one real second; it is still an estimate, not a
measured time. The run's luck percentile compares its total with {luck.SIMS:,} simulated runs that each drew one random
layout of every sublevel counted here. As on splits, negative means faster
than the median: green is good, red is bad. "Runner" is what the runner actually did on the sublevel, measured from one
entry screen to the next, against the median of the runs on this site, counting two pokos as one second. These
runs are personal bests, which drew lucky layouts more often than chance, so the median run usually had a good layout
(on SH 6 about 30 s better than the median layout); the judge's difference between this layout and the median run's is
taken out, so only the runner's own part is left. Only seeds read at high confidence count anywhere on this page; lower-confidence reads (dashed cards) are
hidden unless you ask for them, and are never added to the totals.</p>
</main>
<dialog id="zoom"><img alt=""></dialog>
<script>
const low = document.getElementById('show-low');
if (low) {{
  try {{ low.checked = localStorage.getItem('p2seeds-show-low') === '1'; }} catch (e) {{}}
  const apply = () => document.body.classList.toggle('show-low', low.checked);
  low.addEventListener('change', () => {{ apply(); try {{ localStorage.setItem('p2seeds-show-low', low.checked ? '1' : '0'); }} catch (e) {{}} }});
  apply();
}}
const dlg = document.getElementById('zoom'), big = dlg.querySelector('img');
document.querySelectorAll('button.shot').forEach(b => b.addEventListener('click', () => {{
  big.src = b.querySelector('img').src; big.alt = b.getAttribute('aria-label'); dlg.showModal();
}}));
dlg.addEventListener('click', () => dlg.close());
</script>
<script>{charts.TOOLTIP_JS}</script>
</body></html>'''
    dest = out_dir / "judge.html"
    from . import theme
    page = theme.apply(page, prefix="../", run=out_dir.name, active="judge", category=theme.category_of(kind, out_dir))
    dest.write_text(page, encoding="utf-8")
    return dest
