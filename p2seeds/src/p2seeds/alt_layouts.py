"""Alternate designs of a run's "Layouts & luck" page, to compare with judge.html.

  <run>/judge_a.html   Table: one dense, sortable row per sublevel
  <run>/judge_b.html   Story: the run's luck and the runner's time as a race through the run,
                       then each cave as a strip of small cards that open for details
  <run>/judge_c.html   Spotlight: the biggest swings first, with large layouts; the rest as a
                       grid of thumbnails

All three show the same numbers as judge.html (judge2's layout luck, the runner's net result,
pokos), only arranged differently. A bar at the top switches between the four.
"""

from __future__ import annotations

import html
import json
from pathlib import Path

import numpy as np

from . import charts, judge_report, luck, theme, treasures
from .judge_report import CAVE_NAMES, _beats, _num, _pokos, _tone, cg3_url, treasure_name, trusted

VARIANTS = [("judge.html", "Current"), ("judge_a.html", "A · Table"), ("judge_b.html", "B · Story"),
            ("judge_c.html", "C · Spotlight")]


def _rows(out_dir: Path, actual: dict) -> tuple[dict, list[dict]]:
    data = json.loads((out_dir / "judge.json").read_text(encoding="utf-8"))
    meta, kind = data.get("meta", {}), data.get("kind", "pod")
    run = meta.get("run", {})
    tre = treasures.load(out_dir)
    imgs = {p.name for p in (out_dir / "img").glob("layout_*.png")}
    rows = []
    for n, r in enumerate(data["entries"]):
        if not r.get("cave") or not r.get("sublevel"):
            continue
        img = f"layout_{r['frame']}_{r['cave']}-{r['sublevel']}.png"
        ok = trusted(r)
        judged = ok and luck.judged(r)
        act = actual.get(str(r["frame"]))
        t = tre.get(str(r["frame"]))
        rows.append({
            "label": f"{r['cave']} {r['sublevel']}", "cave": r["cave"], "sub": r["sublevel"],
            "anchor": f"{r['cave']}-{r['sublevel']}", "seed": r.get("layout_seed", ""),
            "img": f"img/{img}" if img in imgs else None, "trusted": ok, "fixed": bool(r.get("judge_fixed")),
            "delta": luck.delta(r) if judged else None,
            "pct": luck.faster_than(r, kind) if judged else None,
            "dist": luck.reference(r, kind) if judged else None,
            "skip": [treasure_name(x) for x in (r.get("judge2_skip") or [])] if judged else [],
            "net": act["net"] if act else None, "took": act["took"] if act else None,
            "median_took": act["median_took"] if act else None,
            "pokos": act["pokos"] if act else (t or {}).get("pokos"),
            "median_pokos": act["median_pokos"] if act else None,
            "pokos_text": _pokos(t), "link": r.get("link"), "time": r.get("time", ""), "cg3": cg3_url(r),
        })
    for r in rows:      # preformatted (f-strings can't nest quotes before Python 3.12)
        d, pc, nt = r["delta"], r["pct"], r["net"]
        r.update(dv="" if d is None else f"{d:.2f}", pv="" if pc is None else f"{pc:.1f}",
                 nv="" if nt is None else f"{nt:.2f}", pct_txt="" if pc is None else f"{pc:.0f}%",
                 dshort="" if d is None else f"{d:+.0f}s")
    return {"run": run, "kind": kind, "runner": ", ".join(p["name"] for p in run.get("players", [])) or out_dir.name,
            "time": run.get("time_seconds")}, rows


def _fmt_time(t) -> str:
    return f"{int(t // 3600)}:{int(t % 3600 // 60):02d}:{int(t % 60):02d}" if t else ""


