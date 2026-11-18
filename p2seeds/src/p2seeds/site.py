"""Build the report site: a landing page over every judged run, and one page per run.

  data/output/index.html               runs table, seed-order chart, judge calibration
  data/output/<run>/judge.html         layouts and judge results for one run

Seed order: each detected letter seed is located in the RNG sequence relative to
the run's first one (how many RNG steps after it). Over a run that number must
only grow, roughly with time; a point out of line marks a doubtful seed.

Judge calibration: the time from one entry screen to the next entry of the same
cave is how long the runner took on that sublevel (including the load). Across
runs of the same sublevel, regress that time on the judge's estimate with a
fixed effect per sublevel and per runner:
    actual = runner + sublevel + slope * judge
A slope of 1 means one predicted second is one real second.
"""

from __future__ import annotations

import html
import json
from pathlib import Path

import numpy as np

from . import cavegen, charts, judge2, judge_report, rng, treasures

STORY_ORDER = ["EC", "HoB", "WFG", "SH", "BK", "SCx", "FC", "CoS", "GK", "SR", "SC", "CoC", "HoH", "DD"]

STEP_LIMIT = 5_000_000       # gap allowed between two plotted seeds (a sublevel is ~10k-500k steps)


def _run_label(run: dict, fallback: str) -> str:
    """A run is a player and a time: 'JackDraz 1:30:25'."""
    name = ", ".join(p["name"] for p in run.get("players", [])) or fallback
    t = run.get("time_seconds")
    return f"{name} {_fmt_time(t)}" if t else name


def _load(root: Path) -> list[dict]:
    runs = []
    for d in sorted(p.parent for p in root.glob("*/judge.json")):
        data = json.loads((d / "judge.json").read_text(encoding="utf-8"))
        meta = data.get("meta", {})
        run = meta.get("run", {})
        runs.append({"dir": d, "slug": d.name, "meta": meta, "run": run, "kind": data.get("kind", "pod"),
                     "entries": data["entries"], "fps": meta.get("fps", 30.0),
                     "player": ", ".join(p["name"] for p in run.get("players", [])) or d.name,
                     "runner": _run_label(run, d.name)})
    runs.sort(key=lambda r: (r["run"].get("time_seconds") or 1e9, r["slug"]))     # fastest first
    return runs


def seed_steps(entries: list[dict]) -> list[int | None]:
    """RNG steps from the run's first confirmed letter seed to each entry's letter seed.

    Only high-confidence seeds are placed. The line starts at the first one that the next
    high-confidence seed follows within STEP_LIMIT steps (so a misread first seed cannot anchor
    it); each later seed is placed from the last one placed, and one that is not found within
    STEP_LIMIT steps (out of order, or wrong) gets None, so one bad seed does not break the rest."""
    seeds = [int(e["letter_seed"], 16) if e.get("letter_seed") and e.get("confidence") == "high" else None
             for e in entries]
    idx = [i for i, sd in enumerate(seeds) if sd is not None]
    out: list[int | None] = [None] * len(entries)
    anchor = next((i for i, j in zip(idx, idx[1:])
                   if rng.distance(seeds[i], seeds[j], limit=STEP_LIMIT) is not None), None)
    if anchor is None:
        return out
    prev, total = seeds[anchor], 0
    out[anchor] = 0
    for i in idx:
        if i <= anchor:
            continue
        d = rng.distance(prev, seeds[i], limit=STEP_LIMIT)
        if d is not None:
            total += d
            prev = seeds[i]
            out[i] = total
    return out


def _mode(values):
    vals = [v for v in values if v is not None]
    if not vals:
        return None
    best = max(set(vals), key=vals.count)
    return best if vals.count(best) * 2 > len(vals) else None    # a clear majority only


POKOS_PER_SECOND = 2.0     # Pay Off Debt: two extra pokos are worth one second


def actuals(runs: list[dict]) -> list[dict]:
    """Per run: entry frame -> what the runner did on that sublevel against the median run.

    took: seconds from this entry screen to the next one (same cave); pokos from the treasure
    panels. net = (took - median took) - (pokos - median pokos) / 2 for Pay Off Debt, plain
    time otherwise. Negative = faster than the median run."""
    plays: dict[str, list[tuple[int, str, float, int | None]]] = {}
    for i, r in enumerate(runs):
        tre = treasures.load(r["dir"])
        e = r["entries"]
        for a, b in zip(e, e[1:]):
            if a["cave"] == b["cave"] and a.get("sublevel") and b.get("sublevel") == a["sublevel"] + 1:
                if r["kind"] == "pod" and not judge_report.trusted(a):
                    continue      # pokos are read against the seed's treasures: no trusted seed, no net time
                t = tre.get(str(a["frame"]))
                plays.setdefault(f'{a["cave"]} {a["sublevel"]}', []).append(
                    (i, str(a["frame"]), (b["frame"] - a["frame"]) / r["fps"], treasures.reliable_pokos(t)))
    out: list[dict] = [{} for _ in runs]
    for sub, ps in plays.items():
        if len(ps) < 2:
            continue
        med_t = float(np.median([p[2] for p in ps]))
        pk = [p[3] for p in ps if p[3] is not None]
        med_p = float(np.median(pk)) if pk else None
        for i, frame, took, pokos in ps:
            net = took - med_t
            if runs[i]["kind"] == "pod" and pokos is not None and med_p is not None:
                net -= (pokos - med_p) / POKOS_PER_SECOND
            out[i][frame] = {"net": net, "took": took, "median_took": med_t, "pokos": pokos,
                             "median_pokos": med_p, "n": len(ps)}
    return out


