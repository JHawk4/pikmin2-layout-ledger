"""Build the report site: a landing page over every judged run, and one page per run.

  data/output/index.html               runs table and how lucky each run's layouts were
  data/output/accuracy.html            does the judge predict real times (calibration)
  data/output/pokos.html               pokos per sublevel against the median run
  data/output/seeds.html               seed-order check
  data/output/layouts.html             pick a run's layouts page
  data/output/detection.html           pick a run's seed detection page
  data/output/timesave.html            every run's time per sublevel, raw or beyond the layout
  data/output/<run>/judge.html         layouts and luck for one run (run_page; judge_report for other categories)

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

from . import cavegen, charts, judge2, judge_report, luck, rng, run_page, treasures

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


POKOS_PER_SECOND = 2.0


def median_pokos(values) -> int | None:
    """The median of some poko counts, rounded half up to a whole poko (a median of two runs
    can fall between them, and half a poko is not a thing)."""
    vals = [v for v in values if v is not None]
    return int(np.floor(float(np.median(vals)) + 0.5)) if vals else None     # Pay Off Debt: two extra pokos are worth one second


def timed(entries: list[dict], tre: dict) -> list[tuple[dict, int]]:
    """(entry, frame its time stops) for every sublevel that can be timed: up to the next
    sublevel's entry screen, or for a cave's last sublevel up to the cave's results screen
    ("Treasures Salvaged"), found by the treasure scan. Each sublevel is only compared with
    itself across runs, so the two kinds of end needn't match."""
    out = []
    for k, a in enumerate(entries):
        b = entries[k + 1] if k + 1 < len(entries) else None
        if not a.get("sublevel"):
            continue
        if b is not None and b["cave"] == a["cave"] and b.get("sublevel") == a["sublevel"] + 1:
            out.append((a, b["frame"]))
        elif (b is None or b["cave"] != a["cave"]) and (tre.get(str(a["frame"])) or {}).get("exit"):
            out.append((a, tre[str(a["frame"])]["exit"][0]))
    return out


def actuals(runs: list[dict], slope: float = 1.0) -> list[dict]:
    """Per run: entry frame -> what the runner did on that sublevel, allowing for the layout.

    took: seconds from this entry screen to the next one (same cave), or to the cave's results
    screen for its last sublevel (see timed); pokos from the treasure panels.
    raw = (took - median took) - (pokos - median pokos) / 2 for Pay Off Debt, plain time
    otherwise: against the median run on this site.

    The runs here are personal bests, which drew lucky layouts more often than chance, so the
    median run had a better than median layout (on SH 6 about 30 s better). raw would count
    that layout as the runner's doing. expected = slope * (this layout's luck - the median run's
    layout luck) is what the layout alone should change against the median run, and
    net = raw - expected is the runner's own part. Negative = faster."""
    plays: dict[str, list[tuple[int, str, float, int | None, float | None]]] = {}
    for i, r in enumerate(runs):
        tre = treasures.load(r["dir"])
        e = r["entries"]
        for a, end in timed(e, tre):
            if r["kind"] == "pod" and not judge_report.trusted(a):
                continue      # pokos are read against the seed's treasures: no trusted seed, no net time
            t = tre.get(str(a["frame"]))
            d = luck.delta(a) if luck.judged(a) and judge_report.trusted(a) else None
            plays.setdefault(f'{a["cave"]} {a["sublevel"]}', []).append(
                (i, str(a["frame"]), (end - a["frame"]) / r["fps"], treasures.reliable_pokos(t), d))
    out: list[dict] = [{} for _ in runs]
    for sub, ps in plays.items():
        if len(ps) < 2:
            continue
        med_t = float(np.median([p[2] for p in ps]))
        pk = [p[3] for p in ps if p[3] is not None]
        med_p = median_pokos(pk)
        ds = [p[4] for p in ps if p[4] is not None]
        med_d = float(np.median(ds)) if ds else None
        for i, frame, took, pokos, d in ps:
            raw = took - med_t
            if runs[i]["kind"] == "pod" and pokos is not None and med_p is not None:
                raw -= (pokos - med_p) / POKOS_PER_SECOND
            expected = slope * (d - med_d) if d is not None and med_d is not None else 0.0
            out[i][frame] = {"net": raw - expected, "raw": raw, "expected": expected, "took": took,
                             "median_took": med_t, "pokos": pokos, "median_pokos": med_p,
                             "median_luck": med_d, "n": len(ps)}
    return out


def _layout_url(run: dict, entry: dict) -> str | None:
    """The run's rendered layout for this entry, as a path relative to index.html (loaded only on hover)."""
    name = f"layout_{entry['frame']}_{entry['cave']}-{entry['sublevel']}.png"
    return f"{run['slug']}/img/{name}" if (run["dir"] / "img" / name).exists() else None


def _treasure_names(t) -> str:
    picks = [c for c in (t or {}).get("collected", []) if c]
    return ", ".join(f"{n.replace('_', ' ')} ({p})" for n, p in picks)


