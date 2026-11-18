"""Small inline-SVG charts for the report site (no JavaScript libraries).

Colors come from CSS custom properties defined by the page (see CSS below), so
light and dark themes swap in one place. Every mark that carries a value has a
`data-tip` attribute; TOOLTIP_JS shows it on hover and keyboard focus.
"""

from __future__ import annotations

import json

import html
import math

SERIES = ["--series-1", "--series-2", "--series-3", "--series-4", "--series-5",
          "--series-6", "--series-7", "--series-8"]

CSS = """
.sc-keys[hidden] { display:none !important; }
.scatter-controls { display:flex; flex-wrap:wrap; gap:6px 16px; align-items:center; font-size:13px; margin:0 0 6px; }
.scatter-controls select { font:inherit; color:inherit; background:var(--surface-1); border:1px solid var(--grid); border-radius:6px; padding:2px 6px; max-width:60vw; }
.cumul .brush-area { cursor:crosshair; touch-action:none; }
.cumul .sortval { font-size:10px; }
.cumul .brush-read { font-size:12px; font-weight:600; }
.viz-root { --surface-1:#fcfcfb; --ink-1:#0b0b0b; --ink-2:#52514e; --ink-3:#8a8984; --grid:#e6e5e0;
  --range:#d4d3cd; --good-mark:#0ca30c; --bad-mark:#d03b3b; --series-1:#2a78d6; --series-2:#eb6834; --series-3:#1baf7a; --series-4:#eda100;
  --series-5:#e87ba4; --series-6:#008300; --series-7:#6250d6; --series-8:#e34948; }
@media (prefers-color-scheme: dark) { :root:where(:not([data-theme="light"])) .viz-root {
  --surface-1:#1a1a19; --ink-1:#f0efec; --ink-2:#c3c2b7; --ink-3:#8f8e88; --grid:#2f2f2c; --range:#45443f;
  --series-1:#3987e5; --series-2:#d95926; --series-3:#199e70; --series-4:#c98500; --series-5:#d55181;
  --series-6:#0ca30c; --series-7:#9085e9; --series-8:#e66767; } }
:root[data-theme="dark"] .viz-root { --surface-1:#1a1a19; --ink-1:#f0efec; --ink-2:#c3c2b7; --ink-3:#8f8e88;
  --grid:#2f2f2c; --range:#45443f; --series-1:#3987e5; --series-2:#d95926; --series-3:#199e70;
  --series-4:#c98500; --series-5:#d55181; --series-6:#0ca30c; --series-7:#9085e9; --series-8:#e66767; }
.chart { background:var(--surface-1); border:1px solid var(--grid); border-radius:10px; padding:12px 12px 6px; }
.chart svg { display:block; width:100%; height:auto; overflow:visible; }
.chart text { fill:var(--ink-2); font:11px system-ui,sans-serif; }
.chart .ttl { fill:var(--ink-1); font-weight:600; font-size:12px; }
.chart .grid { stroke:var(--grid); stroke-width:1; }
.chart .zero { stroke:var(--ink-3); stroke-width:1; }
.chart .range { stroke:var(--range); stroke-width:6; stroke-linecap:round; }
.chart .hit { fill:transparent; cursor:default; outline:none; }
.chart svg text, .chart .dot { pointer-events:none; }
.chart .hit:hover + .dot, .chart .hit:focus + .dot { stroke:var(--ink-1); stroke-width:2; }
.chart .runline { opacity:.35; } .chart .runline:hover, .chart .runline:focus-within { opacity:1; }
.chart .runline:hover path { stroke-width:2.5; }
.legend { display:flex; flex-wrap:wrap; gap:4px 14px; margin:8px 2px 2px; font-size:12px; color:var(--ink-2); }
.legend i { display:inline-block; width:16px; height:2px; vertical-align:middle; margin-right:6px; border-radius:1px; }
.legend i.dotkey { width:8px; height:8px; border-radius:50%; }
#viz-tip { position:fixed; pointer-events:none; z-index:10; background:var(--surface-1); color:var(--ink-2);
  border:1px solid var(--grid); border-radius:8px; padding:6px 9px; font:12px/1.4 system-ui,sans-serif;
  box-shadow:0 4px 14px rgba(0,0,0,.25); display:none; box-sizing:border-box; max-width:min(260px, calc(100vw - 16px)); }
#viz-tip b { color:var(--ink-1); display:block; font-size:13px; }
#viz-tip img { display:block; width:240px; height:min(200px, 45vh); object-fit:contain; max-width:100%; margin-top:6px;
  border-radius:4px; background:#000; }
"""