def _layout_url(run: dict, entry: dict) -> str | None:
    """The run's rendered layout for this entry, as a path relative to index.html (loaded only on hover)."""
    name = f"layout_{entry['frame']}_{entry['cave']}-{entry['sublevel']}.png"
    return f"{run['slug']}/img/{name}" if (run["dir"] / "img" / name).exists() else None


def _treasure_names(t) -> str:
    picks = [c for c in (t or {}).get("collected", []) if c]
    return ", ".join(f"{n.replace('_', ' ')} ({p})" for n, p in picks)


def calibration(runs: list[dict], key: str = "judge", drop: set | None = None) -> dict:
    """Judge estimate vs measured sublevel outcome, with sublevel and runner fixed effects.

    For Pay Off Debt the outcome is net time: seconds taken minus pokos collected / 2, so a
    runner who stops for an extra treasure is credited for its pokos. For other categories
    it is plain time, and plays that took a different number of treasures than most runs
    of the sublevel are left out instead.

    `key`: "judge" (CaveGen's) or "judge2" (judge2/, the refit PoD judge). `drop`: (run index,
    sublevel) plays to leave out, e.g. outliers where the runner made a big mistake."""
    order = {c: k for k, c in enumerate(STORY_ORDER)}
    drop = drop or set()
    rows = []
    for i, r in enumerate(runs):
        tre = treasures.load(r["dir"])
        e = r["entries"]
        net = r["kind"] == "pod"
        for a, b in zip(e, e[1:]):
            if (a["cave"] == b["cave"] and a.get("sublevel") and b.get("sublevel") == a["sublevel"] + 1
                    and a.get(f"{key}_score") is not None and not a.get(f"{key}_fixed") and judge_report.trusted(a)
                    and (i, f'{a["cave"]} {a["sublevel"]}') not in drop):
                ref = cavegen.reference_scores(a["cave"], a["sublevel"], r["kind"])
                t = tre.get(str(a["frame"]))
                took = (b["frame"] - a["frame"]) / r["fps"]
                pokos = treasures.reliable_pokos(t)
                if net and pokos is None:
                    continue          # Pay Off Debt is judged on net time: no reliable pokos, no outcome
                rows.append({
                    "run": i, "runner": r["runner"], "sub": f'{a["cave"]} {a["sublevel"]}',
                    "order": order.get(a["cave"], 99) * 100 + a["sublevel"],
                    "judge": a[f"{key}_score"], "actual": took,
                    "cost": took - pokos / POKOS_PER_SECOND if net and pokos is not None else took,
                    "net": net and pokos is not None, "pokos": pokos, "names": _treasure_names(t),
                    "seed": a.get("layout_seed"), "link": a.get("link"), "time": a.get("time", ""),
                    "img": _layout_url(r, a),
                    "median": a.get(f"{key}_median"),
                    "spread": (a["judge2_hi"] - a["judge2_lo"] if key == "judge2"
                               else float(np.percentile(ref, 95) - np.percentile(ref, 5)) if ref is not None else 0.0),
                    "treasures": t["treasures"] if t else None,
                })
    # plain-time plays that followed another route (a different number of treasures) are left out
    by_sub: dict[str, list[dict]] = {}
    for row in rows:
        by_sub.setdefault(row["sub"], []).append(row)
    excluded = []
    for sub, rs in by_sub.items():
        usual = _mode([row["treasures"] for row in rs])
        for row in rs:
            row["usual"] = usual
            if not row["net"] and usual is not None and row["treasures"] is not None and row["treasures"] != usual:
                excluded.append(row)
    rows = [row for row in rows if row not in excluded]
    counts: dict[str, int] = {}
    for row in rows:
        counts[row["sub"]] = counts.get(row["sub"], 0) + 1
    rows = [row for row in rows if counts[row["sub"]] >= 2]      # a lone play carries no comparison
    if len(rows) < 5:
        return {"n": len(rows), "excluded": excluded}

    subs = sorted({row["sub"] for row in rows})
    runs_used = sorted({row["run"] for row in rows})
    X_fe = np.zeros((len(rows), len(subs) + len(runs_used) - 1))
    for k, row in enumerate(rows):
        X_fe[k, subs.index(row["sub"])] = 1
        j = runs_used.index(row["run"])
        if j > 0:
            X_fe[k, len(subs) + j - 1] = 1

    def resid(v):
        coef, *_ = np.linalg.lstsq(X_fe, v, rcond=None)
        return v - X_fe @ coef

    def fit(xr, yr):
        slope = float(xr @ yr / (xr @ xr))
        e = yr - slope * xr
        dof = max(1, len(rows) - X_fe.shape[1] - 1)
        return slope, float(np.sqrt((e @ e) / dof / (xr @ xr))), float(np.corrcoef(xr, yr)[0, 1])

    # saved = the negative of what was spent, for both the prediction and the outcome
    # seconds against the other runs of the sublevel; negative = faster, as on splits
    xr = resid(np.array([row["judge"] for row in rows]))
    yr = resid(np.array([row["cost"] for row in rows]))
    slope, se, corr = fit(xr, yr)
    time_only = fit(xr, resid(np.array([row["actual"] for row in rows])))
    for row, a, b in zip(rows, xr, yr):
        row["x"], row["y"] = float(a), float(b)
    any_net = any(row["net"] for row in rows)

    # medians of the plays of each sublevel, so the tooltip can say "vs median" for everything
    med = {}
    for sub in {row["sub"] for row in rows}:
        rs = [row for row in rows if row["sub"] == sub]
        pk = [row["pokos"] for row in rs if row["pokos"] is not None]
        med[sub] = (float(np.median([row["actual"] for row in rs])), float(np.median([row["cost"] for row in rs])),
                    float(np.median(pk)) if pk else None)

    def tip(row):
        m_took, m_cost, m_pk = med[row["sub"]]
        jm = row["judge"] - row["median"] if row.get("median") is not None else None
        lines = [f"run {row['y']:+.1f} s{' net' if row['net'] else ''} · judge {row['x']:+.1f} s  (after runner pace)",
                 f"{row['sub']} · {row['runner']} · {row['time']}",
                 f"layout seed {row['seed']}",
                 (f"judge: layout {jm:+.1f} s vs the median layout" if jm is not None else "judge: no median"),
                 f"runner: took {row['actual'] - m_took:+.1f} s vs the median run here"
                 + (f", net {row['cost'] - m_cost:+.1f} s" if row["net"] else "")]
        if row["pokos"] is not None:
            vs = f" ({row['pokos'] - m_pk:+g} vs median)" if m_pk is not None else ""
            lines.append(f"{row['pokos']} pokos{vs}" + (f": {row['names']}" if row["names"] else ""))
        return "\n".join(lines)

    pts = [(row["x"], row["y"], tip(row), row["link"], row["img"]) for row in rows]
    e = yr - xr                                  # what a perfectly calibrated judge leaves unexplained
    r2 = float(1 - (e @ e) / (yr @ yr)) if yr @ yr > 0 else 0.0
    for row, ek in zip(rows, e):
        row["e"] = float(ek)
    return {"n": len(rows), "sublevels": len(subs), "slope": slope, "se": se, "corr": corr, "points": pts,
            "rows": rows, "excluded": excluded, "tip": tip, "net": any_net, "time_only": time_only, "r2": r2,
            "key": key}


