"""A Pay Off Debt or All Treasures run's "Layouts" page (<run>/judge.html), top to bottom:

  1. headline numbers: layout luck against median layouts, its percentile among random runs,
     and the runner's own time saved
  2. every sublevel as a row: how 1000 random layouts score (a sideways violin), this layout
     (a tick) and the runner (a diamond)
  3. the run as a story: running totals of luck and of the runner's own time
  4. a scatter of the judge's layout difference against the runner's time, per sublevel
  5. a compact sortable table
  6. small cards: the luckiest and unluckiest layouts, the runner's best and worst sublevels,
     then every cave in story order

The runner's numbers come from site.actuals: against the median run on this site, with the
judge's difference between this layout and the median run's taken out ("beyond the layout"),
or against par, a median runner on a median layout (the diamonds in the sublevel chart).
"""

from __future__ import annotations

import html
import json
from pathlib import Path

import numpy as np

from . import charts, judge_report, luck, theme, treasures
from .judge_report import CAVE_NAMES, _beats, _num, _pokos, cg3_url, treasure_name, trusted

SPOTLIGHT = 5        # luckiest and unluckiest layouts, best and worst sublevels, shown first


def _rows(out_dir: Path, actual: dict) -> tuple[dict, list[dict]]:
    data = json.loads((out_dir / "judge.json").read_text(encoding="utf-8"))
    meta, kind = data.get("meta", {}), data.get("kind", "pod")
    run = meta.get("run", {})
    tre = treasures.load(out_dir)
    imgs = {p.name for p in (out_dir / "img").glob("layout_*.png")}
    rows = []
    for r in judge_report.mark_revisits(judge_report.mark_neighbors(data["entries"])):
        if not r.get("cave") or not r.get("sublevel"):
            continue
        img = f"layout_{r['frame']}_{r['cave']}-{r['sublevel']}.png"
        ok = trusted(r)
        judged = ok and luck.judged(r) and not r.get("revisit")      # purple-farm visits are not totalled
        act = actual.get(str(r["frame"]))
        t = tre.get(str(r["frame"]))
        k2 = luck.key(r) == "judge2"
        rows.append({
            "entry": r, "label": f"{r['cave']} {r['sublevel']}", "cave": r["cave"], "sub": r["sublevel"],
            "anchor": f"{r['cave']}-{r['sublevel']}", "seed": r.get("layout_seed", ""),
            "img": f"img/{img}" if img in imgs else None, "trusted": ok, "fixed": bool(r.get("judge_fixed")),
            "score": (r.get("judge2_score") if k2 else r.get("judge_score")) if judged else None,
            "median": (r.get("judge2_median") if k2 else r.get("judge_median")) if judged else None,
            "delta": luck.delta(r) if judged else None,
            "pct": luck.faster_than(r, kind) if judged else None,
            "dist": luck.reference(r, kind) if judged else None,
            "skip": [treasure_name(x) for x in (r.get("judge2_skip") or [])] if judged else [],
            "net": act["net"] if act else None, "par": act.get("par") if act else None, "raw": act.get("raw") if act else None,
            "expected": act.get("expected") if act else None, "median_luck": act.get("median_luck") if act else None,
            "took": act["took"] if act else None, "median_took": act["median_took"] if act else None,
            "pokos": act["pokos"] if act else (t or {}).get("pokos"),
            "median_pokos": act["median_pokos"] if act else None,
            "pokos_text": _missing(r) if kind == "at" else _pokos(t), "link": r.get("link"), "time": r.get("time", ""), "cg3": cg3_url(r),
        })
    return {"run": run, "kind": kind, "runner": ", ".join(p["name"] for p in run.get("players", [])) or out_dir.name,
            "time": run.get("time_seconds")}, rows


def _missing(r: dict) -> str:
    """All Treasures: what the layout lacks (a spawning quirk that costs the runner time)."""
    m = r.get("judge2_missing") or {}
    bits = []
    if m.get("treasures"):
        bits.append(f"{m['treasures']} treasure{'s' if m['treasures'] != 1 else ''}")
    if m.get("purples"):
        bits.append(f"{m['purples']} purple flower{'s' if m['purples'] != 1 else ''}")
    note = f"Missing from this layout: {' and '.join(bits)}." if bits else ""
    if r.get("revisit"):
        note = (note + " " if note else "") + "A purple-farm visit (the cave is entered again later): not counted."
    return note