def calibration(runs: list[dict], key: str = "judge", drop: set | None = None, flag: set | None = None) -> dict:
    """Judge estimate vs measured sublevel outcome, with sublevel and runner fixed effects.

    For Pay Off Debt the outcome is net time: seconds taken minus pokos collected / 2, so a
    runner who stops for an extra treasure is credited for its pokos. For other categories
    it is plain time, and plays that took a different number of treasures than most runs
    of the sublevel are left out instead.

    `key`: "judge" (CaveGen's) or "judge2" (judge2/, the refit PoD judge). `drop`: (run index,
    sublevel) plays to leave out; `flag`: plays to mark as unusual in the chart."""
    order = {c: k for k, c in enumerate(STORY_ORDER)}
    drop = drop or set()
    rows = []
    for i, r in enumerate(runs):
        tre = treasures.load(r["dir"])
        e = r["entries"]
        net = r["kind"] == "pod"
        for a, end in timed(e, tre):
            if (a.get(f"{key}_score") is not None and not a.get(f"{key}_fixed") and judge_report.trusted(a)
                    and (i, f'{a["cave"]} {a["sublevel"]}') not in drop):
                ref = cavegen.reference_scores(a["cave"], a["sublevel"], r["kind"])
                t = tre.get(str(a["frame"]))
                took = (end - a["frame"]) / r["fps"]
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
                    "creatures": t.get("creature_cap") if t else None,
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
                    median_pokos(pk))

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

    pts = [(row["x"], row["y"], tip(row), row["link"], row["img"],
            {"run": row["runner"], "runner": row["runner"].split(" ")[0], "flag": (row["run"], row["sub"]) in (flag or set())})
           for row in rows]
    e = yr - xr                                  # what a perfectly calibrated judge leaves unexplained
    r2 = float(1 - (e @ e) / (yr @ yr)) if yr @ yr > 0 else 0.0
    for row, ek in zip(rows, e):
        row["e"] = float(ek)
    return {"n": len(rows), "sublevels": len(subs), "slope": slope, "se": se, "corr": corr, "points": pts,
            "rows": rows, "excluded": excluded, "tip": tip, "net": any_net, "time_only": time_only, "r2": r2,
            "key": key}


OUTLIER_Z = 4.0          # robust z-score (median absolute deviation) of the unexplained seconds