OUTLIER_Z = 4.0          # robust z-score (median absolute deviation) of the unexplained seconds


def outliers(cals: list[dict]) -> dict:
    """(run, sublevel) -> row for plays far off under every judge: more than OUTLIER_Z robust
    standard deviations from what each judge predicts. A big mistake (a death, a lost treasure,
    a misplay) is not something any layout judge can explain, and one such play can pull
    the slope; a play only one judge misses is kept."""
    flagged = None
    for cal in cals:
        rows = cal.get("rows") or []
        if not rows:
            continue
        e = np.array([row["e"] for row in rows])
        scale = 1.4826 * float(np.median(np.abs(e - np.median(e)))) or 1.0
        far = {(row["run"], row["sub"]): row for row in rows if abs(row["e"] - np.median(e)) > OUTLIER_Z * scale}
        flagged = far if flagged is None else {k: v for k, v in far.items() if k in flagged}
    return flagged or {}


SORTS = [
    ("prediction", "Sorted by predicted time saved", lambda r: r["x"], "low to high"),
    ("size", "Sorted by size of the prediction", lambda r: abs(r["x"]), "small to large swings"),
    ("spread", "Sorted by how variable the sublevel is", lambda r: r["spread"], "5th–95th spread, low to high"),
    ("length", "Sorted by sublevel length", lambda r: r["median"] or 0, "median judge time, short to long"),
    ("order", "Sorted by game order", lambda r: r["order"], "cave and sublevel"),
    ("runner", "Sorted by runner", lambda r: (r["run"], r["order"]), "one runner after another"),
]