TOOLTIP_JS = """
(() => {
  const tip = document.createElement('div'); tip.id = 'viz-tip'; tip.className = 'viz-root';
  document.body.appendChild(tip);
  let at = null;
  const place = () => {
    if (!at) return;
    const [x, y] = at, w = tip.offsetWidth, h = tip.offsetHeight, gap = 14;
    // right of the pointer if it fits, else left; vertically centred on it, kept inside the window
    let left = x + gap + w <= innerWidth - 8 ? x + gap : x - gap - w;
    left = Math.max(8, Math.min(left, innerWidth - w - 8));
    const top = Math.max(8, Math.min(y - h / 2, innerHeight - h - 8));
    tip.style.left = left + 'px'; tip.style.top = top + 'px';
  };
  let cur = null;
  const hide = () => { tip.style.display = 'none'; cur = null; };
  const show = (el, x, y) => {
    if (cur === el) { at = [x, y]; place(); return; }  // same mark: just follow the pointer
    cur = el;
    tip.replaceChildren();
    const [head, ...rest] = el.dataset.tip.split('\\n');
    const b = document.createElement('b'); b.textContent = head; tip.appendChild(b);
    rest.forEach(line => { const d = document.createElement('div'); d.textContent = line; tip.appendChild(d); });
    if (el.dataset.img) {
      const im = document.createElement('img'); im.alt = ''; im.addEventListener('load', place);
      im.src = el.dataset.img; tip.appendChild(im);
    }
    tip.style.display = 'block';
    at = [x, y]; place();
  };
  document.querySelectorAll('[data-tip]').forEach(el => {
    el.addEventListener('pointermove', e => show(el, e.clientX, e.clientY));
    el.addEventListener('pointerleave', hide);
    el.addEventListener('focus', () => { const r = el.getBoundingClientRect(); show(el, r.right, r.top); });
    el.addEventListener('blur', hide);
  });
})();
"""


def _esc(s: str) -> str:
    return html.escape(str(s), quote=True)


def nice_ticks(lo: float, hi: float, n: int = 5) -> list[float]:
    if hi <= lo:
        hi = lo + 1
    raw = (hi - lo) / n
    mag = 10 ** math.floor(math.log10(raw))
    step = min((m * mag for m in (1, 2, 2.5, 5, 10) if m * mag >= raw), default=raw)
    start = math.floor(lo / step) * step
    ticks, t = [], start
    while True:                       # the last tick must reach past the data
        ticks.append(round(t, 10))
        if t >= hi - 1e-9:
            return ticks
        t += step


def _scale(d0, d1, r0, r1):
    span = (d1 - d0) or 1.0
    return lambda v: r0 + (v - d0) * (r1 - r0) / span


