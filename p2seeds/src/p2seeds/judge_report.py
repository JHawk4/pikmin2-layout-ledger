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

from . import cavegen, charts, treasures
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
    return f"https://jhawk4.github.io/CaveGen3/?sublevel=pikmin2:{r['cave']}-{r['sublevel']}&seed={seed}"


def trusted(r: dict) -> bool:
    """Only high-confidence seeds feed totals, charts and the calibration; the rest are shown
    on request, marked, since a wrong seed means a wrong layout, judge score and treasure list."""
    return r.get("confidence") == "high"


def _pokos(t: dict | None) -> str:
    """'280 pokos: dia a red (180), tape yellow (100)' for a sublevel's treasure record."""
    if not t or t.get("pokos") is None:
        return ""
    picks = [c for c in t.get("collected", []) if c]
    names = ", ".join(f"{n.replace('_', ' ')} ({p})" for n, p in picks)
    return f"{t['pokos']} pokos" + (f": {names}" if names else " (no treasure)")


def chart_points(rows: list[dict], kind: str, tre: dict | None = None, actual: dict | None = None) -> list[dict]:
    """Per sublevel, in seconds against the median: the judge's estimate with the 5th/95th
    percentile of random layouts, and the runner's actual net result when known."""
    pts = []
    for r in rows:
        label = f"{r['cave']} {r['sublevel']}"
        act = (actual or {}).get(str(r.get("frame")))
        pt = {"label": label, "anchor": f"{r['cave']}-{r['sublevel']}", "fixed": bool(r.get("judge_fixed")),
              "judge": None, "actual": act["net"] if act else None,
              "extra": _pokos((tre or {}).get(str(r.get("frame"))))}
        if "judge_score" in r and not r.get("judge_fixed"):
            ref = cavegen.reference_scores(r["cave"], r["sublevel"], kind)
            med = r["judge_median"]
            pt.update(judge=_delta(r), beats=_faster_than(r),
                      lo=float(np.percentile(ref, 5)) - med, hi=float(np.percentile(ref, 95)) - med)
        pts.append(pt)
    return pts


def _actual_html(a: dict | None) -> str:
    if not a:
        return ('<div class="verdict mid"><span class="lbl">Run</span><span class="muted small">not measured '
                '(last sublevel of the cave, or no other runs)</span></div>')
    parts = [f'took {a["took"]:.1f} s vs {a["median_took"]:.1f} s']
    if a.get("pokos") is not None:
        parts.append(f'{a["pokos"]} pokos vs {a["median_pokos"]:g}')
    return (f'<div class="verdict {_tone(a["net"])}"><span class="lbl">Run</span><span class="big">{a["net"]:+.1f} s</span>'
            f'<span>net vs median run</span></div>'
            f'<p class="muted small">{"; ".join(parts)} (median of {a["n"]} runs)</p>')