def kolmogorov_p(c: float) -> float:
    """P(sup |Brownian bridge| > c)."""
    if c <= 0:
        return 1.0
    return float(min(1.0, max(0.0, 2 * sum((-1) ** (j - 1) * np.exp(-2 * j * j * c * c) for j in range(1, 101)))))


def cumulative(rows: list[dict], slope: float, key) -> dict:
    """Walk the observations in `key` order, accumulating x^2 and x*y.

    With D_k = sum x(y - slope x) and variance time V_k = sum x^2 e^2 (each point's own
    noise), D is a Brownian bridge in V when the slope is the same throughout, so
    max|D| / sqrt(V_total) has the Kolmogorov distribution."""
    rs = sorted(rows, key=key)
    sxx = sxy = d = v = 0.0
    pts, path = [], []
    vt = sum(r["x"] ** 2 * (r["y"] - slope * r["x"]) ** 2 for r in rs)
    worst, worst_at = 0.0, None
    for r in rs:
        sxx += r["x"] ** 2
        sxy += r["x"] * r["y"]
        d += r["x"] * (r["y"] - slope * r["x"])
        v += r["x"] ** 2 * (r["y"] - slope * r["x"]) ** 2
        sd = np.sqrt(max(0.0, v * (vt - v) / vt)) if vt > 0 else 0.0
        path.append((sxx, slope * sxx - 1.96 * sd, slope * sxx + 1.96 * sd))
        pts.append((sxx, sxy, r))
        if abs(d) > worst:
            worst, worst_at = abs(d), r
    stat = worst / np.sqrt(vt) if vt > 0 else 0.0
    return {"points": pts, "band": path, "stat": float(stat), "p": kolmogorov_p(stat), "worst": worst_at}


def _link(href: str | None, text: str) -> str:
    if not href:
        return html.escape(text)
    return f'<a href="{html.escape(href)}" target="_blank" rel="noopener">{html.escape(text)}</a>'


def _calibration_extras(cal: dict) -> tuple[str, str]:
    """(excluded plays table, cumulative-slope section)."""
    ex = cal.get("excluded", [])
    ex_rows = "".join(
        f"<tr><td>{html.escape(r['sub'])}</td><td>{html.escape(r['runner'])}</td>"
        f"<td class='num'>{r['treasures']}</td><td class='num'>{r['usual']}</td>"
        f"<td class='num'>{r['actual']:.1f} s</td><td>{_link(r.get('link'), r.get('time', ''))}</td></tr>"
        for r in ex)
    ex_table = (f'<details><summary>{len(ex)} plays left out: a different number of treasures than most runs of '
                f'that sublevel</summary><div class="tablewrap"><table><thead><tr><th>Sublevel</th><th>Runner</th>'
                f'<th class="num">Treasures</th><th class="num">Usual</th><th class="num">Took</th><th>Video</th>'
                f'</tr></thead><tbody>{ex_rows}</tbody></table></div></details>') if ex else ""
    if not cal.get("rows"):
        return ex_table, ""
    curves, findings = [], []
    for key, title, fn, how in SORTS:
        c = cumulative(cal["rows"], cal["slope"], fn)
        pts = [(sxx, sxy, f"{cal['tip'](r)}\nrunning totals: Σx² {sxx:,.0f}, Σxy {sxy:,.0f}", r["link"])
               for sxx, sxy, r in c["points"]]
        verdict = ("<b>significant bend</b>" if c["p"] < 0.01 else "possible bend" if c["p"] < 0.05
                   else "no significant bend")
        where = "" if c["p"] >= 0.05 else f", largest around {html.escape(c['worst']['sub'])} ({html.escape(c['worst']['runner'])})"
        curves.append(charts.cumulative_chart(pts, c["band"], cal["slope"], title,
                                              f"{how} · max deviation {c['stat']:.2f}, p = {c['p']:.2f}"))
        findings.append(f"<li>{html.escape(title)}: {verdict} (p = {c['p']:.3f}){where}</li>")
    section = f'''<h3>Is the slope the same everywhere?</h3>
<p>Each chart walks through the same plays in a different order, adding up prediction² along the bottom and
prediction × actual up the side, so the slope of the walk so far is the regression slope over those plays. If the
judge is off by the same proportion everywhere, the walk follows the dashed line and stays inside the grey 95% band.
A bend that leaves the band shows where the slope differs: for example, a steeper end in "size" would mean big
predicted swings are more reliable than small ones. The test allows each play its own noise level.</p>
<ul class="findings">{"".join(findings)}</ul>
<div class="curves">{"".join(curves)}</div>'''
    return ex_table, section