def timesave_chart(points: list[dict], title: str) -> str:
    """One column per sublevel, in seconds against the median (negative = faster, like splits).

    Grey bar: 5th to 95th percentile of random layouts (judge). Circle: the judge's estimate
    for this run's layout. Diamond: what the runner actually did, net of pokos, against the
    median run. Marks are green when faster than the median and red when slower.

    points: dicts with label, anchor, fixed (bool), judge (or None), lo/hi (5th/95th
    percentile deltas), beats (% of layouts beaten), actual (or None), extra (tooltip text)."""
    W, H, L, R, T, B = 960, 320, 48, 10, 26, 44
    vals = [v for p in points for v in (p.get("judge"), p.get("lo"), p.get("hi"), p.get("actual")) if v is not None]
    lo, hi = min(vals + [0]), max(vals + [0])
    pad = 0.08 * (hi - lo or 1)
    ticks = nice_ticks(lo - pad, hi + pad)
    y = _scale(ticks[0], ticks[-1], H - B, T)
    n = max(1, len(points))
    col = (W - L - R) / n
    out = [f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="{_esc(title)}">',
           f'<text class="ttl" x="{L}" y="14">{_esc(title)}</text>']
    for t in ticks:
        out.append(f'<line class="{"zero" if t == 0 else "grid"}" x1="{L}" x2="{W - R}" y1="{y(t):.1f}" y2="{y(t):.1f}"/>'
                   f'<text x="{L - 6}" y="{y(t) + 4:.1f}" text-anchor="end">{t:+g}</text>')
    out.append(f'<text x="12" y="{(T + H - B) / 2:.0f}" transform="rotate(-90 12 {(T + H - B) / 2:.0f})" '
               f'text-anchor="middle">seconds vs median (negative = faster)</text>')

    def color(v):
        return "var(--good-mark)" if v < 0 else "var(--bad-mark)" if v > 0 else "var(--ink-3)"

    prev_cave = None
    for i, p in enumerate(points):
        cx = L + col * (i + 0.5)
        cave = p["label"].split(" ")[0]
        if cave != prev_cave:
            out.append(f'<text x="{cx:.1f}" y="{H - B + 30}" text-anchor="start" style="font-weight:600">{_esc(cave)}</text>')
            if prev_cave is not None:
                out.append(f'<line class="grid" x1="{cx - col / 2:.1f}" x2="{cx - col / 2:.1f}" y1="{T}" y2="{H - B + 34}"/>')
            prev_cave = cave
        out.append(f'<text x="{cx:.1f}" y="{H - B + 14}" text-anchor="middle">{_esc(p["label"].split(" ")[-1])}</text>')
        lines = [p["label"]]
        if p.get("fixed") or p.get("judge") is None:
            out.append(f'<circle cx="{cx - 3:.1f}" cy="{y(0):.1f}" r="2.5" fill="var(--ink-3)"/>')
            lines.append("judge: fixed floor (every seed scores the same)" if p.get("fixed") else "judge: none")
        else:
            out.append(f'<line class="range" x1="{cx - 3:.1f}" x2="{cx - 3:.1f}" y1="{y(p["hi"]):.1f}" y2="{y(p["lo"]):.1f}"/>')
            out.append(f'<circle cx="{cx - 3:.1f}" cy="{y(p["judge"]):.1f}" r="4.5" fill="{color(p["judge"])}" '
                       f'stroke="var(--surface-1)" stroke-width="1.5"/>')
            lines.append(f'judge: {p["judge"]:+.1f} s (faster than {p["beats"]:.0f}% of layouts)')
            lines.append(f'random layouts, 5th–95th pct: {p["lo"]:+.1f} to {p["hi"]:+.1f} s')
        if p.get("actual") is not None:
            ax, ay = cx + 4, y(p["actual"])
            out.append(f'<path d="M{ax:.1f},{ay - 5:.1f} L{ax + 5:.1f},{ay:.1f} L{ax:.1f},{ay + 5:.1f} L{ax - 5:.1f},{ay:.1f} Z" '
                       f'fill="var(--surface-1)" stroke="{color(p["actual"])}" stroke-width="2"/>')
            lines.append(f'run: {p["actual"]:+.1f} s net vs the median run')
        if p.get("extra"):
            lines.append(p["extra"])
        out.append(f'<a href="#{_esc(p["anchor"])}"><rect class="hit" tabindex="0" x="{cx - col / 2:.1f}" y="{T}" '
                   f'width="{col:.1f}" height="{H - B - T}" data-tip="{_esc(chr(10).join(lines))}"/></a>')
    out.append("</svg>")
    legend = ('<div class="legend"><span><i class="dotkey" style="background:var(--good-mark)"></i>'
              '<i class="dotkey" style="background:var(--bad-mark);margin-left:-4px"></i>judge estimate for this layout</span>'
              '<span><i class="dotkey" style="background:transparent;border:2px solid var(--ink-2);border-radius:2px;'
              'transform:rotate(45deg);width:7px;height:7px"></i>runner\'s actual result, net of pokos</span>'
              '<span><i style="background:var(--range);height:6px"></i>5th–95th percentile of random layouts</span>'
              '<span>green = faster than the median, red = slower</span></div>')
    return f'<div class="chart viz-root">{"".join(out)}{legend}</div>'


