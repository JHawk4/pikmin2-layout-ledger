"""Small inline-SVG charts for the report site (no JavaScript libraries).

Colors come from CSS custom properties defined by the page (see CSS below), so
light and dark themes swap in one place. Every mark that carries a value has a
`data-tip` attribute; TOOLTIP_JS shows it on hover and keyboard focus.
"""

from __future__ import annotations

import html
import math

SERIES = ["--series-1", "--series-2", "--series-3", "--series-4", "--series-5",
          "--series-6", "--series-7", "--series-8"]

CSS = """
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
.chart .hit:hover + .dot, .chart .hit:focus + .dot { stroke:var(--ink-1); stroke-width:2; }
.legend { display:flex; flex-wrap:wrap; gap:4px 14px; margin:8px 2px 2px; font-size:12px; color:var(--ink-2); }
.legend i { display:inline-block; width:16px; height:2px; vertical-align:middle; margin-right:6px; border-radius:1px; }
.legend i.dotkey { width:8px; height:8px; border-radius:50%; }
#viz-tip { position:fixed; pointer-events:none; z-index:10; background:var(--surface-1); color:var(--ink-2);
  border:1px solid var(--grid); border-radius:8px; padding:6px 9px; font:12px/1.4 system-ui,sans-serif;
  box-shadow:0 4px 14px rgba(0,0,0,.18); display:none; max-width:260px; }
#viz-tip b { color:var(--ink-1); display:block; font-size:13px; }
#viz-tip img { display:block; width:240px; height:200px; object-fit:contain; max-width:100%; margin-top:6px;
  border-radius:4px; background:#000; }
"""

TOOLTIP_JS = """
(() => {
  const tip = document.createElement('div'); tip.id = 'viz-tip'; document.body.appendChild(tip);
  const show = (el, x, y) => {
    tip.replaceChildren();
    const [head, ...rest] = el.dataset.tip.split('\\n');
    const b = document.createElement('b'); b.textContent = head; tip.appendChild(b);
    rest.forEach(line => { const d = document.createElement('div'); d.textContent = line; tip.appendChild(d); });
    if (el.dataset.img) { const im = document.createElement('img'); im.src = el.dataset.img; im.alt = ''; tip.appendChild(im); }
    tip.style.display = 'block';
    const w = tip.offsetWidth, h = tip.offsetHeight;
    tip.style.left = Math.min(innerWidth - w - 8, x + 14) + 'px';
    tip.style.top = Math.max(8, y - h - 10) + 'px';
  };
  document.querySelectorAll('[data-tip]').forEach(el => {
    el.addEventListener('pointermove', e => show(el, e.clientX, e.clientY));
    el.addEventListener('pointerleave', () => tip.style.display = 'none');
    el.addEventListener('focus', () => { const r = el.getBoundingClientRect(); show(el, r.right, r.top); });
    el.addEventListener('blur', () => tip.style.display = 'none');
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
    """series: dicts with name, slot (0-based color slot), points [(x, y, tip)], breaks allowed as None."""
    W, H, L, R, T, B = 960, 360, 56, 120, 26, 40
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
        color = f"var({SERIES[s['slot'] % len(SERIES)]})"
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
            out.append(f'<path d="{d}" fill="none" stroke="{color}" stroke-width="2" stroke-linejoin="round"/>')
        for px, py, tip in (p for p in s["points"] if p):
            out.append(f'<circle class="hit" tabindex="0" cx="{x(px):.1f}" cy="{y(py):.1f}" r="12" data-tip="{_esc(tip)}"/>'
                       f'<circle class="dot" cx="{x(px):.1f}" cy="{y(py):.1f}" r="3" fill="{color}" '
                       f'stroke="var(--surface-1)" stroke-width="1.5"/>')
        last = [p for p in s["points"] if p]
        if last:
            ly = y(last[-1][1])
            while any(abs(ly - o) < 13 for o in label_ys):
                ly += 13
            label_ys.append(ly)
            out.append(f'<text x="{x(last[-1][0]) + 14:.1f}" y="{ly + 4:.1f}" style="fill:var(--ink-1)">{_esc(s["name"])}</text>')
    out.append("</svg>")
    legend = "".join(f'<span><i style="background:var({SERIES[s["slot"] % len(SERIES)]})"></i>{_esc(s["name"])}</span>'
                     for s in series)
    return f'<div class="chart viz-root">{"".join(out)}<div class="legend">{legend}</div></div>'


def scatter_chart(points: list[tuple], title: str, x_label: str, y_label: str,
                  slope: float | None = None, quadrants: tuple | None = None) -> str:
    """Single-series scatter with a y = x reference and an optional fitted line through 0.

    points: (x, y, tip[, href[, image url]]); the image is shown in the tooltip on hover.
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
    for pt in points:
        px, py, tip = pt[:3]
        href = pt[3] if len(pt) > 3 else None
        img = pt[4] if len(pt) > 4 else None
        img_attr = f' data-img="{_esc(img)}"' if img else ""
        mark = (f'<circle class="hit" tabindex="0" cx="{s(px):.1f}" cy="{v(py):.1f}" r="12" data-tip="{_esc(tip)}"{img_attr}/>'
                f'<circle class="dot" cx="{s(px):.1f}" cy="{v(py):.1f}" r="4" fill="var(--series-1)" '
                f'fill-opacity=".75" stroke="var(--surface-1)" stroke-width="1.5"/>')
        out.append(f'<a href="{_esc(href)}" target="_blank" rel="noopener">{mark}</a>' if href else mark)
    out.append(f'<text x="{(L + W - R) / 2:.0f}" y="{H - 8}" text-anchor="middle">{_esc(x_label)}</text>')
    out.append(f'<text x="14" y="{(T + H - B) / 2:.0f}" transform="rotate(-90 14 {(T + H - B) / 2:.0f})" '
               f'text-anchor="middle">{_esc(y_label)}</text>')
    out.append("</svg>")
    legend = ('<div class="legend"><span><i class="dotkey" style="background:var(--series-1)"></i>one sublevel in one run</span>'
              '<span><i style="background:var(--series-2)"></i>fitted slope</span>'
              '<span><i style="background:var(--ink-3)"></i>y = x (perfect calibration)</span></div>')
    return f'<div class="chart viz-root">{"".join(out)}{legend}</div>'