def mini_violin(dist, value: float | None, lo: float, hi: float, w: int = 150, h: int = 22) -> str:
    """A small horizontal violin of `dist` from lo to hi seconds, with this layout as a tick."""
    if dist is None:
        return ""
    q = np.sort(np.asarray(dist))
    if len(q) > 200:
        q = q[np.linspace(0, len(q) - 1, 200).astype(int)]
    x = lambda v: 2 + (min(hi, max(lo, v)) - lo) / ((hi - lo) or 1) * (w - 4)
    a, b = float(q[int(0.01 * (len(q) - 1))]), float(q[int(0.99 * (len(q) - 1))])
    if b - a < 1e-6:
        shape = f'<rect x="{x(a) - 1:.1f}" y="{h / 2 - 3}" width="2" height="6" fill="var(--range)"/>'
    else:
        grid = [a + (b - a) * k / 24 for k in range(25)]
        dens = charts._density(list(q), grid)
        top = max(dens) or 1
        half = h / 2 - 2
        up = [f"{x(g):.1f},{h / 2 - half * d / top - .5:.1f}" for g, d in zip(grid, dens)]
        dn = [f"{x(g):.1f},{h / 2 + half * d / top + .5:.1f}" for g, d in zip(reversed(grid), reversed(dens))]
        shape = f'<polygon points="{" ".join(up + dn)}" fill="var(--range)"/>'
    zero = f'<line x1="{x(0):.1f}" x2="{x(0):.1f}" y1="1" y2="{h - 1}" stroke="var(--ink-3)" stroke-width="1"/>'
    mark = ""
    if value is not None:
        col = "var(--good-mark)" if value < 0 else "var(--bad-mark)"
        mark = (f'<line x1="{x(value):.1f}" x2="{x(value):.1f}" y1="0" y2="{h}" stroke="{col}" stroke-width="2.5"/>')
    return f'<svg class="mv viz-root" viewBox="0 0 {w} {h}" width="{w}" height="{h}" aria-hidden="true">{shape}{zero}{mark}</svg>'


def _switcher(current: str) -> str:
    links = " · ".join(f'<b>{label}</b>' if href == current else f'<a href="{href}">{label}</a>' for href, label in VARIANTS)
    return (f'<div class="switcher">Draft layouts of this page, to compare: {links}</div>')