def line_chart(series: list[dict], title: str, x_label: str, y_label: str, y_fmt=lambda v: f"{v:g}") -> str:
    """series: dicts with name, slot (0-based color slot), points [(x, y, tip)], breaks allowed as None.

    More series than there are distinguishable colors are drawn in one neutral color without end
    labels; each point's tooltip names its series and hovering a line brings it forward."""
    many = len(series) > len(SERIES)
    W, H, L, R, T, B = 960, 360, 56, 20 if many else 120, 26, 40
    xs = [p[0] for s in series for p in s["points"] if p]
    ys = [p[1] for s in series for p in s["points"] if p]
    xt = nice_ticks(0, max(xs or [1]))
    yt = nice_ticks(0, max(ys or [1]))
    x = _scale(xt[0], xt[-1], L, W - R)
    y = _scale(yt[0], yt[-1], H - B, T)
    out = [f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="{_esc(title)}">',
           f'<text class="ttl" x="{L}" y="14">{_esc(title)}</text>']
    for t in yt:
        out.append(f'<line class="grid" x1="{L}" x2="{W - R}" y1="{y(t):.1f}" y2="{y(t):.1f}"/>'
                   f'<text x="{L - 6}" y="{y(t) + 4:.1f}" text-anchor="end">{_esc(y_fmt(t))}</text>')
    for t in xt:
        out.append(f'<text x="{x(t):.1f}" y="{H - B + 16}" text-anchor="middle">{t:g}</text>')
    out.append(f'<text x="{(L + W - R) / 2:.0f}" y="{H - 6}" text-anchor="middle">{_esc(x_label)}</text>')
    out.append(f'<text x="14" y="{(T + H - B) / 2:.0f}" transform="rotate(-90 14 {(T + H - B) / 2:.0f})" '
               f'text-anchor="middle">{_esc(y_label)}</text>')
    label_ys = []
    for s in series:
        color = "var(--series-1)" if many else f"var({SERIES[s['slot'] % len(SERIES)]})"
        out.append('<g class="runline">' if many else "<g>")
        segs, cur = [], []
        for p in s["points"]:
            if p is None:
                if cur:
                    segs.append(cur)
                cur = []
            else:
                cur.append(p)
        if cur:
            segs.append(cur)
        for seg in segs:
            d = " ".join(f"{'M' if i == 0 else 'L'}{x(px):.1f},{y(py):.1f}" for i, (px, py, _) in enumerate(seg))
            out.append(f'<path d="{d}" fill="none" stroke="{color}" stroke-width="{1.5 if many else 2}" '
                       f'stroke-linejoin="round"/>')
        for px, py, tip in (p for p in s["points"] if p):
            out.append(f'<circle class="hit" tabindex="0" cx="{x(px):.1f}" cy="{y(py):.1f}" r="12" data-tip="{_esc(tip)}"/>'
                       f'<circle class="dot" cx="{x(px):.1f}" cy="{y(py):.1f}" r="{2 if many else 3}" fill="{color}" '
                       f'stroke="var(--surface-1)" stroke-width="1"/>')
        out.append("</g>")
        last = [p for p in s["points"] if p]
        if last and not many:
            ly = y(last[-1][1])
            while any(abs(ly - o) < 13 for o in label_ys):
                ly += 13
            label_ys.append(ly)
            out.append(f'<text x="{x(last[-1][0]) + 14:.1f}" y="{ly + 4:.1f}" style="fill:var(--ink-1)">{_esc(s["name"])}</text>')
    out.append("</svg>")
    if many:
        legend = (f'<span><i style="background:var(--series-1)"></i>{len(series)} runs, one line each; '
                  f'hover a line or point to see which</span>')
    else:
        legend = "".join(f'<span><i style="background:var({SERIES[s["slot"] % len(SERIES)]})"></i>{_esc(s["name"])}</span>'
                         for s in series)
    return f'<div class="chart viz-root">{"".join(out)}<div class="legend">{legend}</div></div>'