def outliers(cals: list[dict]) -> dict:
    """(run, sublevel) -> row for plays far off under every judge given: more than OUTLIER_Z robust
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


SORTS = [   # (key, title, sort key, how, label of a play's sort value for the x axis)
    ("prediction", "Sorted by predicted time saved", lambda r: r["x"], "low to high", lambda r: f"{r['x']:+.0f} s"),
    ("size", "Sorted by size of the prediction", lambda r: abs(r["x"]), "small to large swings", lambda r: f"{abs(r['x']):.0f} s"),
    ("spread", "Sorted by how variable the sublevel is", lambda r: r["spread"], "5th–95th spread, low to high",
     lambda r: f"{r['spread']:.0f} s"),
    ("length", "Sorted by sublevel length", lambda r: r["median"] or 0, "median judge time, short to long",
     lambda r: f"{r['median'] or 0:.0f} s"),
    ("creatures", "Sorted by creature pokos on offer", lambda r: r.get("creatures") or 0,
     "most pokos the layout's creatures can give, low to high", lambda r: f"{r.get('creatures') or 0} pk"),
    ("order", "Sorted by game order", lambda r: r["order"], "cave and sublevel", lambda r: r["sub"]),
    ("runner", "Sorted by runner", lambda r: (r["run"], r["order"]), "one runner after another",
     lambda r: r["runner"].split()[0]),
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
    bends = []
    for key, title, fn, how, lab in SORTS:
        c = cumulative(cal["rows"], cal["slope"], fn)
        # short tooltips: seven charts of every play would otherwise weigh megabytes
        pts = [(sxx, sxy, f"{r['sub']} · {r['runner']}\npredicted {r['x']:+.1f} s, actual {r['y']:+.1f} s · {lab(r)}",
                r["link"], lab(r))
               for sxx, sxy, r in c["points"]]
        if c["p"] < 0.05:
            bends.append(title)
        verdict = ("<b>significant bend</b>" if c["p"] < 0.01 else "possible bend" if c["p"] < 0.05
                   else "no significant bend")
        where = "" if c["p"] >= 0.05 else f", largest around {html.escape(c['worst']['sub'])} ({html.escape(c['worst']['runner'])})"
        curves.append(charts.cumulative_chart(pts, c["band"], cal["slope"], title,
                                              f"{how} · max deviation {c['stat']:.2f}, p = {c['p']:.2f}"))
        findings.append(f"<li>{html.escape(title)}: {verdict} (p = {c['p']:.3f}){where}</li>")
    plain = ("No sign that the judge is better or worse for any cave, runner or layout size."
             if not bends else "The judge may be off by a different amount in places: " + "; ".join(bends).lower() + ".")
    section = f'''<h3 id="consistency">Is the judge equally right everywhere?</h3>
<p>{plain}</p>
<details><summary>Show the checks</summary>
<p>Each chart walks through the same plays in a different order, adding up prediction² along the bottom and
prediction × actual up the side, so the slope of the walk so far is the regression slope over those plays. If the
judge is off by the same proportion everywhere, the walk follows the dashed line and stays inside the grey 95% band.
A bend that leaves the band shows where the slope differs: for example, a steeper end in "size" would mean big
predicted swings are more reliable than small ones. The test allows each play its own noise level. Under each chart
are the sort's values; drag across a chart to see the slope of just that stretch.</p>
<ul class="findings">{"".join(findings)}</ul>
<div class="curves">{"".join(curves)}</div></details>'''
    return ex_table, section


ADD_RUN_NOTE = ('<p class="muted">Missing a run, or want one added? Share its video or speedrun.com link in the '
                '<a href="suggest.html">suggestion box</a>.</p>')


def _pct(p: dict) -> str:
    return "" if p["pct"] is None else f'{p["pct"]:.0f}%'


def picker(picks: list[dict], what: str) -> str:
    """A landing page that lists the runs, each linking to its layouts or detection page."""
    layouts = what == "layouts"
    href = "judge.html" if layouts else "report.html"
    trs = []
    for p in picks:
        rank = "former WR" if p["wr"] else p["rank"]
        extra = ((f'<td class="num">{judge_report._num(p["luck"])}</td>'
                  f'<td class="num">{_pct(p)}</td>'
                  f'<td class="num">{judge_report._num(p["runner"])}</td>') if layouts else
                 f'<td class="num{" weak" if p["high"] < 0.9 * p["n"] else ""}">{p["high"]} of {p["n"]}</td>')
        trs.append(f'<tr><td class="num">{html.escape(rank)}</td>'
                   f'<td class="sticky"><a href="{html.escape(p["slug"])}/{href}"><b>{html.escape(p["player"])}</b></a></td>'
                   f'<td>{_fmt_time(p["time"])}</td>{extra}<td>{html.escape(p["date"])}</td></tr>')
    if layouts:
        title, intro = "Layouts", ("Pick a run to see every layout it got: how lucky each one was against 1000 random layouts "
                                   "of the same sublevel, what the runner did with it, and the pictures.")
        cols = ('<th class="num">Layout luck</th><th class="num">Luck percentile</th>'
                '<th class="num">Runner vs field</th>')
    else:
        title, intro = "Seed detection", ("Pick a run to see how each sublevel's seed was read from the falling title "
                                          "letters, how sure the reading is, and the pictures behind it.")
        cols = '<th class="num">Seeds read</th>'
    return f'''
<h1>{title}</h1>
<p class="intro">{intro}</p>
<div class="tablewrap"><table>
<thead><tr><th class="num">Rank</th><th class="sticky">Runner</th><th>Time</th>{cols}<th>Date</th></tr></thead>
<tbody>{"".join(trs)}</tbody></table></div>
{ADD_RUN_NOTE}
'''


def timesave_page(runs: list[dict], acts: list[dict]) -> str:
    """Every Pay Off Debt run against the median run, per sublevel: raw, or beyond what the layout gave."""
    order = {c: k for k, c in enumerate(STORY_ORDER)}
    per_run = {}
    for i, r in enumerate(runs):
        if r["kind"] != "pod" or not acts[i]:
            continue
        entries = {str(e["frame"]): e for e in r["entries"]}
        vals = {}
        for frame, a in acts[i].items():
            e = entries.get(frame, {})
            vals[f'{e.get("cave")} {e.get("sublevel")}'] = (a, e)
        per_run[i] = vals
    if not per_run:
        return ""
    cats = sorted({c for v in per_run.values() for c in v}, key=lambda c: (order.get(c.split()[0], 99), int(c.split()[1])))
    # keep the usual route: sublevels most runs played
    cats = [c for c in cats if sum(c in v for v in per_run.values()) >= len(per_run) / 2]
    allv = [abs(a[k]) for v in per_run.values() for c in cats if c in v for a in (v[c][0],) for k in ("raw", "net")]
    big = float(np.percentile(allv, 95)) if allv else 1.0

    def cell(a, e, k, sub, runner):
        val = a[k]
        tip = (f"{sub} · {runner} · {e.get('time', '')}\n"
               f"took {a['took']:.1f} s (median run {a['median_took']:.1f} s)"
               + (f"\n{a['pokos']} pokos (median run {a['median_pokos']:g})" if a.get("pokos") is not None and a.get("median_pokos") is not None else "")
               + f"\nvs the median run: {a['raw']:+.1f} s net of pokos"
               + (f"\nlayout vs the median run's: {a['expected']:+.1f} s by the judge" if a.get("expected") else "")
               + f"\nbeyond the layout: {a['net']:+.1f} s")
        mark = "--good-mark" if val < 0 else "--bad-mark"
        pct = 0 if abs(val) < 0.5 else 15 + 55 * min(1.0, abs(val) / (big or 1))
        text = f"{val:+.0f}"
        if e.get("link"):
            text = f"<a href='{html.escape(e['link'])}' target='_blank' rel='noopener'>{text}</a>"
        return (f"<td class='num heat' tabindex='0' style='background:color-mix(in srgb, var({mark}) {pct:.0f}%, transparent)' "
                f"data-tip='{html.escape(tip)}'>{text}</td>")

    tables = []
    for k, label in (("net", "beyond the layout"), ("raw", "vs the median run")):
        head = "".join(f"<th class='num'>{html.escape(c)}</th>" for c in cats)
        trs = []
        for i, v in sorted(per_run.items(), key=lambda kv: sum(a[k] for a, _ in kv[1].values() if a)):
            cells = [cell(*v[c], k, c, runs[i]["runner"]) if c in v else "<td class='num muted' title='not timed'>–</td>"
                     for c in cats]
            tot = sum(v[c][0][k] for c in cats if c in v)
            tone = "good" if tot < 0 else "bad" if tot > 0 else "mid"
            trs.append(f"<tr><td><a href='{html.escape(runs[i]['slug'])}/judge.html'>{html.escape(runs[i]['runner'])}</a></td>"
                       f"<td class='num {tone}-text'><b>{tot:+.0f}</b></td>{''.join(cells)}</tr>")
        tables.append(f"<div class='tablewrap ts' data-kind='{k}'{'' if k == 'net' else ' hidden'}><table class='heatgrid'>"
                      f"<thead><tr><th>Run</th><th class='num'>Total</th>{head}</tr></thead>"
                      f"<tbody>{''.join(trs)}</tbody></table></div>")
    return f'''
<h1>Time saved by sublevel</h1>
<p>Seconds each run gained or lost on each sublevel against the median run on this site, counting 2 pokos as 1 second.
Negative (green) is faster. Hover a cell for the details; click it to open the video there.</p>
<fieldset class="ts-pick"><legend class="muted">Show</legend>
<label><input type="radio" name="ts" value="net" checked> <b>The runner beyond the layout</b>: the judge's difference between
this layout and the median run's is taken out, so it shows execution, not luck</label>
<label><input type="radio" name="ts" value="raw"> <b>Against the median run</b>: the plain difference, layout luck included</label>
</fieldset>
{"".join(tables)}
<p class="muted small">Runs are sorted by their total, fastest first. Only the usual route's sublevels are shown; – = not
timed (an uncertain seed, or the last sublevel's results screen was not found).</p>
{ADD_RUN_NOTE}
'''


TIMESAVE_JS = """
document.querySelectorAll('input[name=ts]').forEach(i => i.addEventListener('change', () => {
  document.querySelectorAll('.ts').forEach(t => { t.hidden = t.dataset.kind !== i.value; }); }));