CSS = """
:root { --bg:#f6f6f4; --fg:#1d1d1b; --muted:#6b6b66; --card:#fff; --line:#deded8; --good:#1f7a3a; --bad:#b42318;
        --goodbg:#e3f1e6; --badbg:#f8e1df; }
@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) { --bg:#161614; --fg:#ececea; --muted:#9a9a94;
  --card:#20201e; --line:#33332f; --good:#5cc27a; --bad:#f0786d; --goodbg:#1d3324; --badbg:#3b2120; } }
:root[data-theme="dark"] { --bg:#161614; --fg:#ececea; --muted:#9a9a94; --card:#20201e; --line:#33332f;
  --good:#5cc27a; --bad:#f0786d; --goodbg:#1d3324; --badbg:#3b2120; }
* { box-sizing:border-box; }
body { background:var(--bg); color:var(--fg); font:15px/1.45 system-ui,sans-serif; margin:0; padding:24px 16px 48px; }
main { max-width:1180px; margin:0 auto; }
h1 { font-size:26px; margin:0 0 4px; } h2 { font-size:19px; margin:30px 0 10px; } h3 { font-size:15px; margin:0; }
a { color:inherit; } .muted { color:var(--muted); } .small { font-size:13px; }
.good-text { color:var(--good); } .bad-text { color:var(--bad); } .mid-text { color:var(--muted); }
.switcher { font-size:13px; background:var(--card); border:1px dashed var(--line); border-radius:8px; padding:6px 10px;
  margin:0 0 14px; display:inline-block; }
.heads { display:flex; flex-wrap:wrap; gap:10px 28px; align-items:baseline; margin:10px 0 16px; }
.heads div b { display:block; font-size:30px; font-variant-numeric:tabular-nums; line-height:1.1; }
.heads div > span { color:var(--muted); font-size:13px; }
.tablewrap { overflow-x:auto; background:var(--card); border:1px solid var(--line); border-radius:10px; }
table { border-collapse:collapse; width:100%; font-size:14px; }
th, td { text-align:left; padding:5px 9px; border-bottom:1px solid var(--line); white-space:nowrap; vertical-align:middle; }
th { color:var(--muted); font-weight:500; position:sticky; top:0; background:var(--card); z-index:1; }
th[data-sort] { cursor:pointer; } th[aria-sort="ascending"]::after { content:" ▲"; } th[aria-sort="descending"]::after { content:" ▼"; }
td.num, th.num { text-align:right; font-variant-numeric:tabular-nums; }
tr.cave-row td { background:var(--bg); font-weight:700; font-size:13px; }
tr.low td { opacity:.5; }
.thumb { width:44px; height:44px; object-fit:contain; background:#000; border-radius:4px; display:block; cursor:zoom-in; }
.mv { display:block; }
.strip { display:flex; gap:8px; overflow-x:auto; padding:4px 2px 10px; }
.mini { flex:0 0 150px; background:var(--card); border:1px solid var(--line); border-radius:10px; padding:6px; font-size:12px; }
.mini img { width:100%; aspect-ratio:1; object-fit:contain; background:#000; border-radius:6px; display:block; cursor:zoom-in; }
.mini .nums { display:flex; justify-content:space-between; margin-top:4px; font-variant-numeric:tabular-nums; font-weight:600; }
.mini.low { border-style:dashed; opacity:.6; }
.mini details summary { color:var(--muted); cursor:pointer; margin-top:3px; }
.mini dl { display:grid; grid-template-columns:auto 1fr; gap:1px 8px; margin:4px 0 0; }
.mini dt { color:var(--muted); } .mini dd { margin:0; text-align:right; }
.spot { display:grid; grid-template-columns:repeat(auto-fill,minmax(330px,1fr)); gap:14px; }
.spot article { background:var(--card); border:1px solid var(--line); border-radius:12px; padding:12px; display:grid;
  grid-template-columns:150px 1fr; gap:12px; }
.spot img { width:150px; height:150px; object-fit:contain; background:#000; border-radius:8px; cursor:zoom-in; }
.spot .big { font-size:26px; font-weight:700; font-variant-numeric:tabular-nums; }
.tiles { display:grid; grid-template-columns:repeat(auto-fill,minmax(96px,1fr)); gap:8px; }
.tile { position:relative; display:block; background:#000; border-radius:8px; overflow:hidden; border:2px solid transparent; }
.tile img { width:100%; aspect-ratio:1; object-fit:contain; display:block; }
.tile span { position:absolute; left:4px; bottom:4px; font-size:11px; font-weight:700; background:rgba(0,0,0,.7); color:#fff;
  border-radius:4px; padding:0 4px; font-variant-numeric:tabular-nums; }
.tile.good { border-color:var(--good); } .tile.bad { border-color:var(--bad); }
.tile em { position:absolute; right:4px; top:4px; font-style:normal; font-size:11px; background:rgba(0,0,0,.7); color:#fff;
  border-radius:4px; padding:0 4px; }
dialog { border:none; padding:0; background:transparent; max-width:96vw; max-height:96vh; }
dialog::backdrop { background:rgba(0,0,0,.8); } dialog img { max-width:96vw; max-height:92vh; display:block; border-radius:6px; }
@media (max-width:520px) { .spot article { grid-template-columns:1fr; } .spot img { width:100%; height:auto; aspect-ratio:1; } }
"""

ZOOM_JS = """
const dlg = document.getElementById('zoom'), big = dlg.querySelector('img');
document.querySelectorAll('img[data-zoom]').forEach(im => im.addEventListener('click', e => {
  e.preventDefault(); big.src = im.src; dlg.showModal(); }));
dlg.addEventListener('click', () => dlg.close());
"""