def scatter_chart(points: list[tuple], title: str, x_label: str, y_label: str,
                  slope: float | None = None, quadrants: tuple | None = None) -> str:
    """Single-series scatter with a y = x reference and an optional fitted line through 0.

    points: (x, y, tip[, href[, image url[, info]]]); the image is shown in the tooltip on hover.
            info: {"run": label, "runner": name, "flag": bool}; with it the chart gets a menu to
            highlight one runner or run and a switch to colour the points by runner, and flagged
            (unusual) points get a ring.
    quadrants: labels for the top-right, bottom-right, top-left and bottom-left corners."""
    W, H, L, R, T, B = 620, 440, 56, 16, 26, 44
    lim = max([abs(c) for p in points for c in p[:2]] + [1]) * 1.05
    t = nice_ticks(-lim, lim, 6)
    s = _scale(t[0], t[-1], L, W - R)
    v = _scale(t[0], t[-1], H - B, T)
    out = [f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="{_esc(title)}">',
           f'<text class="ttl" x="{L}" y="14">{_esc(title)}</text>']
    for k in t:
        cls = "zero" if k == 0 else "grid"
        out.append(f'<line class="{cls}" x1="{L}" x2="{W - R}" y1="{v(k):.1f}" y2="{v(k):.1f}"/>'
                   f'<line class="{cls}" x1="{s(k):.1f}" x2="{s(k):.1f}" y1="{T}" y2="{H - B}"/>'
                   f'<text x="{L - 6}" y="{v(k) + 4:.1f}" text-anchor="end">{k:+g}</text>'
                   f'<text x="{s(k):.1f}" y="{H - B + 16}" text-anchor="middle">{k:+g}</text>')
    out.append(f'<line x1="{s(t[0]):.1f}" y1="{v(t[0]):.1f}" x2="{s(t[-1]):.1f}" y2="{v(t[-1]):.1f}" '
               f'stroke="var(--ink-3)" stroke-width="1.5" stroke-dasharray="5 4"/>')
    # line labels sit midway along their lines, clear of the corner labels
    m = 0.55 * t[-1]
    out.append(f'<text x="{s(m) - 8:.1f}" y="{v(m) - 6:.1f}" text-anchor="end">y = x</text>')
    if slope is not None:
        x0, x1 = t[0], t[-1]
        y0, y1 = max(t[0], min(t[-1], slope * x0)), max(t[0], min(t[-1], slope * x1))
        x0, x1 = y0 / slope, y1 / slope
        out.append(f'<line x1="{s(x0):.1f}" y1="{v(y0):.1f}" x2="{s(x1):.1f}" y2="{v(y1):.1f}" '
                   f'stroke="var(--series-2)" stroke-width="2"/>')
        out.append(f'<text x="{s(m) + 8:.1f}" y="{v(slope * m) + 16:.1f}" text-anchor="start" style="fill:var(--ink-1)">'
                   f'fit: slope {slope:.2f}</text>')
    if quadrants:
        # top-right, bottom-right, top-left, bottom-left
        for (qx, qy, anchor), q in zip(((W - R - 6, T + 14, "end"), (W - R - 6, H - B - 8, "end"),
                                        (L + 6, T + 14, "start"), (L + 6, H - B - 8, "start")), quadrants):
            label, tone = q if isinstance(q, tuple) else (q, None)
            fill = {"good": "var(--good-mark)", "bad": "var(--bad-mark)"}.get(tone, "var(--ink-3)")
            weight = "600" if tone else "400"
            lines = label.split("\n")
            for k, line in enumerate(lines):
                out.append(f'<text x="{qx}" y="{qy + 15 * k - (15 * (len(lines) - 1) if qy > H / 2 else 0)}" '
                           f'text-anchor="{anchor}" style="fill:{fill};font-weight:{weight}">{_esc(line)}</text>')
    infos = [pt[5] if len(pt) > 5 else None for pt in points]
    runner_count: dict = {}
    for info in infos:
        if info:
            runner_count[info["runner"]] = runner_count.get(info["runner"], 0) + 1
    # the runners with the most plays get the series colours, the rest share grey
    colour = {name: SERIES[k] for k, name in enumerate(sorted(runner_count, key=lambda n: -runner_count[n])[:len(SERIES)])}
    for pt, info in zip(points, infos):
        px, py, tip = pt[:3]
        href = pt[3] if len(pt) > 3 else None
        img = pt[4] if len(pt) > 4 else None
        img_attr = f' data-img="{_esc(img)}"' if img else ""
        data = (f' data-run="{_esc(info["run"])}" data-runner="{_esc(info["runner"])}" '
                f'data-col="var({colour.get(info["runner"], "--ink-3")})"') if info else ""
        ring = (f'<circle cx="{s(px):.1f}" cy="{v(py):.1f}" r="7.5" fill="none" stroke="var(--bad-mark)" stroke-width="1.5" '
                f'class="ring"{data}/>') if info and info.get("flag") else ""
        mark = (f'<circle class="hit" tabindex="-1" cx="{s(px):.1f}" cy="{v(py):.1f}" r="12" data-tip="{_esc(tip)}"{img_attr}/>'
                f'{ring}<circle class="dot" cx="{s(px):.1f}" cy="{v(py):.1f}" r="4" fill="var(--series-1)" '
                f'fill-opacity=".75" stroke="var(--surface-1)" stroke-width="1.5"{data}/>')
        out.append(f'<a href="{_esc(href)}" target="_blank" rel="noopener" tabindex="-1">{mark}</a>' if href else mark)
    out.append(f'<text x="{(L + W - R) / 2:.0f}" y="{H - 8}" text-anchor="middle">{_esc(x_label)}</text>')
    out.append(f'<text x="14" y="{(T + H - B) / 2:.0f}" transform="rotate(-90 14 {(T + H - B) / 2:.0f})" '
               f'text-anchor="middle">{_esc(y_label)}</text>')
    out.append("</svg>")
    legend = ('<div class="legend"><span><i class="dotkey" style="background:var(--series-1)"></i>one sublevel in one run</span>'
              '<span><i style="background:var(--series-2)"></i>fitted slope</span>'
              '<span><i style="background:var(--ink-3)"></i>y = x (perfect calibration)</span>'
              + ('<span><i class="dotkey" style="background:transparent;box-shadow:inset 0 0 0 2px var(--bad-mark)"></i>'
                 'unusual play (far off under every judge)</span>' if any(i and i.get("flag") for i in infos) else "")
              + '</div>')
    controls = ""
    if runner_count:
        runs = sorted({i["run"] for i in infos if i}, key=lambda r: (r.split(" ")[0].lower(), r))
        opts = ('<option value="">All runs</option><optgroup label="Runner">'
                + "".join(f'<option value="runner:{_esc(n)}">{_esc(n)} ({runner_count[n]} plays)</option>'
                          for n in sorted(runner_count, key=str.lower))
                + '</optgroup><optgroup label="Run">'
                + "".join(f'<option value="run:{_esc(r)}">{_esc(r)}</option>' for r in runs) + '</optgroup>')
        keys = "".join(f'<span><i class="dotkey" style="background:var({c})"></i>{_esc(n)}</span>' for n, c in colour.items())
        controls = (f'<div class="scatter-controls"><label>Highlight <select class="sc-pick">{opts}</select></label>'
                    f'<label><input type="checkbox" class="sc-colour"> Colour by runner</label></div>'
                    f'<div class="legend sc-keys" hidden>{keys}<span><i class="dotkey" style="background:var(--ink-3)"></i>others</span></div>')
    return f'<div class="chart viz-root scatter">{controls}{"".join(out)}{legend}</div>'


