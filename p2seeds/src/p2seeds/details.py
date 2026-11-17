"""A run's detection page with what the detector saw, for checking it by eye.

Per sublevel: the falling letters with the tracker's boxes and the fitted fall, the two views of
the floor in the video (the comedown, the high view behind the title as the pod comes down, and
the landing view once it has landed), the layout with those views outlined, and a plain
reading of the score. Built from seeds.json and the
video; detection itself is not redone, and pictures already made are kept.
"""

from __future__ import annotations

import html
import json
from pathlib import Path

import cv2
import numpy as np

SCORE_HELP = """<details class="help"><summary>How to read a detection</summary>
<p>Each sublevel's entry screen drops the cave name's letters with starting speeds drawn from the game's random
number generator. The detector tracks every letter's fall (the boxes in the pictures: green = used in the fit,
orange = matched but not used, for example while bouncing; red ticks = where the fitted fall puts the letter),
fits one starting speed per letter, then finds the generator state that produces those speeds.</p>
<ul>
<li><b>Letters</b>: how many letters had a clean enough fall to measure. Each letter narrows the seed down about
50-fold, so 10 or more letters pin it down on their own.</li>
<li><b>Fit</b>: the typical distance in pixels between a tracked letter and its fitted fall. Below about 0.2 px is a
clean capture; above about 0.5 px something is off (a dropped frame, blur, a mistracked letter).</li>
<li><b>Score</b>: how far the best seed's letter speeds are from the measured ones, in units of each letter's own
measurement error, squared and summed over the letters (each letter's share capped, so one bad letter can't
dominate) after removing a shared speed offset. Lower is better; about 1 per letter is a perfect match.</li>
<li><b>Next</b>: the same score for the second-best seed. A big gap between the two means nothing else comes close.</li>
<li><b>Confidence</b>: <i>high</i> needs 10+ letters, under 4 per letter and a gap of 30+; <i>medium</i> needs 7+,
under 6 and a gap of 15+. A seed can also be confirmed by its neighbours: consecutive sublevels' seeds sit a few
hundred thousand steps apart in the generator, which almost never happens by chance.</li>
</ul>
<p>Two pictures from the video show the floor as the sublevel starts: the <b>comedown</b>, the high, wide view behind
the title while the pod comes down (often dim, so it is brightened), and the <b>landing view</b>, the first view once
the pod has landed. The layout, drawn by CaveGen3, outlines both on the floor: the comedown in blue (the game holds
this one still shot, nearly straight down, while the title is up) and the landing view in yellow, with an arrow for
the way the pod faces, so the pictures and the layout should match.</p></details>"""


def explain(row: dict) -> str:
    """One plain sentence about why a detection got its confidence."""
    n, rms = row.get("letters_measured") or 0, row.get("fit_rms_px")
    sc, nxt = row.get("score"), row.get("runner_up_score")
    parts = [f"{n} letters measured"]
    if rms is not None:
        parts.append(f"fit {rms:.2f} px ({'clean' if rms < 0.2 else 'fair' if rms < 0.5 else 'poor'})")
    if sc is not None:
        parts.append(f"best seed scores {sc:g} ({sc / max(1, n):.1f} per letter)")
        parts.append(f"next best {nxt:g}, a gap of {nxt - sc:.0f}" if nxt is not None else "no other seed came close")
    note = row.get("note") or ""
    if any(k in note for k in ("confirmed by", "found near", "just before")):
        parts.append("confirmed by the neighbouring sublevels' seeds")
    return "; ".join(parts) + "."