def write_page(out_dir: Path, rows: list[dict] | None = None, home: str | None = None,
               actual: dict | None = None) -> Path:
    """`actual`: entry frame -> the runner's measured result against the median run (see site.actuals)."""
    data = json.loads((out_dir / "judge.json").read_text(encoding="utf-8"))
    rows = rows if rows is not None else data["entries"]
    meta, kind = data.get("meta", {}), data.get("kind", "pod")
    run = meta.get("run", {})
    runner = ", ".join(p["name"] for p in run.get("players", [])) or out_dir.name
    t = run.get("time_seconds")
    run_time = f"{int(t // 3600)}:{int(t % 3600 // 60):02d}:{int(t % 60):02d}" if t else ""
    judged = [r for r in rows if "judge_score" in r and not r.get("judge_fixed") and trusted(r)]
    n_fixed = sum(1 for r in rows if r.get("judge_fixed"))
    n_low = sum(1 for r in rows if not trusted(r))

    layouts = {p.name: p for p in (out_dir / "img").glob("layout_*.png")}

    def layout_for(r):
        return layouts.get(f"layout_{r['frame']}_{r['cave']}-{r['sublevel']}.png")

    actual = actual or {}
    total_judge = sum(_delta(r) for r in judged)
    j2 = [r for r in judged if r.get("judge2_score") is not None]
    total_judge2 = sum(r["judge2_vs_median"] for r in j2) if j2 else None
    measured = [actual[str(r["frame"])] for r in rows if str(r.get("frame")) in actual]
    total_actual = sum(a["net"] for a in measured) if measured else None
    avg_faster = sum(_faster_than(r) for r in judged) / max(1, len(judged))
    best = min(judged, key=lambda r: r["judge_rank"], default=None)
    worst = max(judged, key=lambda r: r["judge_rank"], default=None)

    def label(r):
        return f"{r['cave']} {r['sublevel']}"

    tre = treasures.load(out_dir)
    shown = [r if trusted(r) else {k: x for k, x in r.items() if not k.startswith("judge_")} for r in rows]
    chart = charts.timesave_chart(chart_points(shown, kind, tre, actual),
                                  "Judge estimate and actual result per sublevel")

    sections = []
    for cave in dict.fromkeys(r["cave"] for r in rows):     # caves in the order they were played
        rs = [r for r in rows if r["cave"] == cave]
        if not rs:
            continue
        sub_judge = sum(_delta(r) for r in rs if "judge_score" in r and not r.get("judge_fixed") and trusted(r))
        sub_act = [actual[str(r["frame"])]["net"] for r in rs if str(r.get("frame")) in actual]
        cards = []
        for r in rs:
            p = layout_for(r)
            img = (f'<button class="shot" aria-label="Enlarge {html.escape(label(r))} layout">'
                   f'<img loading="lazy" src="{_img(p)}" alt="{html.escape(label(r))} layout"></button>'
                   if p else '<div class="shot empty">no render</div>')
            if r.get("judge_fixed"):
                verdict = (f'<div class="verdict fixed"><span class="big">Fixed floor</span></div>'
                           f'<p class="muted small">Every seed gives the same judge estimate '
                           f'({r["judge_score"]:.1f} s), so the layout involves no luck.</p>')
            elif "judge_score" in r:
                f = _faster_than(r)
                verdict = (f'<div class="verdict {_tone(_delta(r))}"><span class="lbl">Judge</span>'
                           f'<span class="big">{_delta(r):+.1f} s</span><span>layout vs median</span></div>'
                           f'<div class="meter" title="faster than {f:.0f}% of layouts"><span style="width:{f:.0f}%"></span></div>'
                           f'<dl><dt>Judge estimate</dt><dd>{r["judge_score"]:.1f} s</dd>'
                           f'<dt>Median layout</dt><dd>{r["judge_median"]:.1f} s</dd>'
                           f'<dt>Faster than</dt><dd>{f:.0f}% of layouts</dd></dl>')
            else:
                verdict = '<p class="muted">CaveGen has no judge for this sublevel.</p>'
            if r.get("judge2_score") is not None and not r.get("judge_fixed"):
                d2 = r["judge2_vs_median"]
                skip = r.get("judge2_skip") or []
                verdict += (f'<div class="verdict {_tone(d2)}"><span class="lbl">Judge2</span>'
                            f'<span class="big">{d2:+.1f} s</span><span>layout vs median</span></div>'
                            + (f'<p class="muted small">judge2 expects the runner to skip: {html.escape(", ".join(skip))}</p>'
                               if skip else ""))
            verdict += _actual_html(actual.get(str(r.get("frame"))))
            pk = _pokos(tre.get(str(r.get("frame"))))
            body = img + verdict + (f'<p class="small">{html.escape(pk)}</p>' if pk else "")
            conf = "" if trusted(r) else f' <span class="tag">{html.escape(r["confidence"])}</span>'
            if not trusted(r):
                body = (f'<p class="muted small hide-low">The seed was read at {html.escape(r["confidence"])} confidence, so its '
                        f'layout, judge and pokos are left out. Tick "show lower-confidence reads" above to see them.</p>'
                        f'<div class="low-only">{body}</div>')
            link = (f'<a href="{html.escape(r["link"])}" target="_blank" rel="noopener">{html.escape(r["time"])}</a>'
                    if r.get("link") else html.escape(r.get("time", "")))
            cards.append(f'''<article class="card{"" if trusted(r) else " low"}" id="{r["cave"]}-{r["sublevel"]}">
  <header><h3>{html.escape(label(r))}</h3><code>{html.escape(r["layout_seed"])}</code>{conf}</header>
  {body}
  <p class="muted small">Entered at {link} · <a href="{cg3_url(r)}" target="_blank" rel="noopener">open in CaveGen3</a></p>
</article>''')
        sections.append(f'''<section>
  <h2>{html.escape(CAVE_NAMES.get(cave, cave))} <span class="muted">· {len(rs)} sublevels · judge {_num(sub_judge)}{f" · run {_num(sum(sub_act))} net" if sub_act else ""}</span></h2>
  <div class="grid">{"".join(cards)}</div>
</section>''')

    title = f"{runner} — layouts and judge report"
    page = f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(runner)} layout judge</title>
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
.stat b {{ display:block; font-size:22px; font-variant-numeric:tabular-nums; }} .stat span {{ color:var(--muted); font-size:13px; }}
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
{f'<p class="nav"><a href="{html.escape(home)}">← All runs</a></p>' if home else ""}
<h1>{html.escape(title)}</h1>
<p class="lede">Pay Off Debt{f", {html.escape(run_time)}" if run_time else ""}{f", {html.escape(run.get('date', ''))}" if run.get('date') else ""}
{f' · <a href="{html.escape(run["weblink"])}" target="_blank" rel="noopener">speedrun.com</a>' if run.get("weblink") else ""}.
Every sublevel's layout was rebuilt from the seed read off the video, then scored by CaveGen's <b>{html.escape(kind)}</b> judge:
an estimate of how long the layout takes to clear, compared with 1000 random layouts of the same sublevel.</p>