SORT_JS = """
(() => { const t = document.getElementById('subs'); if (!t) return; const body = t.tBodies[0];
  t.querySelectorAll('th[data-sort]').forEach(th => th.addEventListener('click', () => {
    const col = [...th.parentNode.children].indexOf(th), up = th.getAttribute('aria-sort') !== 'ascending';
    t.querySelectorAll('th').forEach(x => x.removeAttribute('aria-sort'));
    th.setAttribute('aria-sort', up ? 'ascending' : 'descending');
    body.querySelectorAll('tr.cave-row').forEach(r => r.remove());
    const key = r => { const v = r.children[col].dataset.v; return v === undefined || v === '' ? NaN : +v; };
    [...body.rows].sort((a, b) => { const x = key(a), y = key(b);
      return (isNaN(x) - isNaN(y)) || (up ? x - y : y - x); }).forEach(r => body.appendChild(r));
  }));
})();
"""


def _heads(info: dict, rows: list[dict]) -> tuple[str, str]:
    jd = [r for r in rows if r["delta"] is not None]
    tot = sum(r["delta"] for r in jd)
    nets = [r["net"] for r in rows if r["net"] is not None]
    pct = None
    if jd:
        sims = np.zeros(luck.SIMS)
        rng = np.random.default_rng(1)
        for r in jd:
            sims += rng.choice(r["dist"], luck.SIMS)
        pct = luck.percentile(tot, sims)
    heads = (f'<div class="heads"><div><b>{_num(tot)}</b><span>layout luck, {luck.describe(pct) if pct is not None else ""}</span></div>'
             + (f'<div><b>{_num(sum(nets))}</b><span>runner vs field, net of pokos ({len(nets)} sublevels)</span></div>' if nets else "")
             + '</div>')
    return heads, (f"{tot:+.1f}" if jd else "")


def _page(info: dict, name: str, body: str, out_dir: Path, extra_js: str = "") -> None:
    title = f"{info['runner']} {_fmt_time(info['time'])} · layouts & luck"
    page = f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(title)}</title><meta name="robots" content="noindex">
<style>{CSS}
{charts.CSS}</style></head><body><main>
{_switcher(name)}
<h1>{html.escape(title)}</h1>
{body}
</main>
<dialog id="zoom"><img alt=""></dialog>
<script>{ZOOM_JS}</script><script>{SORT_JS}</script><script>{charts.TOOLTIP_JS}</script>{extra_js}
</body></html>'''
    page = theme.apply(page, prefix="../", run=out_dir.name, active="judge")
    (out_dir / name).write_text(page, encoding="utf-8")


def _lohi(rows):
    vals = [v for r in rows if r["dist"] is not None for v in (np.percentile(r["dist"], 1), np.percentile(r["dist"], 99))]
    vals += [r["delta"] for r in rows if r["delta"] is not None]
    return (min(vals + [-10]), max(vals + [10]))


def variant_a(info, rows, out_dir):
    """Table: every sublevel one row, sortable, with a small violin of random layouts."""
    lo, hi = _lohi(rows)
    trs, cave = [], None
    for r in rows:
        if r["cave"] != cave:
            cave = r["cave"]
            trs.append(f'<tr class="cave-row"><td colspan="8">{html.escape(CAVE_NAMES.get(cave, cave))}</td></tr>')
        img = (f'<a href="{html.escape(r["cg3"])}" target="_blank" rel="noopener"><img class="thumb" data-zoom loading="lazy" '
               f'src="{r["img"]}" alt="{r["label"]} layout"></a>') if r["img"] else ""
        luck_cell = ("fixed floor" if r["fixed"] else "uncertain seed" if not r["trusted"] else "")
        pk = (f'{r["pokos"]}' + (f' <span class="muted">({r["pokos"] - r["median_pokos"]:+g})</span>'
                                 if r["median_pokos"] is not None and r["pokos"] is not None else "")) if r["pokos"] is not None else ""
        tip = r["pokos_text"] + (f"\nThe judge expects a skip: {', '.join(r['skip'])}" if r["skip"] else "")
        vid = (f'<a href="{html.escape(r["link"])}" target="_blank" rel="noopener">{html.escape(r["time"])}</a>'
               if r["link"] else html.escape(r["time"]))
        trs.append(
            f'<tr class="{"" if r["trusted"] else "low"}"><td data-v="{rows.index(r)}"><b>{r["label"]}</b></td><td>{img}</td>'
            f'<td class="num" data-v="{r["dv"]}">'
            f'{_num(r["delta"]) if r["delta"] is not None else f"<span class=muted>{luck_cell}</span>"}</td>'
            f'<td>{mini_violin(r["dist"], r["delta"], lo, hi)}</td>'
            f'<td class="num" data-v="{r["pv"]}">{r["pct_txt"]}</td>'
            f'<td class="num" data-v="{r["nv"]}">{_num(r["net"]) if r["net"] is not None else ""}</td>'
            f'<td class="num" data-tip="{html.escape(tip)}" tabindex="0">{pk}</td><td>{vid}</td></tr>')
    heads, _ = _heads(info, rows)
    body = f'''{heads}