def pokos_section(runs: list[dict]) -> str:
    """Pokos collected per sublevel for every Pay Off Debt run, as a chart and a table."""
    pod = [(i, r) for i, r in enumerate(runs) if r["kind"] == "pod"]
    per_run = {}
    for i, r in pod:
        entries = {str(e["frame"]): e for e in r["entries"]}
        vals = {}
        for k, t in treasures.load(r["dir"]).items():
            if treasures.reliable_pokos(t) is None:
                continue
            e = entries.get(k, {})
            if not judge_report.trusted(e):
                continue          # the treasure values come from the seed's layout
            sub = f'{t["cave"]} {t["sublevel"]}'
            names = _treasure_names(t)
            vals[sub] = (t["pokos"], f"{t['pokos']} pokos\n{sub} · {r['runner']} · {e.get('time', '')}"
                         + (f"\n{names}" if names else "\nno treasure"), e.get("link"))
        if vals:
            per_run[i] = vals
    if not per_run:
        return ""
    order = {c: k for k, c in enumerate(STORY_ORDER)}
    cats = sorted({c for v in per_run.values() for c in v},
                  key=lambda c: (order.get(c.split()[0], 99), int(c.split()[1])))
    # the median run on each sublevel is the expected baseline
    median = {c: float(np.median([v[c][0] for v in per_run.values() if c in v])) for c in cats}
    series = []
    for i, v in per_run.items():
        rel = {c: (p - median[c], f"{p - median[c]:+g} pokos vs the median ({p} vs {median[c]:g})\n{tip.split(chr(10), 1)[1]}", href)
               for c, (p, tip, href) in v.items()}
        series.append({"name": runs[i]["runner"], "slot": i, "values": rel})
    # a grid: one row per run, one column per sublevel where somebody differs from the median
    diff_cats = [c for c in cats if any(c in v and v[c][0] != median[c] for v in per_run.values())]
    same = len(cats) - len(diff_cats)
    big = max((abs(v[c][0] - median[c]) for v in per_run.values() for c in diff_cats if c in v), default=1) or 1
    head = "".join(f"<th class='num'>{html.escape(c)}<br><span class='muted'>{median[c]:g}</span></th>" for c in diff_cats)
    rows = []
    for i, v in per_run.items():
        cells = []
        for c in diff_cats:
            if c not in v:
                cells.append("<td class='num muted'>·</td>")
                continue
            p, tip, href = v[c]
            d = p - median[c]
            if d == 0:
                cells.append(f"<td class='num muted' data-tip='{html.escape(chr(10).join([f'{p} pokos (the median)', tip.split(chr(10), 1)[1]]))}'>0</td>")
                continue
            mark = "--good-mark" if d > 0 else "--bad-mark"
            pct = 18 + 52 * min(1.0, abs(d) / big)
            text = f"{d:+g}"
            if href:
                text = f"<a href='{html.escape(href)}' target='_blank' rel='noopener'>{text}</a>"
            tipx = f"{d:+g} pokos vs the median ({p} vs {median[c]:g})" + chr(10) + tip.split(chr(10), 1)[1]
            cells.append(f"<td class='num heat' tabindex='0' style='background:color-mix(in srgb, var({mark}) {pct:.0f}%, transparent)' "
                         f"data-tip='{html.escape(tipx)}'>{text}</td>")
        tot = sum(v[c][0] - median[c] for c in v)
        tone = "good" if tot > 0 else "bad" if tot < 0 else "mid"
        rows.append(f"<tr><td>{html.escape(runs[i]['runner'])}</td><td class='num {tone}-text'><b>{tot:+g}</b></td>{''.join(cells)}</tr>")
    hidden = (f" {same} other sublevel{'s' if same != 1 else ''}, where every run got the median, "
              f"{'are' if same != 1 else 'is'} left out.") if same else ""
    return f'''<h2>Pokos by sublevel</h2>
<p>Pokos collected on each sublevel (Pay Off Debt runs), from treasures and from creatures, against the median run on the same sublevel,
the expected baseline. Each row is a run, each column a sublevel where at least one run differs from the median (the
median is under the name). Green cells collected more than usual, red cells fewer; a darker cell is a bigger
difference, and a dot means the sublevel was not read.{hidden} Each treasure collected shows a panel with its value;
the panels are counted in the video and matched to the treasures CaveGen places on that layout. Each panel also shows
the run's running Total, so pokos from creatures are whatever the Total rose by beyond the treasure; they are shared
among the cave sublevels between the two panels by time spent in each (never the surface, and treasures picked up on
the surface count toward no sublevel). Hover a cell for the treasures; click the number to open the video.</p>
<div class="tablewrap viz-root"><table class="heatgrid">
<thead><tr><th>Run</th><th class='num'>Total vs median</th>{head}</tr></thead><tbody>{"".join(rows)}</tbody>
</table></div>'''