def cumulative_chart(points: list[tuple], band: list[tuple], beta: float, title: str, subtitle: str) -> str:
    """Cumulative regression chart.

    points: (sum x^2, sum x*y, tip, href) after each observation in sort order.
    band:   (sum x^2, low, high) pointwise 95% band around the straight line y = beta * x.
    A straight walk along the line means the slope is the same throughout this ordering; a
    bend that leaves the band means the slope differs in part of it."""
    W, H, L, R, T, B = 460, 300, 52, 12, 40, 36
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
    out.append(f'<text x="{(L + W - R) / 2:.0f}" y="{H - 4}" text-anchor="middle">cumulative prediction² (s²)</text>')
    out.append(f'<text x="12" y="{(T + H - B) / 2:.0f}" transform="rotate(-90 12 {(T + H - B) / 2:.0f})" '
               f'text-anchor="middle">cumulative prediction × actual (s²)</text>')
    if band:
        poly = [f"{x(0):.1f},{y(0):.1f}"] + [f"{x(b[0]):.1f},{y(b[2]):.1f}" for b in band] + \
               [f"{x(b[0]):.1f},{y(b[1]):.1f}" for b in reversed(band)]
        out.append(f'<polygon points="{" ".join(poly)}" fill="var(--range)" fill-opacity=".55"/>')
    out.append(f'<line x1="{x(0):.1f}" y1="{y(0):.1f}" x2="{x(xs[-1]):.1f}" y2="{y(beta * xs[-1]):.1f}" '
               f'stroke="var(--ink-3)" stroke-width="1.5" stroke-dasharray="5 4"/>')
    d = f"M{x(0):.1f},{y(0):.1f} " + " ".join(f"L{x(p[0]):.1f},{y(p[1]):.1f}" for p in points)
    out.append(f'<path d="{d}" fill="none" stroke="var(--series-1)" stroke-width="2" stroke-linejoin="round"/>')
    for px, py, tip, href in points:
        hit = f'<circle class="hit" tabindex="0" cx="{x(px):.1f}" cy="{y(py):.1f}" r="7" data-tip="{_esc(tip)}"/>'
        out.append(f'<a href="{_esc(href)}" target="_blank" rel="noopener">{hit}</a>' if href else hit)
    out.append("</svg>")
    return f'<div class="chart viz-root">{"".join(out)}</div>'


def dot_chart(categories: list[str], series: list[dict], title: str, y_label: str) -> str:
    """Values per category for several series, as dots side by side within each category.

    series: dicts with name, slot, values {category: (value, tip, href)}."""
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
            color = f"var({SERIES[s['slot'] % len(SERIES)]})"
            mark = (f'<circle class="hit" tabindex="0" cx="{px:.1f}" cy="{y(v[0]):.1f}" r="9" data-tip="{_esc(v[1])}"/>'
                    f'<circle class="dot" cx="{px:.1f}" cy="{y(v[0]):.1f}" r="3.5" fill="{color}" '
                    f'stroke="var(--surface-1)" stroke-width="1.5"/>')
            out.append(f'<a href="{_esc(v[2])}" target="_blank" rel="noopener">{mark}</a>' if v[2] else mark)
    out.append("</svg>")
    legend = "".join(f'<span><i class="dotkey" style="background:var({SERIES[s["slot"] % len(SERIES)]})"></i>{_esc(s["name"])}</span>'
                     for s in series)
    return f'<div class="chart viz-root">{"".join(out)}<div class="legend">{legend}</div></div>'