<p class="muted small">One row per sublevel. <b>Layout</b>: seconds the layout should save against the median random layout
(negative = faster). The grey shape is how 1000 random layouts score, the tick is this one. <b>Beats</b>: share of random
layouts it beats. <b>Runner</b>: what the runner actually did against the median run, net of pokos (2 pokos = 1 s).
Click a column to sort, a picture to enlarge it.</p>
<div class="tablewrap"><table id="subs"><thead><tr><th data-sort>Sublevel</th><th></th><th class="num" data-sort>Layout</th>
<th>vs random layouts <span class="muted">({lo:+.0f} to {hi:+.0f} s)</span></th><th class="num" data-sort>Beats</th>
<th class="num" data-sort>Runner</th><th class="num">Pokos (vs median)</th><th>Video</th></tr></thead>
<tbody>{"".join(trs)}</tbody></table></div>'''
    _page(info, "judge_a.html", body, out_dir)


def _race(rows) -> str:
    """Running totals through the run: the layouts' luck and the runner's net time."""
    W, H, L, R, T, B = 960, 300, 52, 110, 26, 48
    lk, rn, labels = [0.0], [0.0], [""]
    a = b = 0.0
    for r in rows:
        a += r["delta"] or 0.0
        b += r["net"] or 0.0
        lk.append(a)
        rn.append(b)
        labels.append(r["label"])
    vals = lk + rn
    ticks = charts.nice_ticks(min(vals + [0]), max(vals + [0]), 5)
    x = charts._scale(0, len(rows), L, W - R)
    y = charts._scale(ticks[0], ticks[-1], H - B, T)
    out = [f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="Luck and time through the run">',
           f'<text class="ttl" x="{L}" y="14">Through the run: running totals, seconds vs the median (negative = ahead)</text>']
    for t in ticks:
        out.append(f'<line class="{"zero" if t == 0 else "grid"}" x1="{L}" x2="{W - R}" y1="{y(t):.1f}" y2="{y(t):.1f}"/>'
                   f'<text x="{L - 6}" y="{y(t) + 4:.1f}" text-anchor="end">{t:+g}</text>')
    cave = None
    for k, r in enumerate(rows, start=1):
        if r["cave"] != cave:
            cave = r["cave"]
            out.append(f'<line class="grid" x1="{x(k - .5):.1f}" x2="{x(k - .5):.1f}" y1="{T}" y2="{H - B + 6}"/>'
                       f'<text x="{x(k - .5) + 3:.1f}" y="{H - B + 18}" style="font-weight:600">{cave}</text>')
    for vals_, col, name in ((lk, "var(--series-1)", "layout luck"), (rn, "var(--series-2)", "runner vs field")):
        d = " ".join(f"{'M' if k == 0 else 'L'}{x(k):.1f},{y(v):.1f}" for k, v in enumerate(vals_))
        out.append(f'<path d="{d}" fill="none" stroke="{col}" stroke-width="2.2" stroke-linejoin="round"/>')
        out.append(f'<text x="{x(len(rows)) + 6:.1f}" y="{y(vals_[-1]) + 4:.1f}" style="fill:{col};font-weight:600">'
                   f'{name} {vals_[-1]:+.0f} s</text>')
    for k, r in enumerate(rows, start=1):
        tip = (f"after {r['label']}\nlayout luck so far {lk[k]:+.1f} s ({_signed(r['delta'])} here)\n"
               f"runner so far {rn[k]:+.1f} s ({_signed(r['net'])} here)")
        out.append(f'<a href="#{r["anchor"]}"><rect class="hit" tabindex="-1" x="{x(k - .5):.1f}" y="{T}" '
                   f'width="{x(1) - x(0):.1f}" height="{H - B - T}" data-tip="{html.escape(tip)}"/></a>')
    out.append(f'<text x="{(L + W - R) / 2:.0f}" y="{H - 6}" text-anchor="middle">sublevels in the order played</text>')
    out.append("</svg>")
    return f'<div class="chart viz-root">{"".join(out)}</div>'


def _signed(v) -> str:
    return "–" if v is None else f"{v:+.1f} s"


def variant_b(info, rows, out_dir):
    """Story: the race chart, then each cave as a strip of small cards."""
    heads, _ = _heads(info, rows)
    caves = []
    for cave in dict.fromkeys(r["cave"] for r in rows):
        rs = [r for r in rows if r["cave"] == cave]
        lk = sum(r["delta"] or 0 for r in rs)
        rn = [r["net"] for r in rs if r["net"] is not None]
        cards = []
        for r in rs:
            img = f'<img data-zoom loading="lazy" src="{r["img"]}" alt="{r["label"]} layout">' if r["img"] else ""
            dl = (f'<dl><dt>Beats</dt><dd>{r["pct_txt"]}{" of layouts" if r["pct_txt"] else ""}</dd>'
                  + (f'<dt>Took</dt><dd>{r["took"]:.1f} s (median {r["median_took"]:.1f})</dd>' if r["took"] is not None else "")
                  + (f'<dt>Pokos</dt><dd>{r["pokos"]}' + (f' (median {r["median_pokos"]:g})' if r["median_pokos"] is not None else "") + '</dd>'
                     if r["pokos"] is not None else "")
                  + '</dl>'
                  + (f'<p class="muted">{html.escape(r["pokos_text"])}</p>' if r["pokos_text"] else "")
                  + (f'<p class="muted">Judge expects a skip: {html.escape(", ".join(r["skip"]))}</p>' if r["skip"] else "")
                  + f'<p><a href="{html.escape(r["cg3"])}" target="_blank" rel="noopener">CaveGen3</a>'
                  + (f' · <a href="{html.escape(r["link"])}" target="_blank" rel="noopener">video</a>' if r["link"] else "")
                  + f' · <a href="report.html#{r["anchor"]}">seed</a></p>')
            note = "fixed" if r["fixed"] else "uncertain" if not r["trusted"] else ""
            cards.append(f'<div class="mini{"" if r["trusted"] else " low"}" id="{r["anchor"]}"><b>{r["label"]}</b> '
                         f'<span class="muted">{note}</span>{img}'
                         f'<div class="nums"><span title="layout luck">{_num(r["delta"]) if r["delta"] is not None else "–"}</span>'
                         f'<span title="runner vs field">{_num(r["net"]) if r["net"] is not None else "–"}</span></div>'
                         f'<details><summary>details</summary>{dl}</details></div>')
        caves.append(f'<h2>{html.escape(CAVE_NAMES.get(cave, cave))} <span class="muted small">layouts {_num(lk)}'
                     f'{f" · runner {_num(sum(rn))}" if rn else ""}</span></h2><div class="strip">{"".join(cards)}</div>')
    body = f'''{heads}
{_race(rows)}
<p class="muted small">Blue: how much time the layouts handed the runner so far, against median layouts. Orange: how far
ahead of the median run the runner actually was, net of pokos. When orange falls faster than blue, the runner was beating
the field beyond what the layouts gave. Each card below shows layout luck (left) and the runner's result (right).</p>
{"".join(caves)}'''
    _page(info, "judge_b.html", body, out_dir)


def variant_c(info, rows, out_dir):
    """Spotlight: the biggest swings first, then everything as a grid of thumbnails."""
    heads, _ = _heads(info, rows)
    jd = [r for r in rows if r["delta"] is not None]
    lo, hi = _lohi(rows)

    def card(r):
        img = f'<img data-zoom loading="lazy" src="{r["img"]}" alt="{r["label"]} layout">' if r["img"] else "<div></div>"
        return (f'<article id="{r["anchor"]}">{img}<div><h3>{r["label"]} <span class="muted small">'
                f'{html.escape(CAVE_NAMES.get(r["cave"], r["cave"]))}</span></h3>'
                f'<div class="big">{_num(r["delta"])}</div><div class="muted small">{_beats(r["pct"])}</div>'
                f'{mini_violin(r["dist"], r["delta"], lo, hi, w=170)}'
                + (f'<p class="small">Runner: {_num(r["net"])} net vs the median run</p>' if r["net"] is not None else "")
                + (f'<p class="muted small">{html.escape(r["pokos_text"])}</p>' if r["pokos_text"] else "")
                + f'<p class="small"><a href="{html.escape(r["cg3"])}" target="_blank" rel="noopener">CaveGen3</a>'
                + (f' · <a href="{html.escape(r["link"])}" target="_blank" rel="noopener">video {html.escape(r["time"])}</a>' if r["link"] else "")
                + '</p></div></article>')
    lucky = sorted([r for r in jd if r["delta"] < 0], key=lambda r: r["delta"])[:4]
    unlucky = sorted([r for r in jd if r["delta"] > 0], key=lambda r: -r["delta"])[:4]
    tiles = []
    for r in rows:
        tone = _tone(r["delta"]) if r["delta"] is not None else ""
        tip = (f"{r['label']}\nlayout {_signed(r['delta'])}" + (f" ({_beats(r['pct'])})" if r["pct"] is not None else "")
               + f"\nrunner {_signed(r['net'])} net" + (f"\n{r['pokos_text']}" if r["pokos_text"] else ""))
        inner = (f'<img loading="lazy" src="{r["img"]}" alt="">' if r["img"] else '<div style="aspect-ratio:1"></div>')
        tiles.append(f'<a class="tile {tone}" href="{html.escape(r["cg3"])}" target="_blank" rel="noopener" data-tip="{html.escape(tip)}">'
                     f'{inner}<span>{r["label"]} {r["dshort"]}</span>'
                     f'{"<em>?</em>" if not r["trusted"] else ""}</a>')
    body = f'''{heads}
<h2>Luckiest layouts</h2><div class="spot">{"".join(card(r) for r in lucky)}</div>
<h2>Unluckiest layouts</h2><div class="spot">{"".join(card(r) for r in unlucky)}</div>
<h2>Every sublevel</h2>
<p class="muted small">Green border: a faster-than-median layout; red: slower. The number is the layout's luck in seconds.
Hover for the runner's result and pokos; click to open the layout in CaveGen3. ? = the seed is uncertain.</p>
<div class="tiles">{"".join(tiles)}</div>'''
    _page(info, "judge_c.html", body, out_dir)


def write(out_dir: Path, actual: dict | None = None) -> None:
    info, rows = _rows(Path(out_dir), actual or {})
    if not rows:
        return
    variant_a(info, rows, Path(out_dir))
    variant_b(info, rows, Path(out_dir))
    variant_c(info, rows, Path(out_dir))