def _fmt_time(t):
    if not t:
        return ""
    return f"{int(t // 3600)}:{int(t % 3600 // 60):02d}:{int(t % 60):02d}"


def build(root: str | Path = "data/output") -> Path:
    root = Path(root)
    if judge2.available():
        for d in sorted(root.iterdir()):
            if (d / "judge.json").exists():
                judge2.add_to_run(d)          # only fills what is missing
    runs = _load(root)
    acts = actuals(runs)
    for r, a in zip(runs, acts):
        judge_report.write_page(r["dir"], home="../index.html", actual=a)

    # seed order chart
    series, table_rows = [], []
    for i, r in enumerate(runs):
        steps = seed_steps(r["entries"])
        pts = []
        for e, s in zip(r["entries"], steps):
            if s is None:
                pts.append(None)
                continue
            minutes = e["frame"] / r["fps"] / 60
            pts.append((minutes, s / 1e6, f"{s / 1e6:.2f} M steps\n{e['cave']} {e['sublevel']} · {r['runner']}\n"
                                          f"at {e.get('time', '')} in the video"))
            table_rows.append((r["runner"], e.get("time", ""), f"{e['cave']} {e['sublevel']}", e["letter_seed"], s))
        series.append({"name": r["runner"], "slot": i, "points": pts})
    order_chart = charts.line_chart(series, "RNG position of each detected seed", "minutes into the video",
                                    "million RNG steps after the run's first seed")

    keys = ["judge"] + (["judge2"] if any(x.get("judge2_score") is not None for r in runs for x in r["entries"]) else [])
    first = [calibration(runs, k) for k in keys]
    out = outliers(first)
    # compare the judges on the same plays (they disagree on a few fixed floors)
    seen = [{(row["run"], row["sub"]) for row in c.get("rows") or []} for c in first]
    not_shared = set().union(*seen) - set.intersection(*seen) if seen else set()
    cals = {k: calibration(runs, k, drop=set(out) | not_shared) for k in keys}
    cal = cals["judge"]
    names = {"judge": "CaveGen judge", "judge2": "judge2 (refit)"}
    if cal.get("points"):
        outcome = ("run: net seconds vs other runs (time − pokos ÷ 2; negative = faster)" if cal["net"]
                   else "run: seconds vs other runs (negative = faster)")
        charts_html = []
        for k, c in cals.items():
            if not c.get("points"):
                continue
            charts_html.append(charts.scatter_chart(
                c["points"], f"{names[k]}: prediction vs actual sublevel outcome",
                f"{names[k]}: seconds vs the other runs' layouts (negative = faster layout)",
                outcome, slope=c["slope"],
                quadrants=(("judge: bad layout\nrun: slower", "bad"),
                           ("judge: bad layout\nrun: faster", None),
                           ("judge: good layout\nrun: slower", None),
                           ("judge: good layout\nrun: faster", "good"))))
        cal_chart = "".join(charts_html)
        cmp_rows = "".join(
            f"<tr><td>{names[k]}</td><td class='num'>{c['n']}</td>"
            f"<td class='num'><b>{c['slope']:.2f}</b> ({c['slope'] - 1.96 * c['se']:.2f}–{c['slope'] + 1.96 * c['se']:.2f})</td>"
            f"<td class='num'>{c['corr']:.2f}</td><td class='num'>{c['r2']:.2f}</td></tr>"
            for k, c in cals.items() if c.get("points"))
        out_rows = "".join(
            f"<tr><td>{html.escape(row['sub'])}</td><td>{html.escape(row['runner'])}</td>"
            f"<td>{_link(row['link'], row['time'] or 'video')}</td><td class='num'>{row['y']:+.1f} s</td></tr>"
            for row in sorted(out.values(), key=lambda r: -abs(r["y"])))
        cal_text = (f"<p>Over <b>{cal['n']}</b> sublevel plays ({cal['sublevels']} sublevels seen in at least two runs), "
                    f"each second a judge predicts should be worth one second of {'net' if cal['net'] else 'real'} time. "
                    f"The slope is what it is actually worth (1 = calibrated, below 1 = the judge overstates differences "
                    f"between layouts); R² is the share of the runs' differences a judge explains taking its seconds at face value.</p>"
                    f"<div class='tablewrap'><table><thead><tr><th>Judge</th><th class='num'>Plays</th><th class='num'>Slope (95%)</th>"
                    f"<th class='num'>Correlation</th><th class='num'>R² (slope 1)</th></tr></thead><tbody>{cmp_rows}</tbody></table></div>"
                    + (f"<p>The outcome is <b>net time</b>: seconds minus pokos ÷ 2. The CaveGen judge on plain time would have slope "
                       f"{cal['time_only'][0]:.2f} (correlation {cal['time_only'][2]:.2f}).</p>" if cal["net"] else "")
                    + (f"<details><summary>{len(out)} play{'s' if len(out) != 1 else ''} left out as likely mistakes</summary>"
                       f"<p class='muted small'>More than {OUTLIER_Z:g} robust standard deviations off under every judge, so no layout "
                       f"judge explains them (a death, a lost treasure, a misplay). Check them in the video.</p>"
                       f"<div class='tablewrap'><table><thead><tr><th>Sublevel</th><th>Runner</th><th>Video</th>"
                       f"<th class='num'>Run vs others</th></tr></thead><tbody>{out_rows}</tbody></table></div></details>" if out else ""))
    else:
        cal_chart, cal_text = "", "<p class='muted'>Not enough runs share sublevels to check calibration.</p>"

    ex_table, curve_html = _calibration_extras(cal)
    pokos_html = pokos_section(runs)

    trs = []
    for r in runs:
        e = [x for x in r["entries"] if x.get("cave")]
        judged = [x for x in e if "judge_score" in x and not x.get("judge_fixed") and judge_report.trusted(x)]
        judge_total = sum(x.get("judge_vs_median") or 0 for x in judged)
        j2 = [x for x in judged if x.get("judge2_score") is not None]
        judge2_total = sum(x["judge2_vs_median"] for x in j2) if j2 else None
        act = acts[runs.index(r)]
        run_total = sum(v["net"] for v in act.values()) if act else None
        high = sum(1 for x in e if x.get("confidence") == "high")
        link = r["run"].get("weblink")
        tag = "former WR" if r["run"].get("series") == "wr" else str(r["run"].get("place", ""))
        trs.append(f'<tr><td>{tag}</td><td><a href="{html.escape(r["slug"])}/judge.html">'
                   f'{html.escape(r["player"])}</a></td><td>{_fmt_time(r["run"].get("time_seconds"))}</td>'
                   f'<td>{html.escape(r["run"].get("date", ""))}</td><td>{html.escape(r["run"].get("platform", ""))}</td>'
                   f'<td class="num">{len(e)}</td><td class="num">{high}</td><td class="num">{judge_report._num(judge_total)}</td><td class="num">{judge_report._num(judge2_total)}</td><td class="num">{judge_report._num(run_total)}</td>'
                   f'<td><a href="{html.escape(r["slug"])}/report.html">detection</a>'
                   f'{f" · <a href={chr(34)}{html.escape(link)}{chr(34)} target=_blank rel=noopener>speedrun.com</a>" if link else ""}</td></tr>')

    data_rows = "".join(f"<tr><td>{html.escape(a)}</td><td>{html.escape(b)}</td><td>{html.escape(c)}</td>"
                        f"<td><code>{html.escape(d)}</code></td><td class='num'>{s:,}</td></tr>"
                        for a, b, c, d, s in table_rows)
    page = f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Pikmin 2 run seeds</title>