AT_TEXT = [   # (Pay Off Debt wording, All Treasures wording) in the finished page
    (", pokos counted (2 = 1 s)", ""),
    (", pokos counted", ""),
    ("Pay Off Debt judge, refit on these runs' real times", "All Treasures judge, with its walking, carrying, enemy and gate "
     "times weighted as the Pay Off Debt judge refit on real times, which matches All Treasures runs too"),
    (", counting\n2 pokos as 1 second,", ","),
]


def _fmt_time(t) -> str:
    return f"{int(t // 3600)}:{int(t % 3600 // 60):02d}:{int(t % 60):02d}" if t else ""


def _signed(v) -> str:
    return "–" if v is None else f"{v:+.1f} s"


def _v(x, f="{:.2f}") -> str:
    return "" if x is None else f.format(x)


def _tone(v) -> str:
    return "" if v is None or abs(v) < 0.5 else "good-text" if v < 0 else "bad-text"


CSS = """
:root { --bg:#f6f6f4; --fg:#1d1d1b; --muted:#6b6b66; --card:#fff; --line:#deded8; --good:#1f7a3a; --bad:#b42318; }
@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) { --bg:#161614; --fg:#ececea; --muted:#9a9a94;
  --card:#20201e; --line:#33332f; --good:#5cc27a; --bad:#f0786d; } }
:root[data-theme="dark"] { --bg:#161614; --fg:#ececea; --muted:#9a9a94; --card:#20201e; --line:#33332f;
  --good:#5cc27a; --bad:#f0786d; }
* { box-sizing:border-box; }
body { background:var(--bg); color:var(--fg); font:15px/1.45 system-ui,sans-serif; margin:0; padding:24px 16px 48px; }
main { max-width:1180px; margin:0 auto; }
h1 { font-size:26px; margin:0 0 4px; } h2 { font-size:19px; margin:34px 0 10px; } h3 { font-size:15px; margin:0; }
a { color:inherit; } .muted { color:var(--muted); } .small { font-size:13px; } p { max-width:860px; }
.good-text { color:var(--good); } .bad-text { color:var(--bad); }
.heads { display:grid; grid-template-columns:repeat(auto-fit,minmax(220px,1fr)); gap:12px; margin:14px 0 18px; }
.heads > div { background:var(--card); border:1px solid var(--line); padding:12px 14px; }
.heads b { display:block; font-size:34px; font-variant-numeric:tabular-nums; line-height:1.1; }
.heads > div > span { color:var(--muted); font-size:13px; }
.tablewrap { overflow-x:auto; background:var(--card); border:1px solid var(--line); border-radius:10px; }
table { border-collapse:collapse; width:100%; font-size:14px; }
th, td { text-align:left; padding:5px 9px; border-bottom:1px solid var(--line); white-space:nowrap; vertical-align:middle; }
th { color:var(--muted); font-weight:500; background:var(--card); }
th[data-sort] { cursor:pointer; user-select:none; } th[aria-sort="ascending"]::after { content:" ▲"; }
th[aria-sort="descending"]::after { content:" ▼"; }
td.num, th.num { text-align:right; font-variant-numeric:tabular-nums; }
tr.cave-row td { background:var(--bg); font-weight:700; font-size:13px; }
tr.low td { opacity:.5; }
.strip { display:flex; gap:8px; overflow-x:auto; padding:4px 2px 10px; }
.mini { flex:0 0 156px; background:var(--card); border:1px solid var(--line); border-radius:10px; padding:6px; font-size:12px; }
.mini img { width:100%; aspect-ratio:1; object-fit:contain; background:#000; border-radius:6px; display:block; cursor:zoom-in; margin-top:3px; }
.mini .nums { display:flex; justify-content:space-between; margin-top:4px; font-variant-numeric:tabular-nums; font-weight:600; }
.mini .nums small { display:block; font-weight:400; color:var(--muted); font-size:10px; }
.mini .nums span:last-child { text-align:right; }
.mini .links { margin-top:3px; display:flex; flex-wrap:wrap; gap:0 8px; }
.mini.low { border-style:dashed; opacity:.6; }
.mini details summary { color:var(--muted); cursor:pointer; margin-top:3px; }
.mini dl { display:grid; grid-template-columns:auto 1fr; gap:1px 8px; margin:4px 0 0; }
.mini dt { color:var(--muted); } .mini dd { margin:0; text-align:right; }
.legend .tick { width:3px; height:12px; background:var(--good-mark); }
.legend .diamond { width:8px; height:8px; transform:rotate(45deg); border:2px solid var(--ink-2); background:var(--surface-1); }
.legend .shape { width:18px; height:10px; background:var(--range); border-radius:5px; }
.scatterbox { max-width:720px; }
dialog { border:none; padding:0; background:transparent; max-width:96vw; max-height:96vh; }
dialog::backdrop { background:rgba(0,0,0,.8); } dialog img { max-width:96vw; max-height:92vh; display:block; border-radius:6px; }
:target { scroll-margin-top:12px; }
.chart.wide { overflow-x:auto; } .chart.wide svg { min-width:680px; }
.mini:target { outline:3px solid var(--sun, #f2a01c); }
"""