{f'''<label class="toggle"><input type="checkbox" id="show-low"> Show lower-confidence reads ({n_low} sublevel{"s" if n_low != 1 else ""};
  never counted in the totals or the chart)</label>''' if n_low else ""}
<div class="stats">
  <div class="stat"><b>{len(judged)}</b><span>high-confidence random-layout sublevels{f" (+{n_fixed} fixed floors)" if n_fixed else ""}</span></div>
  <div class="stat"><b>{_num(total_judge)}</b><span>judge: layouts vs median layouts</span></div>
  {f'<div class="stat"><b>{_num(total_judge2)}</b><span>judge2 (refit): layouts vs median layouts</span></div>' if j2 else ""}
  {f'<div class="stat"><b>{_num(total_actual)}</b><span>run: net vs median run ({len(measured)} sublevels)</span></div>' if measured else ""}
  <div class="stat"><b>{avg_faster:.0f}%</b><span>average share of layouts beaten</span></div>
  {f'<div class="stat"><b>{html.escape(label(best))}</b><span>luckiest: faster than {_faster_than(best):.0f}%</span></div>' if best else ""}
  {f'<div class="stat"><b>{html.escape(label(worst))}</b><span>unluckiest: faster than {_faster_than(worst):.0f}%</span></div>' if worst else ""}
</div>

{chart}
<p class="legend muted small">Each dot is this run's layout; the grey bar spans the 5th to 95th percentile of 1000 random
layouts, so a dot near or past the end of its bar is a big swing. Hover for details; click to jump to the layout.</p>

{"".join(sections)}

<p class="note">The judge is CaveGen's heuristic (walking, carrying and fighting estimates for the PoD route), not a
measured time, so treat the seconds as relative luck rather than exact savings. As on splits, negative means faster
than the median: green is good, red is bad. "Run" is what the runner actually did on the sublevel, measured from one
entry screen to the next, against the median of the runs on this site, counting two pokos as one second. Only seeds read at high confidence count anywhere on this page; lower-confidence reads (dashed cards) are
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
    dest.write_text(page, encoding="utf-8")
    return dest