def find_views(video, feed, frame: int, span: int = 240) -> tuple[int | None, int | None]:
    """Frames of the comedown and the landing view after the entry screen settles at `frame`.

    The title stays up over the comedown (the pod coming down, seen from above) until the
    screen goes dark; the landing view fades in after that dark gap (the last one, past any
    short cutscene). The comedown frame is two thirds of the way from its brightest moment to the gap;
    the landing frame is early in the fade-in, before the Pikmin pour out."""
    fr, br = [], []
    for f, g in video.sample(2, frame, frame + span):
        fr.append(f)
        br.append(float(feed.crop(g).mean()))
    if not br:
        return None, None
    br = np.array(br)
    # captures' black is rarely 0 (often ~17), so "dark" is relative to this clip's range
    # (the range is taken over the first 180 frames: later the player may walk somewhere brighter)
    early = np.array(fr) < frame + 180
    lo, hi = br[early].min(), br[early].max()
    dark = [i for i in np.nonzero(br <= lo + 0.12 * (hi - lo))[0] if early[i]]
    if not dark:
        return None, None
    d = int(dark[-1])
    # the comedown: the title stretch before that dark gap. The gap is found by walking back from
    # its end while the screen stays at the gap's own floor (a dim title barely differs from it)
    g0 = d
    while g0 > 0 and br[g0 - 1] <= br[d] + 0.5:
        g0 -= 1
    come = None
    if g0 >= 2:
        p = int(np.argmax(br[:g0]))
        if g0 - p >= 2:
            come = fr[p + int(0.65 * (g0 - p))]                # past the flash of the pod opening
    after = br[d: d + 30]
    hit = np.nonzero(after >= lo + 0.45 * (after.max() - lo))[0]
    land = fr[d + int(hit[0])] if len(hit) else None
    return come, land


def _brighten(img: np.ndarray) -> np.ndarray:
    """Stretch a dim frame's levels so the floor shows (1st-99.5th percentile to full range)."""
    lo, hi = np.percentile(img, (1, 99.5))
    return cv2.convertScaleAbs(img, alpha=255.0 / max(hi - lo, 1.0), beta=-lo * 255.0 / max(hi - lo, 1.0))


def _figure(src: str, alt: str, caption: str, wide: bool = False) -> str:
    return (f'<figure{" class=wide" if wide else ""}><img loading="lazy" src="{html.escape(src)}" '
            f'alt="{html.escape(alt)}"><figcaption>{html.escape(caption)}</figcaption></figure>')


def write(out_dir: str | Path, progress=None, force: bool = False) -> Path:
    from . import debug, views
    from .feed import Feed
    from .video import Video
    out_dir = Path(out_dir)
    data = json.loads((out_dir / "seeds.json").read_text(encoding="utf-8"))
    meta, entries = data["meta"], [e for e in data["entries"] if e.get("cave")]
    video, feed = Video(meta["video"]), Feed(*meta["feed"])
    img = out_dir / "img"
    img.mkdir(exist_ok=True)
    e = html.escape
    cards = []
    for n, row in enumerate(entries):
        f = row["frame"]
        note = row.get("note") or ""
        fall = img / f"fall_{f}.jpg"
        if force or not fall.exists():
            try:
                debug.render(meta["video"], f, feed, fall, weak="weaker" in note, wall="video clock" in note,
                             compact=True, video=video)
            except Exception:
                pass
        come, land = img / f"view_comedown_{f}.jpg", img / f"view_landing_{f}.jpg"
        if force or not come.exists() or not land.exists():
            for p in (img / f"comedown_{f}.jpg", img / f"layout_outline_{f}.jpg"):     # older names
                p.unlink(missing_ok=True)
            cf, lf = find_views(video, feed, f)
            for fr_, path, bright in ((cf, come, True), (lf, land, False)):
                g = video.frame_at(fr_) if fr_ is not None else None
                if g is not None:
                    pic = cv2.resize(feed.crop(g), (480, 360))
                    cv2.imwrite(str(path), _brighten(pic) if bright else pic, [cv2.IMWRITE_JPEG_QUALITY, 80])
        lay = next(iter(img.glob(f"layout_{f}_*.png")), None)
        outl = img / f"layout_views_{f}.jpg"
        if row.get("layout_seed") and row.get("sublevel") and (force or not outl.exists()):
            try:
                views.render(row["cave"], row["sublevel"], int(row["layout_seed"], 16), outl, fallback=lay)
            except Exception:
                pass
        pics = []
        if fall.exists():
            pics.append(_figure(f"img/{fall.name}", "falling letters", "Falling letters, tracker boxes and the fitted fall", True))
        if come.exists():
            pics.append(_figure(f"img/{come.name}", "comedown", "Comedown (behind the title, brightened)"))
        if land.exists():
            pics.append(_figure(f"img/{land.name}", "landing view", "Landing view"))
        if outl.exists():
            pics.append(_figure(f"img/{outl.name}", "layout", "Layout (CaveGen3): comedown (blue), landing view (yellow), pod facing (arrow)"
                                if views.cavegen3_exe() else "Layout: landing view (orange), pod facing (arrow)"))
        elif lay:
            pics.append(_figure(f"img/{lay.name}", "layout", "Layout"))
        entry = img / f"entry_{f}.jpg"
        if entry.exists():
            pics.append(_figure(f"img/{entry.name}", "entry screen", "Entry screen"))
        link = (f'<a href="{e(row["link"])}" target="_blank" rel="noopener">{e(row["time"])}</a>'
                if row.get("link") else e(row.get("time", "")))
        cards.append(f"""
<section class="card {e(row['confidence'])}" id="{e(row['cave'])}-{row['sublevel'] or 0}">
  <header><h2>{e(row['cave'])} {row['sublevel'] or '?'}</h2><span class="conf">{e(row['confidence'])}</span>
  <span class="why">{e(explain(row))}</span></header>
  <dl>
    <dt>Video</dt><dd>{link}</dd>
    <dt>Layout seed</dt><dd><code>{e(row.get('layout_seed') or '-')}</code></dd>
    <dt>Letter seed</dt><dd><code>{e(row.get('letter_seed') or '-')}</code></dd>
    <dt>Letters</dt><dd>{row.get('letters_measured')} measured · fit {row.get('fit_rms_px')} px · score {row.get('score')} (next {row.get('runner_up_score')})</dd>
    {f"<dt>Note</dt><dd>{e(note)}</dd>" if note else ""}
  </dl>
  <div class="imgs">{''.join(pics)}</div>
</section>""")
        if progress:
            progress(n + 1, len(entries), row)
    who = ", ".join(p["name"] for p in meta.get("run", {}).get("players", [])) or out_dir.name
    title = e(f"{who} - detection")
    page = PAGE.format(title=title, summary=e(meta.get("summary", "")), help=SCORE_HELP, cards="".join(cards))
    path = out_dir / "report.html"
    path.write_text(page, encoding="utf-8")
    return path


PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title>
<style>
:root {{ --bg:#f6f6f4; --fg:#1d1d1b; --muted:#6b6b66; --card:#fff; --line:#deded8; --hi:#1f7a3a; --mid:#a86b00; --lo:#b42318; }}
@media (prefers-color-scheme: dark) {{ :root {{ --bg:#161614; --fg:#ececea; --muted:#9a9a94; --card:#20201e; --line:#33332f; --hi:#5cc27a; --mid:#e0a63a; --lo:#f0786d; }} }}
* {{ box-sizing:border-box; }}
body {{ background:var(--bg); color:var(--fg); font:15px/1.45 system-ui,sans-serif; margin:0; padding:24px 16px; }}
main {{ max-width:1240px; margin:0 auto; }}
h1 {{ font-size:22px; margin:0 0 4px; }} .meta {{ color:var(--muted); margin-bottom:14px; }}
.help {{ background:var(--card); border:1px solid var(--line); border-radius:8px; padding:10px 16px; margin-bottom:18px; }}
.help summary {{ cursor:pointer; font-weight:600; }}
.card {{ background:var(--card); border:1px solid var(--line); border-radius:8px; padding:14px 16px; margin-bottom:14px; }}
.card header {{ display:flex; align-items:baseline; gap:12px; flex-wrap:wrap; }} .card h2 {{ margin:0; font-size:18px; }}
.why {{ color:var(--muted); font-size:13px; }}
.conf {{ font-size:12px; text-transform:uppercase; letter-spacing:.05em; font-weight:600; }}
.high .conf {{ color:var(--hi); }} .medium .conf {{ color:var(--mid); }} .low .conf, .none .conf {{ color:var(--lo); }}
dl {{ display:grid; grid-template-columns:max-content 1fr; gap:2px 14px; margin:10px 0; }} dt {{ color:var(--muted); }} dd {{ margin:0; }}
.imgs {{ display:flex; flex-wrap:wrap; gap:10px; align-items:flex-start; }}
figure {{ margin:0; }} figure img {{ display:block; max-width:100%; height:auto; max-height:320px; border-radius:4px; border:1px solid var(--line); }}
figure.wide {{ flex-basis:100%; }} figure.wide img {{ max-height:none; width:100%; }}
figcaption {{ color:var(--muted); font-size:12px; margin-top:3px; }}
code {{ font-size:14px; }} a {{ color:inherit; }}
</style></head><body><main>
<p><a href="../index.html">&larr; All runs</a> &middot; <a href="judge.html">Layouts and judge</a></p>
<h1>{title}</h1>
<div class="meta">{summary}</div>
{help}
{cards}
</main></body></html>"""