ZOOM_JS = """
const dlg = document.getElementById('zoom'), big = dlg.querySelector('img');
document.querySelectorAll('img[data-zoom]').forEach(im => im.addEventListener('click', e => {
  e.preventDefault(); big.src = im.src; dlg.showModal(); }));
dlg.addEventListener('click', () => dlg.close());
"""

SORT_JS = """
(() => { const t = document.getElementById('subs'); if (!t) return; const body = t.tBodies[0];
  t.querySelectorAll('th[data-sort]').forEach(th => { th.tabIndex = 0; th.setAttribute('role', 'button');
    th.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); th.click(); } }); });
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


# --- 1. headline numbers -------------------------------------------------------------------

def _heads(info: dict, rows: list[dict]) -> str:
    jd = [r for r in rows if r["delta"] is not None]
    nets = [r["net"] for r in rows if r["net"] is not None]
    tiles = []
    if jd:
        tot = sum(r["delta"] for r in jd)
        pct = luck.percentile(tot, luck.simulate([r["entry"] for r in jd], info["kind"]))
        tiles.append(f'<div><b class="{_tone(tot)}">{_num(tot)}</b><span>layout luck: what {len(jd)} layouts should save '
                     f'against median layouts of the same sublevels</span></div>')
        tiles.append(f'<div><b>{min(99.5, max(0.5, pct)):.0f}%</b><span>luck percentile: {luck.describe(pct)} '
                     f'over the same sublevels</span></div>')
    if nets:
        tiles.append(f'<div><b class="{_tone(sum(nets))}">{_num(sum(nets))}</b><span>runner: time saved against the median '
                     f'run over {len(nets)} sublevels, beyond what the layouts gave, pokos counted</span></div>')
    return f'<div class="heads">{"".join(tiles)}</div>'


# --- 2. every sublevel as a row --------------------------------------------------------------

def _rows_chart(rows: list[dict]) -> str:
    vals = [v for r in rows if r["dist"] is not None
            for v in (np.percentile(r["dist"], 1), np.percentile(r["dist"], 99), r["delta"])]
    vals += [r["par"] for r in rows if r["par"] is not None]
    ticks = charts.nice_ticks(min(vals + [-10]), max(vals + [10]), 8)
    W, L, R, T, RH, GAP = 960, 76, 96, 40, 22, 18
    n_caves = len(dict.fromkeys(r["cave"] for r in rows))
    H = T + RH * len(rows) + GAP * n_caves + 30
    x = charts._scale(ticks[0], ticks[-1], L, W - R)
    clamp = lambda v: min(ticks[-1], max(ticks[0], v))
    out = [f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="Each sublevel: random layouts, this layout and the runner">',
           f'<text class="ttl" x="{L}" y="14">Every sublevel: seconds against the median (negative = faster)</text>']
    for t in ticks:
        out.append(f'<line class="{"zero" if t == 0 else "grid"}" x1="{x(t):.1f}" x2="{x(t):.1f}" y1="{T - 6}" y2="{H - 26}"/>'
                   f'<text x="{x(t):.1f}" y="{T - 10}" text-anchor="middle">{t:+g}</text>'
                   f'<text x="{x(t):.1f}" y="{H - 12}" text-anchor="middle">{t:+g}</text>')
    out.append(f'<text x="{W - R + 14}" y="14" style="font-weight:600">layout · vs par</text>')
    y, cave = T, None
    for r in rows:
        if r["cave"] != cave:
            cave = r["cave"]
            out.append(f'<text x="4" y="{y + 13}" style="font-weight:700;fill:var(--ink-1)">'
                       f'{html.escape(CAVE_NAMES.get(cave, cave))}</text>')
            y += GAP
        cy = y + RH / 2
        out.append(f'<g id="row-{r["anchor"]}">')
        out.append(f'<text x="{L - 8}" y="{cy + 4:.1f}" text-anchor="end" style="fill:var(--ink-1)">{r["label"]}</text>')
        if r["dist"] is not None:
            q = np.sort(np.asarray(r["dist"]))
            a, b = float(np.percentile(q, 1)), float(np.percentile(q, 99))
            if b - a > 1e-6:
                grid = [a + (b - a) * k / 40 for k in range(41)]
                dens = charts._density(list(q[np.linspace(0, len(q) - 1, min(len(q), 300)).astype(int)]), grid)
                top, half = max(dens) or 1, RH / 2 - 2
                up = [f"{x(clamp(g)):.1f},{cy - half * d / top - .5:.1f}" for g, d in zip(grid, dens)]
                dn = [f"{x(clamp(g)):.1f},{cy + half * d / top + .5:.1f}" for g, d in zip(reversed(grid), reversed(dens))]
                out.append(f'<polygon points="{" ".join(up + dn)}" fill="var(--range)"/>')
            col = "var(--good-mark)" if r["delta"] < 0 else "var(--bad-mark)"
            out.append(f'<line x1="{x(clamp(r["delta"])):.1f}" x2="{x(clamp(r["delta"])):.1f}" y1="{y + 1}" y2="{y + RH - 1}" '
                       f'stroke="{col}" stroke-width="3"/>')
        else:
            why = "fixed floor" if r["fixed"] else "uncertain seed" if not r["trusted"] else "no judge"
            out.append(f'<text x="{L + 6}" y="{cy + 4:.1f}" style="font-style:italic">{why}</text>')
        if r["par"] is not None:
            px, s = x(clamp(r["par"])), 5
            col = "var(--good-mark)" if r["par"] < 0 else "var(--bad-mark)"
            out.append(f'<path d="M{px:.1f},{cy - s:.1f} L{px + s:.1f},{cy:.1f} L{px:.1f},{cy + s:.1f} L{px - s:.1f},{cy:.1f} Z" '
                       f'fill="var(--surface-1)" stroke="{col}" stroke-width="2"/>')
        nums = " · ".join(_signed(v).replace(" s", "") for v in (r["delta"], r["par"]))
        out.append(f'<text x="{W - R + 14}" y="{cy + 4:.1f}" style="font-variant-numeric:tabular-nums">{nums}</text>')
        tip = [f"{r['label']} · seed {r['seed']}"]
        if r["delta"] is not None:
            tip.append(f"layout {r['delta']:+.1f} s vs the median layout ({_beats(r['pct'])})")
        if r["net"] is not None:
            tip.append(f"runner {r['par']:+.1f} s vs par (a median runner on a median layout)")
            tip.append(f"runner {r['net']:+.1f} s beyond the layout")
        if r["pokos_text"]:
            tip.append(r["pokos_text"])
        out.append(f'<a href="#{r["anchor"]}"><rect class="hit" tabindex="-1" x="0" y="{y}" width="{W}" height="{RH}" '
                   f'data-tip="{html.escape(chr(10).join(tip))}"/></a></g>')
        y += RH
    out.append("</svg>")
    legend = ('<div class="legend"><span><i class="shape"></i>1000 random layouts (1st–99th percentile; wider = more '
              'common)</span><span><i class="tick"></i>this layout (green faster, red slower)</span>'
              '<span><i class="diamond"></i>the runner against par: a median runner on a median layout, pokos counted. '
              'The gap from tick to diamond is the runner’s own part</span></div>')
    return f'<div class="chart viz-root wide">{"".join(out)}{legend}</div>'


# --- 3. the story ------------------------------------------------------------------------

def _race(rows) -> str:
    """Running totals through the run: the layouts' luck and the runner's own time."""
    W, H, L, R, T, B = 960, 300, 52, 130, 26, 48
    lk, rn = [0.0], [0.0]
    a = b = 0.0
    for r in rows:
        a += r["delta"] or 0.0
        b += r["net"] or 0.0
        lk.append(a)
        rn.append(b)
    ticks = charts.nice_ticks(min(lk + rn + [0]), max(lk + rn + [0]), 5)
    x = charts._scale(0, len(rows), L, W - R)
    y = charts._scale(ticks[0], ticks[-1], H - B, T)
    out = [f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="Luck and the runner through the run">',
           f'<text class="ttl" x="{L}" y="14">Through the run: running totals, seconds (negative = ahead)</text>']
    for t in ticks:
        out.append(f'<line class="{"zero" if t == 0 else "grid"}" x1="{L}" x2="{W - R}" y1="{y(t):.1f}" y2="{y(t):.1f}"/>'
                   f'<text x="{L - 6}" y="{y(t) + 4:.1f}" text-anchor="end">{t:+g}</text>')
    cave = None
    for k, r in enumerate(rows, start=1):
        if r["cave"] != cave:
            cave = r["cave"]
            out.append(f'<line class="grid" x1="{x(k - .5):.1f}" x2="{x(k - .5):.1f}" y1="{T}" y2="{H - B + 6}"/>'
                       f'<text x="{x(k - .5) + 3:.1f}" y="{H - B + 18}" style="font-weight:600">{cave}</text>')
    for vals_, col, name in ((lk, "var(--series-1)", "layout luck"), (rn, "var(--series-2)", "runner")):
        d = " ".join(f"{'M' if k == 0 else 'L'}{x(k):.1f},{y(v):.1f}" for k, v in enumerate(vals_))
        out.append(f'<path d="{d}" fill="none" stroke="{col}" stroke-width="2.2" stroke-linejoin="round"/>')
    # end labels, pushed apart when the lines finish close together
    ends = sorted([(y(lk[-1]), "var(--series-1)", f"layout luck {lk[-1]:+.0f} s"),
                   (y(rn[-1]), "var(--series-2)", f"runner {rn[-1]:+.0f} s")])
    if ends[1][0] - ends[0][0] < 14:
        mid = (ends[0][0] + ends[1][0]) / 2
        ends = [(mid - 7, *ends[0][1:]), (mid + 7, *ends[1][1:])]
    for yy, col, text in ends:
        out.append(f'<text x="{x(len(rows)) + 6:.1f}" y="{yy + 4:.1f}" style="fill:{col};font-weight:600">{text}</text>')
    for k, r in enumerate(rows, start=1):
        tip = (f"after {r['label']}\nlayout luck so far {lk[k]:+.1f} s ({_signed(r['delta'])} here)\n"
               f"runner so far {rn[k]:+.1f} s ({_signed(r['net'])} here)")
        out.append(f'<a href="#{r["anchor"]}"><rect class="hit" tabindex="-1" x="{x(k - .5):.1f}" y="{T}" '
                   f'width="{x(1) - x(0):.1f}" height="{H - B - T}" data-tip="{html.escape(tip)}"/></a>')
    out.append(f'<text x="{(L + W - R) / 2:.0f}" y="{H - 6}" text-anchor="middle">sublevels in the order played</text>')
    out.append("</svg>")
    return f'<div class="chart viz-root wide">{"".join(out)}</div>'


def _card_lines(r: dict) -> list[str]:
    """A card with its details open, as tooltip lines (the first line is the title)."""
    lines = [f"{r['label']} · {CAVE_NAMES.get(r['cave'], r['cave'])}",
             f"Layout {_signed(r['delta'])}" + (f" · beats {r['pct']:.0f}% of layouts" if r["pct"] is not None else ""),
             f"Runner {_signed(r['net'])} beyond the layout" + (f" · {_signed(r['par'])} vs par" if r["par"] is not None else "")]
    if r["score"] is not None:
        lines.append(f"Judge {r['score']:.1f} s (median {r['median']:.1f})")
    if r["took"] is not None:
        lines.append(f"Took {r['took']:.1f} s (median run {r['median_took']:.1f})")
    if r["pokos"] is not None:
        lines.append(f"Pokos {r['pokos']}" + (f" (median run {r['median_pokos']:g})" if r["median_pokos"] is not None else ""))
    if r["pokos_text"]:
        lines.append(r["pokos_text"])
    if r["skip"]:
        lines.append(f"Judge expects a skip: {', '.join(r['skip'])}")
    lines.append(f"Seed {r['seed']}" + (f" · video {r['time']}" if r["time"] else ""))
    return lines


# --- 4. judge against runner ---------------------------------------------------------------

def _scatter(rows: list[dict]) -> str:
    pts, slopes = [], []
    for r in rows:
        if r["raw"] is None or r["delta"] is None or r["median_luck"] is None:
            continue
        dx = r["delta"] - r["median_luck"]
        if abs(dx) > 1e-6 and r["expected"]:
            slopes.append(r["expected"] / dx)
        tip = "\n".join(_card_lines(r) + [f"Across: layout {dx:+.1f} s vs the median run's layout",
                                          f"Up: runner {r['raw']:+.1f} s vs the median run, pokos counted"])
        pts.append((dx, r["raw"], tip, None, r["img"]))
    if len(pts) < 3:
        return ""
    return ('<div class="scatterbox">' + charts.scatter_chart(
        pts, "The judge against the runner, one dot per sublevel",
        "judge: this layout vs the median run's layout, seconds",
        "runner vs the median run, seconds, pokos counted",
        slope=float(np.median(slopes)) if slopes else None,
        quadrants=(("worse layout, slower", None), ("worse layout,\nstill faster", "good"),
                   ("better layout,\nstill slower", "bad"), ("better layout, faster", None))) + '</div>')


# --- 5. compact table ----------------------------------------------------------------------

def _table(rows: list[dict], kind: str = "pod") -> str:
    trs, cave = [], None
    for n, r in enumerate(rows):
        if r["cave"] != cave:
            cave = r["cave"]
            trs.append(f'<tr class="cave-row"><td colspan="6">{html.escape(CAVE_NAMES.get(cave, cave))}</td></tr>')
        if r["score"] is not None:
            judge = (f'{r["score"]:.1f} s <span class="muted">({r["delta"]:+.1f})</span>')
        else:
            judge = f'<span class="muted">{"fixed floor" if r["fixed"] else "uncertain seed" if not r["trusted"] else ""}</span>'
        pk = ""
        if kind == "at":          # no pokos: the column says what the layout lacks
            m = r["entry"].get("judge2_missing") or {}
            pk = html.escape(", ".join(x for x in (f'{m["treasures"]} treasure missing' if m.get("treasures") else "",
                                                   f'{m["purples"]} purple missing' if m.get("purples") else "",
                                                   "farm visit" if r["entry"].get("revisit") else "") if x))
        elif r["pokos"] is not None:
            pk = f'{r["pokos"]}' + (f' <span class="muted">({r["pokos"] - r["median_pokos"]:+g})</span>'
                                    if r["median_pokos"] is not None else "")
        tip = r["pokos_text"] + (f"\nThe judge expects a skip: {', '.join(r['skip'])}" if r["skip"] else "")
        vid = (f'<a href="{html.escape(r["link"])}" target="_blank" rel="noopener">{html.escape(r["time"])}</a>'
               if r["link"] else html.escape(r["time"]))
        tipattr = f' data-tip="{html.escape(tip)}" tabindex="0"' if tip else ""
        trs.append(
            f'<tr class="{"" if r["trusted"] else "low"}"><td data-v="{n}"><a href="#{r["anchor"]}"><b>{r["label"]}</b></a></td>'
            f'<td class="num" data-v="{_v(r["delta"])}">{judge}</td>'
            f'<td class="num" data-v="{_v(r["pct"])}">{_v(r["pct"], "{:.0f}%")}</td>'
            f'<td class="num {_tone(r["net"])}" data-v="{_v(r["net"])}">{_num(r["net"]) if r["net"] is not None else ""}</td>'
            f'<td class="num" data-v="{_v(r["pokos"], "{}") if kind != "at" else html.escape(pk)}"{tipattr}>{pk}</td>'
            f'<td>{vid}</td></tr>')
    return (f'<div class="tablewrap"><table id="subs"><thead><tr><th data-sort>Sublevel</th>'
            f'<th class="num" data-sort title="The judge\'s estimated clear time (vs the median layout)">Judge</th>'
            f'<th class="num" data-sort title="Share of 1000 random layouts this one beats">Beats</th>'
            f'<th class="num" data-sort title="Seconds vs the median run beyond what the layout gave, pokos counted (2 = 1 s)">Runner</th>'
            + (f'<th class="num" data-sort>Layout lacks</th>' if kind == "at" else
               f'<th class="num" data-sort>Pokos <span class="muted">(vs median)</span></th>') + '<th>Video</th></tr></thead>'
            f'<tbody>{"".join(trs)}</tbody></table></div>')


# --- 6. cards ------------------------------------------------------------------------------

def _card(r: dict, anchor: bool = True) -> str:
    img = f'<img data-zoom loading="lazy" src="{r["img"]}" alt="{r["label"]} layout">' if r["img"] else ""
    dl = ('<dl>'
          + (f'<dt>Judge</dt><dd>{r["score"]:.1f} s (median {r["median"]:.1f})</dd>' if r["score"] is not None else "")
          + (f'<dt>Took</dt><dd>{r["took"]:.1f} s (median run {r["median_took"]:.1f})</dd>' if r["took"] is not None else "")
          + (f'<dt>Pokos</dt><dd>{r["pokos"]}' + (f' (median run {r["median_pokos"]:g})' if r["median_pokos"] is not None else "")
             + '</dd>' if r["pokos"] is not None else "")
          + (f'<dt>Layout</dt><dd>{r["expected"]:+.1f} s vs the median run\'s</dd>' if r["expected"] else "")
          + (f'<dt>Vs par</dt><dd>{r["par"]:+.1f} s</dd>' if r["par"] is not None else "")
          + '</dl>'
          + (f'<p class="muted">{html.escape(r["pokos_text"])}</p>' if r["pokos_text"] else "")
          + (f'<p class="muted">Judge expects a skip: {html.escape(", ".join(r["skip"]))}</p>' if r["skip"] else "")
          + f'<p class="muted">Seed {html.escape(r["seed"])} · <a href="report.html#{r["anchor"]}">how it was read</a></p>')
    note = "fixed floor" if r["fixed"] else "uncertain seed" if not r["trusted"] else ""
    links = []
    if r["pct"] is not None:
        links.append(f'<a href="#row-{r["anchor"]}" title="Where this layout falls among 1000 random layouts">'
                     f'beats {r["pct"]:.0f}%</a>')
    if r["link"]:
        links.append(f'<a href="{html.escape(r["link"])}" target="_blank" rel="noopener">video {html.escape(r["time"])}</a>')
    links.append(f'<a href="{html.escape(r["cg3"])}" target="_blank" rel="noopener">CaveGen3</a>')
    ident = f' id="{r["anchor"]}"' if anchor else ""
    return (f'<div class="mini{"" if r["trusted"] else " low"}"{ident}>'
            f'<b>{r["label"]}</b> <span class="muted">{note}</span>{img}'
            f'<div class="nums"><span class="{_tone(r["delta"])}"><small>layout</small>{_num(r["delta"]) if r["delta"] is not None else "–"}</span>'
            f'<span class="{_tone(r["net"])}"><small>runner</small>{_num(r["net"]) if r["net"] is not None else "–"}</span></div>'
            f'<div class="links">{"".join(links)}</div>'
            f'<details><summary>details</summary>{dl}</details></div>')


def _cards(rows: list[dict]) -> str:
    jd = [r for r in rows if r["delta"] is not None]
    lucky = sorted([r for r in jd if r["delta"] < 0], key=lambda r: r["delta"])[:SPOTLIGHT]
    unlucky = sorted([r for r in jd if r["delta"] > 0], key=lambda r: -r["delta"])[:SPOTLIGHT]
    ran = [r for r in rows if r["net"] is not None]
    best = sorted([r for r in ran if r["net"] < 0], key=lambda r: r["net"])[:SPOTLIGHT]
    worst = sorted([r for r in ran if r["net"] > 0], key=lambda r: -r["net"])[:SPOTLIGHT]
    out = []
    if lucky:
        out.append(f'<h2>Luckiest layouts</h2><div class="strip">{"".join(_card(r, anchor=False) for r in lucky)}</div>')
    if unlucky:
        out.append(f'<h2>Unluckiest layouts</h2><div class="strip">{"".join(_card(r, anchor=False) for r in unlucky)}</div>')
    if best:
        out.append(f'<h2>Highlights <span class="muted small">most time saved beyond the layout</span></h2>'
                   f'<div class="strip">{"".join(_card(r, anchor=False) for r in best)}</div>')
    if worst:
        out.append(f'<h2>Lowlights <span class="muted small">most time lost beyond the layout</span></h2>'
                   f'<div class="strip">{"".join(_card(r, anchor=False) for r in worst)}</div>')
    for cave in dict.fromkeys(r["cave"] for r in rows):
        rs = [r for r in rows if r["cave"] == cave]
        lk = [r["delta"] for r in rs if r["delta"] is not None]
        rn = [r["net"] for r in rs if r["net"] is not None]
        out.append(f'<h2>{html.escape(CAVE_NAMES.get(cave, cave))} <span class="muted small">'
                   f'{f"layouts {_num(sum(lk))}" if lk else ""}{f" · runner {_num(sum(rn))}" if rn else ""}</span></h2>'
                   f'<div class="strip">{"".join(_card(r) for r in rs)}</div>')
    return "".join(out)


def write(out_dir: Path, actual: dict | None = None) -> Path | None:
    out_dir = Path(out_dir)
    info, rows = _rows(out_dir, actual or {})
    if not rows:
        return None
    run = info["run"]
    title = f"{info['runner']} {_fmt_time(info['time'])}".strip()
    n_low = sum(1 for r in rows if not r["trusted"])
    body = f'''<h1>{html.escape(title)} · layouts</h1>
<p class="muted">{"All Treasures" if info["kind"] == "at" else "Pay Off Debt"}{f", {html.escape(run.get('date', ''))}" if run.get('date') else ""}
{f' · <a href="{html.escape(run["weblink"])}" target="_blank" rel="noopener">speedrun.com</a>' if run.get("weblink") else ""}
· <a href="report.html">how the seeds were read</a></p>
{_heads(info, rows)}
<p class="small">Every layout was rebuilt from the seed read off the video and timed by the layout judge (CaveGen's
Pay Off Debt judge, refit on these runs' real times). <b>Layout luck</b> is the judge's time against the median of 1000
random layouts of the same sublevel. <b>Runner</b> is what the runner did against the median run on this site, counting
2 pokos as 1 second, with the judge's difference between this layout and the median run's taken out, so a bad layout
is not counted against the runner. <b>Par</b> is a median runner on a median layout: the diamonds below show the
runner against par, luck included. Negative is faster, as on splits.{f" {n_low} sublevel{'s' if n_low != 1 else ''} whose seed is uncertain {'are' if n_low != 1 else 'is'} shown faded and never counted." if n_low else ""}</p>

<h2>Every sublevel</h2>
{_rows_chart(rows)}

<h2>Through the run</h2>
{_race(rows)}
<p class="muted small">Blue: the time the layouts handed the runner so far, against median layouts. Orange: the time
the runner gained on the median run so far beyond what the layouts gave. Hover for the numbers; click to jump to the card.</p>

<h2>The judge against the runner</h2>
{_scatter(rows)}
<p class="muted small">Across: how much faster or slower the judge rates this layout than the median run's layout. Up:
how much faster or slower the runner actually was than the median run. On the orange line the layout explains the whole
difference; dots below it beat what the layout predicts, dots above it lost time beyond the layout.</p>

<h2>Table</h2>
{_table(rows, info["kind"])}
<p class="muted small">Judge: estimated clear time, with the difference from the median random layout. Beats: share of
random layouts this one beats. Click a heading to sort, a sublevel to see its card.</p>

{_cards(rows)}'''
    page = f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(title)} · layouts · {theme.SITE}</title>
<style>{CSS}
{charts.CSS}</style></head><body><main>
{body}
</main>
<dialog id="zoom"><img alt=""></dialog>
<script>{ZOOM_JS}</script><script>{SORT_JS}</script><script>{charts.TOOLTIP_JS}</script>
</body></html>'''
    if info["kind"] == "at":
        for pod_text, at_text in AT_TEXT:
            page = page.replace(pod_text, at_text)
    page = theme.apply(page, prefix="../", run=out_dir.name, active="judge", category=theme.category_of(info["kind"]))
    dest = out_dir / "judge.html"
    dest.write_text(page, encoding="utf-8")
    return dest