"""


ODD_POKOS = 150      # a difference from the median run this large is flagged in the pokos grid


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
    median = {c: median_pokos([v[c][0] for v in per_run.values() if c in v]) for c in cats}
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
                cells.append("<td class='num muted' title='not read'>–</td>")
                continue
            p, tip, href = v[c]
            d = p - median[c]
            if d == 0:
                cells.append(f"<td class='num muted' data-tip='{html.escape(chr(10).join([f'{p} pokos (the median)', tip.split(chr(10), 1)[1]]))}'>0</td>")
                continue
            odd = abs(d) > ODD_POKOS
            mark = "--good-mark" if d > 0 else "--bad-mark"
            pct = 18 + 52 * min(1.0, abs(d) / big)
            text = f"{d:+g}" + ("<sup title='unusually large: check the video'>?</sup>" if odd else "")
            if href:
                text = f"<a href='{html.escape(href)}' target='_blank' rel='noopener'>{text}</a>"
            tipx = (f"{d:+g} pokos vs the median ({p} vs {median[c]:g})" + chr(10) + tip.split(chr(10), 1)[1]
                    + (chr(10) + "Unusually large: a skipped or extra treasure, or a misread; check the video." if odd else ""))
            cells.append(f"<td class='num heat' tabindex='0' style='background:color-mix(in srgb, var({mark}) {pct:.0f}%, transparent)' "
                         f"data-tip='{html.escape(tipx)}'>{text}</td>")
        tot = sum(v[c][0] - median[c] for c in v)
        tone = "good" if tot > 0 else "bad" if tot < 0 else "mid"
        rows.append(f"<tr><td>{html.escape(runs[i]['runner'])}</td><td class='num {tone}-text'><b>{tot:+g}</b></td>{''.join(cells)}</tr>")
    hidden = (f" {same} other sublevel{'s' if same != 1 else ''}, where every run got the median, "
              f"{'are' if same != 1 else 'is'} left out.") if same else ""
    return f'''<h2 id="pokos">Pokos by sublevel</h2>
<p>Pokos per sublevel against the median run (the median is under each sublevel's name). Green = more, red = fewer,
– = not read, ? = an unusually large difference worth checking. Hover a cell for the treasures; click it to open the video.</p>
<details><summary>How the pokos are counted</summary><p class="muted small">Each row is a run, each column a sublevel where at
least one run differs from the median.{hidden} Each treasure collected shows a panel with its value;
the panels are counted in the video and matched to the treasures CaveGen places on that layout. Each panel also shows
the run's running Total, so pokos from creatures are whatever the Total rose by beyond the treasure; they are shared
among the cave sublevels between the two panels by time spent in each (never the surface, and treasures picked up on
the surface count toward no sublevel).</p></details>
<div class="tablewrap viz-root"><table class="heatgrid">
<thead><tr><th>Run</th><th class='num'>Total vs median</th>{head}</tr></thead><tbody>{"".join(rows)}</tbody>
</table></div>'''


def _missing_note(manifest: Path = Path("data/videos/manifest.json")) -> str:
    """Runs on the leaderboard whose video could not be downloaded (gaps in the Rank column)."""
    try:
        m = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ""
    recs = [v for d in m.values() if isinstance(d, dict) for v in d.values() if isinstance(v, dict)]
    gone = sorted((v["run"] for v in recs if v.get("status") == "error" and v.get("run")),
                  key=lambda r: (r.get("series") == "wr", r.get("place") or 99, r.get("date", "")))
    if not gone:
        return ""
    items = ", ".join(f'{html.escape(_run_label(r, "?"))}'
                      + (f' (rank {r["place"]})' if r.get("place") and r.get("series") != "wr" else " (former WR)")
                      for r in gone)
    return (f'<p class="muted small">Not here: {items}. Their videos could not be downloaded '
            f'(deleted, private, or not available).</p>')


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
    key0 = "judge2" if any(x.get("judge2_score") is not None for r in runs for x in r["entries"]) else "judge"
    acts = actuals(runs, slope=calibration(runs, key0).get("slope", 1.0))
    for r, a in zip(runs, acts):
        if r["kind"] == "pod":
            run_page.write(r["dir"], actual=a)
        else:
            judge_report.write_page(r["dir"], home="../index.html", actual=a)
        for old in ("judge_a.html", "judge_b.html", "judge_c.html"):      # the retired drafts
            (r["dir"] / old).unlink(missing_ok=True)

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

    # judge2 (CaveGen's judge refit on these runs) is the site's judge; CaveGen's own only if judge2 is missing
    keys = ["judge2"] if any(x.get("judge2_score") is not None for r in runs for x in r["entries"]) else ["judge"]
    first = [calibration(runs, k) for k in keys]
    out = outliers(first)
    not_shared: set = set()
    # unusual plays stay in: many are real choices (a skipped treasure); they are marked in the
    # chart, and the table also gives the fit without them
    cals = {k: calibration(runs, k, drop=not_shared, flag=set(out)) for k in keys}
    trims = {k: calibration(runs, k, drop=set(out) | not_shared) for k in keys}
    cal = cals[keys[0]]
    names = {"judge": "CaveGen's judge", "judge2": "The judge"}
    if cal.get("points"):
        outcome = ("run: net seconds vs other runs (time − pokos ÷ 2; negative = faster)" if cal["net"]
                   else "run: seconds vs other runs (negative = faster)")
        charts_html = []
        for k, c in cals.items():
            if not c.get("points"):
                continue
            charts_html.append(charts.scatter_chart(
                c["points"], "Predicted vs actual, one dot per sublevel play",
                "judge: seconds vs the other runs' layouts (negative = faster layout)",
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
            + (f"<tr class='muted'><td>&nbsp;&nbsp;without the {len(out)} unusual plays</td><td class='num'>{trims[k]['n']}</td>"
               f"<td class='num'>{trims[k]['slope']:.2f} ({trims[k]['slope'] - 1.96 * trims[k]['se']:.2f}–{trims[k]['slope'] + 1.96 * trims[k]['se']:.2f})</td>"
               f"<td class='num'>{trims[k]['corr']:.2f}</td><td class='num'>{trims[k]['r2']:.2f}</td></tr>" if out and trims[k].get("points") else "")
            for k, c in cals.items() if c.get("points"))
        out_rows = "".join(
            f"<tr><td>{html.escape(row['sub'])}</td><td>{html.escape(row['runner'])}</td>"
            f"<td>{_link(row['link'], row['time'] or 'video')}</td><td class='num'>{row['y']:+.1f} s</td></tr>"
            for row in sorted(out.values(), key=lambda r: -abs(r["y"])))
        def plain(k, c):
            pct = round(abs(c["slope"] - 1) * 100)
            if pct < 8:
                return (f"{names[k]} is right on average: a layout it calls 10 s faster really is about 10 s faster. "
                        f"It explains about {c['r2'] * 100:.0f}% of the differences between runs on the same sublevel; "
                        f"the rest is the runners")
            return (f"{names[k]} {'overstates' if c['slope'] < 1 else 'understates'} the differences between layouts "
                    f"by about {pct}% (a layout it calls 10 s faster is about {10 * c['slope']:.0f} s faster)")
        lead = "<p class='lead'>" + "; ".join(plain(k, c) for k, c in cals.items() if c.get("points")) + ".</p>"
        cal_text = lead + (f"<p>Over <b>{cal['n']}</b> sublevel plays ({cal['sublevels']} sublevels seen in at least two runs), "
                    f"each second the judge predicts should be worth one second of {'net' if cal['net'] else 'real'} time.</p>"
                    f"<details><summary>The numbers</summary>"
                    f"<p class='muted small'>The slope is what a predicted second is actually worth (1 = calibrated, below 1 = the "
                    f"judge overstates differences between layouts); R² is the share of the runs' differences the judge explains "
                    f"taking its seconds at face value. The judge is CaveGen's Pay Off Debt judge refit on these runs: no credit for "
                    f"pokos from enemies or for treasures runners don't collect, a choice of which treasures to skip, and re-weighted "
                    f"walking, carrying, enemy and gate times. CaveGen's original judge had slope 0.79 here (it overstated layout "
                    f"differences by about a fifth) and R² 0.37.</p>"
                    f"<div class='tablewrap'><table><thead><tr><th>Judge</th><th class='num'>Plays</th><th class='num'>Slope (95%)</th>"
                    f"<th class='num'>Correlation</th><th class='num'>R² (slope 1)</th></tr></thead><tbody>{cmp_rows}</tbody></table></div>"
                    + (f"<p class='muted small'>The outcome is <b>net time</b>: seconds minus pokos ÷ 2. On plain time the judge would "
                       f"have slope {cal['time_only'][0]:.2f} (correlation {cal['time_only'][2]:.2f}).</p>" if cal["net"] else "")
                    + "</details>"
                    + (f"<details><summary>{len(out)} unusual play{'s' if len(out) != 1 else ''} (ringed in the charts)</summary>"
                       f"<p class='muted small'>More than {OUTLIER_Z:g} robust standard deviations off what the judge predicts: no layout "
                       f"judge explains them. Many are real choices (a skipped treasure); some are mistakes (a death, a misplay). "
                       f"They are kept in the fit; the table above also gives it without them.</p>"
                       f"<div class='tablewrap'><table><thead><tr><th>Sublevel</th><th>Runner</th><th>Video</th>"
                       f"<th class='num'>Run vs others</th></tr></thead><tbody>{out_rows}</tbody></table></div></details>" if out else ""))
    else:
        cal_chart, cal_text = "", "<p class='muted'>Not enough runs share sublevels to check calibration.</p>"

    ex_table, curve_html = _calibration_extras(cal)
    pokos_html = pokos_section(runs)

    # layout luck: each run's total against random runs over the same sublevels
    lucks = []
    for r in runs:
        jd = [x for x in r["entries"] if x.get("cave") and luck.judged(x) and judge_report.trusted(x)]
        tot = sum(luck.delta(x) for x in jd)
        pct = luck.percentile(tot, luck.simulate(jd, r["kind"])) if jd else None
        lucks.append((jd, tot, pct))
    # the landing chart: random runs over every judged sublevel, one mark per run
    every: dict = {}
    seen_in: dict = {}
    for r, (jd, tot, pct) in zip(runs, lucks):
        for x in jd:
            every.setdefault((x["cave"], x["sublevel"]), x)
            seen_in[(x["cave"], x["sublevel"])] = seen_in.get((x["cave"], x["sublevel"]), 0) + 1
    # the usual route: sublevels most runs play (an old route's extra caves would make every run look incomplete)
    every = {k: x for k, x in every.items() if seen_in[k] * 2 >= len(runs)}
    luck_chart = ""
    if every:
        full = luck.simulate(list(every.values()))
        def full_route(jd):
            return {(x["cave"], x["sublevel"]) for x in jd} >= set(every)
        marks = [{"x": tot, "hollow": not full_route(jd), "href": f'{r["slug"]}/judge.html',
                  "tip": f'{r["runner"]}\nlayouts {tot:+.1f} s over {len(jd)} sublevels\n{luck.describe(pct)}'
                         + (f"\n(hollow: not the usual {len(every)} sublevels, so its percentile compares it with "
                            f"random runs over its own {len(jd)})" if not full_route(jd) else "")}
                 for r, (jd, tot, pct) in zip(runs, lucks) if jd]
        luck_chart = charts.distribution_chart(
            full.tolist(), marks, "How lucky was each run? Every run against 20,000 random runs",
            "total seconds the layouts should save against median layouts (negative = luckier)",
            subtitle=f"grey: random runs, one random layout of each of the {len(every)} sublevels with layout luck · "
                     f"dots: the runs on this site (hollow = some sublevels not read, or another route)")

    trs, picks = [], []
    for r, (judged, judge2_total, pct) in zip(runs, lucks):
        e = [x for x in r["entries"] if x.get("cave")]
        act = acts[runs.index(r)]
        run_total = sum(v["net"] for v in act.values()) if act else None
        high = sum(1 for x in e if x.get("confidence") == "high")
        link = r["run"].get("weblink")
        wr = r["run"].get("series") == "wr"
        rank = "" if wr else str(r["run"].get("place", ""))

        def sv(x):
            return "" if x is None else f"{x:.3f}"
        picks.append({"rank": rank, "wr": wr, "player": r["player"], "slug": r["slug"], "time": r["run"].get("time_seconds"),
                      "date": r["run"].get("date", ""), "luck": judge2_total if judged else None, "pct": pct,
                      "runner": run_total, "high": high, "n": len(e)})
        trs.append(f'<tr><td class="num" data-v="{html.escape(rank or "99")}">{html.escape(rank)}</td>'
                   f'<td class="sticky"><a href="{html.escape(r["slug"])}/judge.html">{html.escape(r["player"])}</a>'
                   f'{" <span class=badge>former WR</span>" if wr else ""}</td>'
                   f'<td data-v="{r["run"].get("time_seconds") or 0}">{_fmt_time(r["run"].get("time_seconds"))}</td>'
                   f'<td class="num" data-v="{sv(judge2_total if judged else None)}">{judge_report._num(judge2_total if judged else None)}</td>'
                   f'<td class="num" data-v="{sv(pct)}">{"" if pct is None else f"{pct:.0f}%"}</td>'
                   f'<td class="num" data-v="{sv(run_total)}">{judge_report._num(run_total)}</td>'
                   f'<td class="num{" weak" if high < 0.9 * len(e) else ""}" data-v="{high / max(1, len(e)):.3f}">{high} of {len(e)}</td>'
                   f'<td>{html.escape(r["run"].get("date", ""))}</td>'
                   f'<td><a href="{html.escape(r["slug"])}/report.html">detection</a>'
                   f'{f" · <a href={chr(34)}{html.escape(link)}{chr(34)} target=_blank rel=noopener>speedrun.com</a>" if link else ""}</td></tr>')

    data_rows = "".join(f"<tr><td>{html.escape(a)}</td><td>{html.escape(b)}</td><td>{html.escape(c)}</td>"
                        f"<td><code>{html.escape(d)}</code></td><td class='num'>{s:,}</td></tr>"
                        for a, b, c, d, s in table_rows)
    head = f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>@TITLE@</title>
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
.lead {{ font-size:16px; }} .intro {{ max-width:820px; }} .legend-list {{ margin:6px 0 14px; padding-left:18px; max-width:820px; }}
.badge {{ font-size:11px; font-weight:700; color:var(--sun); border:1px solid var(--sun); border-radius:999px; padding:0 6px; margin-left:4px; }}
th[data-sort] {{ cursor:pointer; user-select:none; }} th[data-sort]:hover {{ color:var(--fg); }}
th[aria-sort="ascending"]::after {{ content:" ▲"; }} th[aria-sort="descending"]::after {{ content:" ▼"; }}
td.weak {{ color:var(--bad); }}
.ts-pick {{ border:1px solid var(--line); border-radius:10px; background:var(--card); padding:8px 12px; margin:0 0 12px;
  display:flex; flex-direction:column; gap:4px; max-width:820px; }}
.ts-pick label {{ cursor:pointer; }} .small {{ font-size:13px; }}
@media (max-width:640px) {{ td.sticky, th.sticky {{ position:sticky; left:0; background:var(--card); z-index:1; }} }}
{charts.CSS}
</style></head><body><main>'''
    tail = f'''</main>
<script>{charts.TOOLTIP_JS}</script>
@SCRIPTS@
</body></html>'''
    index = f'''
<h1>How lucky were the layouts?</h1>
<p class="intro">Every cave sublevel's layout is set by the game's random number generator. This site reads that seed from
the falling title letters in each Pay Off Debt run's video, rebuilds the exact layout, and asks how lucky the layouts were
and how much time the runner actually saved.</p>
<ul class="legend-list muted">
<li><b>Layout luck</b>: seconds the run's layouts should save against the median layout of the same sublevels, by
CaveGen's layout judge re-tuned on these runs' real times. <b>Luck percentile</b>: how many random runs it beats.</li>
<li><b>Runner vs field</b>: seconds the runner saved against the median run on the same sublevels, after allowing for
the layouts (so a bad layout is not counted against the runner), counting every 2 pokos as 1 second.</li>
<li>Negative is faster, as on splits. <b>Seeds read</b> is how many sublevels' seeds were read with confidence; only those count.
Click a column to sort; open a runner for their layouts.</li>
</ul>

<div class="tablewrap"><table id="runs">
<thead><tr><th class="num" data-sort>Rank</th><th class="sticky" data-sort>Runner</th><th data-sort>Time</th>
<th class="num" data-sort title="Seconds the layouts should save vs median layouts">Layout luck</th>
<th class="num" data-sort title="Share of random runs over the same sublevels this run's layouts beat">Luck percentile</th>
<th class="num" data-sort title="Seconds saved vs the median run on the same layout luck, time minus pokos ÷ 2">Runner vs field (net)</th>
<th class="num" data-sort title="Sublevels whose seed was read with confidence">Seeds read</th>
<th data-sort>Date</th><th>Pages</th></tr></thead>
<tbody>{"".join(trs)}</tbody></table></div>
{_missing_note()}
{ADD_RUN_NOTE}
<script>
(() => {{
  const t = document.getElementById('runs'), body = t.tBodies[0];
  t.querySelectorAll('th[data-sort]').forEach(th => {{ th.tabIndex = 0; th.setAttribute('role', 'button');
    th.addEventListener('keydown', e => {{ if (e.key === 'Enter' || e.key === ' ') {{ e.preventDefault(); th.click(); }} }}); }});
  t.querySelectorAll('th[data-sort]').forEach((th, i) => th.addEventListener('click', () => {{
    const col = [...th.parentNode.children].indexOf(th), up = th.getAttribute('aria-sort') !== 'ascending';
    t.querySelectorAll('th').forEach(x => x.removeAttribute('aria-sort'));
    th.setAttribute('aria-sort', up ? 'ascending' : 'descending');
    const key = r => {{ const c = r.children[col]; const v = c.dataset.v ?? c.textContent.trim();
      return v === '' ? NaN : (isNaN(+v) ? v : +v); }};
    [...body.rows].sort((a, b) => {{ const x = key(a), y = key(b);
      if (typeof x === 'number' && typeof y === 'number') return (isNaN(x) - isNaN(y)) || (up ? x - y : y - x);
      return up ? String(x).localeCompare(String(y)) : String(y).localeCompare(String(x)); }})
      .forEach(r => body.appendChild(r));
  }}));
}})();
</script>
<h2 id="luck">The runs' luck</h2>
<p>Each dot is a run's layout luck; the grey curve is how luck falls for random runs, so a dot far left of the curve's
middle was a lucky run. Hover a dot for the run; click it for its layouts.</p>
{luck_chart}
'''
    accuracy = f'''
<h1 id="calibration">Does the judge predict real times?</h1>
<p>Each sublevel's real time is measured from the video: from its entry screen to the next sublevel's entry screen
(a cave's last sublevel runs to the cave's results screen). Both the judge's estimate and the real time are compared within the same
sublevel across runs, after removing each runner's overall pace. For Pay Off Debt the outcome counts pokos too, at
two pokos per second; for other categories, plays where the runner collected a different number of treasures than
most runs of that sublevel are left out. Only seeds read at high confidence are used: a misread seed is a wrong
layout, so its judge score would be noise. Hover a point for its seed and pokos; click it to open the video there.</p>
{cal_text}
{cal_chart}
{ex_table}
{curve_html}
'''
    seeds = f'''
<h1 id="seed-order">Seed order</h1>
<p>A check on the seed reading: each seed's position in the game's random number sequence, counted from the run's first
seed. The RNG only moves forward, so every line should climb steadily; a point off its line marks a doubtful seed.</p>
<details><summary>Show the chart and the table</summary>
{order_chart}
<div class="tablewrap"><table>
<thead><tr><th>Runner</th><th>Video time</th><th>Sublevel</th><th>Letter seed</th><th class="num">RNG steps</th></tr></thead>
<tbody>{data_rows}</tbody></table></div></details>
'''
    from . import theme
    pages = [("index.html", "runs", "Pikmin 2 Layout Ledger · layout luck in Pikmin 2 Pay Off Debt runs", index, ""),
             ("layouts.html", "layouts", "Pikmin 2 Layout Ledger · layouts by run", picker(picks, "layouts"), ""),
             ("detection.html", "detection", "Pikmin 2 Layout Ledger · seed detection by run", picker(picks, "detection"), ""),
             ("timesave.html", "timesave", "Pikmin 2 Layout Ledger · time saved by sublevel", timesave_page(runs, acts),
              f"<script>{TIMESAVE_JS}</script>"),
             ("accuracy.html", "accuracy", "Pikmin 2 Layout Ledger · does the judge predict real times?", accuracy,
              f"<script>{charts.BRUSH_JS}</script><script>{charts.SCATTER_JS}</script>"),
             ("pokos.html", "pokos", "Pikmin 2 Layout Ledger · pokos by sublevel", pokos_html.replace('<h2 id="pokos">', '<h1 id="pokos">', 1)
              .replace("Pokos by sublevel</h2>", "Pokos by sublevel</h1>", 1), ""),
             ("seeds.html", "seeds", "Pikmin 2 Layout Ledger · seed order check", seeds, "")]
    for name, active, title, body, scripts in pages:
        page = head.replace("@TITLE@", html.escape(title)) + body + tail.replace("@SCRIPTS@", scripts)
        (root / name).write_text(theme.apply(page, prefix="", active=active), encoding="utf-8")
    dest = root / "index.html"
    (root / "suggest.html").write_text(theme.apply(theme.suggest_page(), prefix="", active="suggest"), encoding="utf-8")
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
    for name in ("index.html", "layouts.html", "detection.html", "timesave.html", "accuracy.html", "pokos.html",
                 "seeds.html", "suggest.html"):
        if (root / name).exists():
            shutil.copy2(root / name, out / name)
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