<style>
:root {{ --bg:#f6f6f4; --fg:#1d1d1b; --muted:#6b6b66; --card:#fff; --line:#deded8; --good:#1f7a3a; --bad:#b42318; }}
@media (prefers-color-scheme: dark) {{ :root:not([data-theme="light"]) {{ --bg:#161614; --fg:#ececea; --muted:#9a9a94;
  --card:#20201e; --line:#33332f; --good:#5cc27a; --bad:#f0786d; }} }}
.good-text {{ color:var(--good); }} .bad-text {{ color:var(--bad); }} .mid-text {{ color:var(--muted); }}
:root[data-theme="dark"] {{ --bg:#161614; --fg:#ececea; --muted:#9a9a94; --card:#20201e; --line:#33332f;
  --good:#5cc27a; --bad:#f0786d; }}
* {{ box-sizing:border-box; }}
body {{ background:var(--bg); color:var(--fg); font:15px/1.5 system-ui,sans-serif; margin:0; padding:24px 16px 48px; }}
main {{ max-width:1080px; margin:0 auto; }}
h1 {{ font-size:26px; margin:0 0 4px; }} h2 {{ font-size:19px; margin:36px 0 8px; }}
a {{ color:inherit; }} .muted {{ color:var(--muted); }} p {{ max-width:780px; }}
.tablewrap {{ overflow-x:auto; background:var(--card); border:1px solid var(--line); border-radius:10px; }}
.heatgrid {{ font-size:12px; }} .heatgrid th, .heatgrid td {{ padding:4px 7px; white-space:nowrap; }}
.heatgrid th:first-child, .heatgrid td:first-child {{ position:sticky; left:0; background:var(--card); z-index:1; }}
.heatgrid td.heat a {{ color:var(--fg); text-decoration:none; font-weight:600; }}
.heatgrid td.heat {{ outline:none; }} .heatgrid td.heat:hover, .heatgrid td.heat:focus {{ box-shadow:inset 0 0 0 2px var(--fg); }}
table {{ border-collapse:collapse; width:100%; font-size:14px; }}
th, td {{ text-align:left; padding:7px 10px; border-bottom:1px solid var(--line); white-space:nowrap; }}
th {{ color:var(--muted); font-weight:500; }} tr:last-child td {{ border-bottom:none; }}
.num {{ text-align:right; font-variant-numeric:tabular-nums; }}
.curves {{ display:grid; grid-template-columns:repeat(auto-fill,minmax(420px,1fr)); gap:12px; }}
@media (max-width:480px) {{ .curves {{ grid-template-columns:1fr; }} }}
h3 {{ font-size:16px; margin:28px 0 6px; }} .findings {{ font-size:14px; }}
details {{ margin:10px 0 0; }} summary {{ cursor:pointer; color:var(--muted); font-size:14px; }}
details .tablewrap {{ max-height:360px; overflow:auto; margin-top:8px; }}
code {{ font:13px ui-monospace,Consolas,monospace; }}
{charts.CSS}
</style></head><body><main>
<h1>Pikmin 2 run seeds</h1>
<p class="muted">Sublevel seeds recovered from speedrun videos, with every layout scored by CaveGen's judge.
Open a run for its layouts and per-sublevel luck.</p>

<div class="tablewrap"><table>
<thead><tr><th>Board</th><th>Runner</th><th>Time</th><th>Date</th><th>Platform</th><th class="num">Sublevels</th>
<th class="num">High conf.</th><th class="num">Judge (layouts)</th><th class="num">judge2</th><th class="num">Run (net)</th><th>Pages</th></tr></thead>
<tbody>{"".join(trs)}</tbody></table></div>

<h2>Seed order</h2>
<p>Each seed's position in the game's random number sequence, counted from the run's first seed. The RNG only moves
forward, so every line should climb steadily; a point off its line, or a break, marks a doubtful seed.</p>
{order_chart}
<details><summary>Show as a table</summary><div class="tablewrap"><table>
<thead><tr><th>Runner</th><th>Video time</th><th>Sublevel</th><th>Letter seed</th><th class="num">RNG steps</th></tr></thead>
<tbody>{data_rows}</tbody></table></div></details>

{pokos_html}

<h2>Is the judge calibrated?</h2>
<p>Each sublevel's real time is measured from the video: from its entry screen to the next sublevel's entry screen
(so each cave's last sublevel is left out). Both the judge's estimate and the real time are compared within the same
sublevel across runs, after removing each runner's overall pace. For Pay Off Debt the outcome counts pokos too, at
two pokos per second; for other categories, plays where the runner collected a different number of treasures than
most runs of that sublevel are left out. Only seeds read at high confidence are used: a misread seed is a wrong
layout, so its judge score would be noise. Hover a point for its seed and pokos; click it to open the video there.</p>
{cal_text}
{cal_chart}
{ex_table}
{curve_html}
</main>
<script>{charts.TOOLTIP_JS}</script>
</body></html>'''
    dest = root / "index.html"
    dest.write_text(page, encoding="utf-8")
    return dest


def export(root: str | Path = "data/output", out: str | Path = "data/pages") -> Path:
    """Copy the built site (landing page, each run's pages and layout images) into `out`,
    ready to serve as static files (GitHub Pages). Videos, caches and JSON stay behind."""
    import shutil
    root, out = Path(root), Path(out)
    if out.exists():
        import os
        import stat

        def writable(func, path, _exc):          # git's pack files are read-only on Windows
            os.chmod(path, stat.S_IWRITE)
            func(path)
        shutil.rmtree(out, onexc=writable)
    out.mkdir(parents=True)
    shutil.copy2(root / "index.html", out / "index.html")
    (out / ".nojekyll").write_text("")          # serve files as they are (no Jekyll processing)
    for run in sorted(p for p in root.iterdir() if (p / "judge.html").exists()):
        dest = out / run.name
        dest.mkdir()
        for name in ("judge.html", "report.html"):
            if (run / name).exists():
                shutil.copy2(run / name, dest / name)
        if (run / "img").exists():
            shutil.copytree(run / "img", dest / "img")
    return out


def publish(out: str | Path = "data/pages", remote: str = "origin", branch: str = "gh-pages") -> None:
    """Push `out` to `branch` as a single commit that replaces the previous one, so the
    repository's history doesn't grow with every rebuild of the site."""
    import subprocess
    out = Path(out).resolve()
    url = subprocess.run(["git", "remote", "get-url", remote], capture_output=True, text=True, check=True).stdout.strip()

    def git(*a):
        subprocess.run(["git", *a], cwd=out, check=True)
    git("init", "-q", "-b", branch)
    git("add", "-A")
    git("commit", "-q", "-m", "Site build")
    git("push", "-q", "--force", url, f"{branch}:{branch}")