def cumulative_chart(points: list[tuple], band: list[tuple], beta: float, title: str, subtitle: str) -> str:
    """Cumulative regression chart.

    points: (sum x^2, sum x*y, tip, href[, label]) after each observation in sort order; label is
            the play's value of the sort (shown under the x axis).
    band:   (sum x^2, low, high) pointwise 95% band around the straight line y = beta * x.
    A straight walk along the line means the slope is the same throughout this ordering; a
    bend that leaves the band means the slope differs in part of it. Dragging across the chart
    shows the slope of the selected stretch (the change in Σxy over the change in Σx²)."""
    W, H, L, R, T, B = 460, 320, 52, 12, 40, 56
    xs = [0.0] + [p[0] for p in points]
    ys = [0.0] + [p[1] for p in points] + [b[1] for b in band] + [b[2] for b in band]
    xt = nice_ticks(0, max(xs) or 1, 4)
    yt = nice_ticks(min(ys), max(ys) or 1, 4)
    x = _scale(xt[0], xt[-1], L, W - R)
    y = _scale(yt[0], yt[-1], H - B, T)
    out = [f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="{_esc(title)}">',
           f'<text class="ttl" x="{L}" y="14">{_esc(title)}</text>',
           f'<text x="{L}" y="30">{_esc(subtitle)}</text>']
    for t in yt:
        out.append(f'<line class="{"zero" if t == 0 else "grid"}" x1="{L}" x2="{W - R}" y1="{y(t):.1f}" y2="{y(t):.1f}"/>'
                   f'<text x="{L - 6}" y="{y(t) + 4:.1f}" text-anchor="end">{t:g}</text>')
    for t in xt:
        out.append(f'<text x="{x(t):.1f}" y="{H - B + 14}" text-anchor="middle">{t:g}</text>')
    # the sort's own values along the bottom, at a few evenly spaced plays
    labels = [p[4] if len(p) > 4 else None for p in points]
    if any(labels):
        n = len(points)
        last = -99.0
        for k in sorted({round(i * (n - 1) / 5) for i in range(6)}):
            if labels[k] is None:
                continue
            px = x(points[k][0])
            if px - last < 52:
                continue
            last = px
            out.append(f'<line class="grid" x1="{px:.1f}" x2="{px:.1f}" y1="{H - B + 18}" y2="{H - B + 22}"/>'
                       f'<text class="sortval" x="{px:.1f}" y="{H - B + 32}" text-anchor="middle">{_esc(labels[k])}</text>')
    out.append(f'<text x="{(L + W - R) / 2:.0f}" y="{H - 4}" text-anchor="middle">cumulative prediction² (s²) · '
               f'drag to measure a stretch</text>')
    out.append(f'<text x="12" y="{(T + H - B) / 2:.0f}" transform="rotate(-90 12 {(T + H - B) / 2:.0f})" '
               f'text-anchor="middle">cumulative prediction × actual (s²)</text>')
    if band:
        poly = [f"{x(0):.1f},{y(0):.1f}"] + [f"{x(b[0]):.1f},{y(b[2]):.1f}" for b in band] + \
               [f"{x(b[0]):.1f},{y(b[1]):.1f}" for b in reversed(band)]
        out.append(f'<polygon points="{" ".join(poly)}" fill="var(--range)" fill-opacity=".55"/>')
    out.append(f'<line x1="{x(0):.1f}" y1="{y(0):.1f}" x2="{x(xs[-1]):.1f}" y2="{y(beta * xs[-1]):.1f}" '
               f'stroke="var(--ink-3)" stroke-width="1.5" stroke-dasharray="5 4"/>')
    # the drag target sits under the path and the dots, so hovering a dot still shows its tooltip
    out.append(f'<rect class="brush-area" x="{L}" y="{T}" width="{W - R - L}" height="{H - B - T}" fill="transparent"/>'
               f'<rect class="brush" x="0" y="{T}" width="0" height="{H - B - T}" fill="var(--series-4)" fill-opacity=".18" '
               f'pointer-events="none"/>')
    d = f"M{x(0):.1f},{y(0):.1f} " + " ".join(f"L{x(p[0]):.1f},{y(p[1]):.1f}" for p in points)
    out.append(f'<path d="{d}" fill="none" stroke="var(--series-1)" stroke-width="2" stroke-linejoin="round" pointer-events="none"/>')
    for p in points:
        px, py, tip, href = p[:4]
        hit = f'<circle class="hit" tabindex="-1" cx="{x(px):.1f}" cy="{y(py):.1f}" r="7" data-tip="{_esc(tip)}"/>'
        out.append(f'<a href="{_esc(href)}" target="_blank" rel="noopener" tabindex="-1">{hit}</a>' if href else hit)
    out.append(f'<text class="brush-read" x="{W - R}" y="{T + 14}" text-anchor="end"></text>')
    out.append("</svg>")
    data = [[round(x(0), 1), 0, 0, ""]] + [[round(x(p[0]), 1), round(p[0], 2), round(p[1], 2), labels[i] or ""]
                                           for i, p in enumerate(points)]
    return (f'<div class="chart viz-root cumul" data-pts="{_esc(json.dumps(data))}" data-beta="{beta:.4f}">'
            f'{"".join(out)}</div>')


