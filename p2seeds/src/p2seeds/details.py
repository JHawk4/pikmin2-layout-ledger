"""A run's detection page with what the detector saw, for checking it by eye.

Per sublevel: the falling letters with the tracker's boxes and the fitted fall, the comedown
(the floor in view after landing, before the Pikmin pour out), the layout with the camera's
view at landing outlined, and a plain reading of the score. Built from seeds.json and the
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
<p>The comedown picture is the first moment the floor is in view after landing. The layout render outlines what the
camera shows at landing, so the two should match.</p></details>"""


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


def find_comedown(video, feed, frame: int, span: int = 240) -> int | None:
    """First frame of the landing view: after the entry screen and the dark gap that follows it
    (the last such gap, past any short cutscene), once the floor has faded in."""
    fr, br = [], []
    for f, g in video.sample(3, frame, frame + span):
        fr.append(f)
        br.append(float(feed.crop(g).mean()))
    if not br:
        return None
    br = np.array(br)
    # captures' black is rarely 0 (often ~17), so "dark" is relative to this clip's range
    lo = br.min()
    dark = [i for i in np.nonzero(br <= lo + 0.12 * (br.max() - lo))[0] if fr[i] < frame + 180]
    if not dark:
        return None
    d = int(dark[-1])
    after = br[d: d + 20]
    hit = np.nonzero(after >= lo + 0.6 * (after.max() - lo))[0]      # early: before the Pikmin pour out
    return fr[d + int(hit[0])] if len(hit) else None


def _figure(src: str, alt: str, caption: str, wide: bool = False) -> str:
    return (f'<figure{" class=wide" if wide else ""}><img loading="lazy" src="{html.escape(src)}" '
            f'alt="{html.escape(alt)}"><figcaption>{html.escape(caption)}</figcaption></figure>')


def write(out_dir: str | Path, progress=None, force: bool = False) -> Path:
    from . import cg3, comedown, debug
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
        come = img / f"comedown_{f}.jpg"
        if force or not come.exists():
            cf = find_comedown(video, feed, f)
            g = video.frame_at(cf) if cf is not None else None
            if g is not None:
                cv2.imwrite(str(come), cv2.resize(feed.crop(g), (480, 360)), [cv2.IMWRITE_JPEG_QUALITY, 80])
        lay = next(iter(img.glob(f"layout_{f}_*.png")), None)
        outl = img / f"layout_outline_{f}.jpg"
        if lay and row.get("layout_seed") and row.get("sublevel") and (force or not outl.exists()):
            try:
                ship = cg3.layout(row["cave"], row["sublevel"], int(row["layout_seed"], 16)).get("ship")
                if ship:
                    tmp = comedown.draw(lay, ship, img / f"_outline_{f}.png")
                    cv2.imwrite(str(outl), cv2.imread(str(tmp)), [cv2.IMWRITE_JPEG_QUALITY, 82])
                    tmp.unlink()
            except Exception:
                pass
        pics = []
        if fall.exists():
            pics.append(_figure(f"img/{fall.name}", "falling letters", "Falling letters, tracker boxes and the fitted fall", True))
        if come.exists():
            pics.append(_figure(f"img/{come.name}", "comedown", "Comedown in the video"))
        if outl.exists():
            pics.append(_figure(f"img/{outl.name}", "layout", "Layout, camera view at landing outlined"))
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