# Scatter options: highlight one runner or run, colour the points by runner.
SCATTER_JS = """
document.querySelectorAll('.scatter').forEach(box => {
  const pick = box.querySelector('.sc-pick'), col = box.querySelector('.sc-colour'), keys = box.querySelector('.sc-keys');
  if (!pick) return;
  const apply = () => {
    const [kind, val] = pick.value ? [pick.value.split(':')[0], pick.value.slice(pick.value.indexOf(':') + 1)] : [null, null];
    box.querySelectorAll('[data-runner]').forEach(d => {
      const on = !kind || d.dataset[kind] === val;
      if (d.classList.contains('dot')) {
        d.setAttribute('fill', col.checked ? d.dataset.col : 'var(--series-1)');
        d.setAttribute('fill-opacity', on ? '.85' : '.08');
        d.setAttribute('r', kind && on ? 5 : 4);
      } else d.setAttribute('stroke-opacity', on ? 1 : .1);
      if (on && kind) d.parentNode.appendChild(d);      // bring the highlighted points to the front
    });
    keys.hidden = !col.checked;
  };
  pick.addEventListener('change', apply); col.addEventListener('change', apply);
});
"""


# Dragging across a cumulative chart: the slope of the selected stretch of plays.
BRUSH_JS = """
document.querySelectorAll('.cumul').forEach(box => {
  const svg = box.querySelector('svg'), area = svg.querySelector('.brush-area'), brush = svg.querySelector('.brush');
  const read = svg.querySelector('.brush-read'), pts = JSON.parse(box.dataset.pts);
  const toX = e => { const p = svg.createSVGPoint(); p.x = e.clientX; p.y = e.clientY;
                     return p.matrixTransform(svg.getScreenCTM().inverse()).x; };
  const near = px => { let k = 0; pts.forEach((q, i) => { if (Math.abs(q[0] - px) < Math.abs(pts[k][0] - px)) k = i; }); return k; };
  let x0 = null;
  const show = (a, b) => {
    let i = near(Math.min(a, b)), j = near(Math.max(a, b));
    brush.setAttribute('x', pts[i][0]); brush.setAttribute('width', Math.max(0, pts[j][0] - pts[i][0]));
    if (j <= i) { read.textContent = ''; return; }
    const sxx = pts[j][1] - pts[i][1], sxy = pts[j][2] - pts[i][2];
    const from = pts[i + 1][3], to = pts[j][3];
    read.textContent = (from || to ? `${from} to ${to}: ` : '') + `${j - i} plays, slope ` +
      (sxx > 0 ? (sxy / sxx).toFixed(2) : '–') + ` (all ${(+box.dataset.beta).toFixed(2)})`;
  };
  area.addEventListener('pointerdown', e => { x0 = toX(e); area.setPointerCapture(e.pointerId); show(x0, x0); });
  area.addEventListener('pointermove', e => { if (x0 !== null) show(x0, toX(e)); });
  area.addEventListener('pointerup', e => { if (x0 !== null) { const x1 = toX(e);
    if (Math.abs(x1 - x0) < 3) { brush.setAttribute('width', 0); read.textContent = ''; } x0 = null; } });
});
"""


def dot_chart(categories: list[str], series: list[dict], title: str, y_label: str) -> str:
    """Values per category for several series, as dots side by side within each category.

    series: dicts with name, slot, values {category: (value, tip, href)}. With more series than
    distinguishable colors, each dot is colored by its sign instead (green above zero, red below)
    and its tooltip names the series."""
    many = len(series) > len(SERIES)
    W, H, L, R, T, B = 960, 300, 48, 10, 26, 44
    vals = [v[0] for s in series for v in s["values"].values() if v and v[0] is not None]
    yt = nice_ticks(min(vals + [0]), max(vals + [1]))
    y = _scale(yt[0], yt[-1], H - B, T)
    n = max(1, len(categories))
    col = (W - L - R) / n
    out = [f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="{_esc(title)}">',
           f'<text class="ttl" x="{L}" y="14">{_esc(title)}</text>']
    for t in yt:
        out.append(f'<line class="{"zero" if t == 0 else "grid"}" x1="{L}" x2="{W - R}" y1="{y(t):.1f}" y2="{y(t):.1f}"/>'
                   f'<text x="{L - 6}" y="{y(t) + 4:.1f}" text-anchor="end">{t:+g}</text>' if yt[0] < 0 else
                   f'<line class="grid" x1="{L}" x2="{W - R}" y1="{y(t):.1f}" y2="{y(t):.1f}"/>'
                   f'<text x="{L - 6}" y="{y(t) + 4:.1f}" text-anchor="end">{t:g}</text>')
    out.append(f'<text x="12" y="{(T + H - B) / 2:.0f}" transform="rotate(-90 12 {(T + H - B) / 2:.0f})" '
               f'text-anchor="middle">{_esc(y_label)}</text>')
    prev_group = None
    for i, c in enumerate(categories):
        cx = L + col * (i + 0.5)
        group, _, sub = c.partition(" ")
        if group != prev_group:
            out.append(f'<text x="{cx:.1f}" y="{H - B + 30}" text-anchor="start" style="font-weight:600">{_esc(group)}</text>')
            if prev_group is not None:
                out.append(f'<line class="grid" x1="{cx - col / 2:.1f}" x2="{cx - col / 2:.1f}" y1="{T}" y2="{H - B + 34}"/>')
            prev_group = group
        out.append(f'<text x="{cx:.1f}" y="{H - B + 14}" text-anchor="middle">{_esc(sub)}</text>')
        k = len(series)
        for j, s in enumerate(series):
            v = s["values"].get(c)
            if not v or v[0] is None:
                continue
            px = cx + (j - (k - 1) / 2) * min(4.0, col / (k + 1))
            if many:
                color = "var(--good-mark)" if v[0] > 0 else "var(--bad-mark)" if v[0] < 0 else "var(--ink-3)"
            else:
                color = f"var({SERIES[s['slot'] % len(SERIES)]})"
            mark = (f'<circle class="hit" tabindex="0" cx="{px:.1f}" cy="{y(v[0]):.1f}" r="9" data-tip="{_esc(v[1])}"/>'
                    f'<circle class="dot" cx="{px:.1f}" cy="{y(v[0]):.1f}" r="3.5" fill="{color}" '
                    f'stroke="var(--surface-1)" stroke-width="1.5"/>')
            out.append(f'<a href="{_esc(v[2])}" target="_blank" rel="noopener">{mark}</a>' if v[2] else mark)
    out.append("</svg>")
    if many:
        legend = (f'<span><i class="dotkey" style="background:var(--good-mark)"></i>above the median</span>'
                  f'<span><i class="dotkey" style="background:var(--bad-mark)"></i>below</span>'
                  f'<span><i class="dotkey" style="background:var(--ink-3)"></i>at the median</span>'
                  f'<span>{len(series)} runs; hover a dot to see which</span>')
    else:
        legend = "".join(f'<span><i class="dotkey" style="background:var({SERIES[s["slot"] % len(SERIES)]})"></i>{_esc(s["name"])}</span>'
                         for s in series)
    return f'<div class="chart viz-root">{"".join(out)}<div class="legend">{legend}</div></div>'
