"""Write a run's results as JSON, CSV and a self-contained HTML page."""

from __future__ import annotations

import csv
import html
import json
from pathlib import Path

import cv2


def _ts(frame: int | None, fps: float) -> str:
    if frame is None:
        return ""
    s = int(frame / fps)
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    return f"{h}:{m:02d}:{sec:02d}"


def _link(video_url: str | None, frame: int | None, fps: float) -> str | None:
    if not video_url or frame is None:
        return None
    sec = max(0, int(frame / fps) - 5)
    sep = "&" if "?" in video_url else "?"
    return f"{video_url}{sep}t={sec}" if "youtube" in video_url else f"{video_url}{sep}t={sec}s"


def rows(results, fps: float, video_url: str | None) -> list[dict]:
    out = []
    for r in results:
        if not r.cave_id:
            continue
        out.append({
            "time": _ts(r.settled_frame, fps),
            "frame": r.settled_frame,
            "link": _link(video_url, r.settled_frame, fps),
            "cave": r.cave_id,
            "cave_name": r.cave,
            "sublevel": r.sublevel,
            "sublevel_source": r.sublevel_source,
            "letter_seed": f"0x{r.letter_seed:08X}" if r.letter_seed is not None else None,
            "layout_seed": f"0x{r.layout_seed:08X}" if r.layout_seed is not None else None,
            "confidence": r.confidence,
            "letters_measured": int(sum(1 for x in r.fit.v if x == x)) if r.fit else 0,
            "fit_rms_px": round(r.fit.rms_px, 3) if r.fit else None,
            "bias": round(r.candidates[0].bias, 3) if r.candidates else None,
            "score": round(r.candidates[0].score, 2) if r.candidates else None,
            "runner_up_score": round(r.candidates[1].score, 2) if len(r.candidates) > 1 else None,
            "cave_match": round(r.cave_score, 3),
            "note": r.note,
            "chain_dist": getattr(r, "chain_dist", None),
            "lang": getattr(r, "lang", "en"),
        })
    return out


def write(out_dir: str | Path, title: str, results, fps: float, video_url: str | None,
          thumbs: dict[int, object], layouts: dict[int, Path], meta: dict) -> Path:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    data = rows(results, fps, video_url)
    (out_dir / "seeds.json").write_text(json.dumps({"meta": meta, "entries": data}, indent=2), encoding="utf-8")
    with open(out_dir / "seeds.csv", "w", newline="", encoding="utf-8") as f:
        if data:
            w = csv.DictWriter(f, fieldnames=list(data[0].keys()))
            w.writeheader()
            w.writerows(data)

    img_dir = out_dir / "img"
    img_dir.mkdir(exist_ok=True)
    cards = []
    for r, row in zip([r for r in results if r.cave_id], data):
        thumb = thumbs.get(r.settled_frame)
        thumb_rel = None
        if thumb is not None:
            thumb_rel = f"img/entry_{r.settled_frame}.jpg"
            cv2.imwrite(str(out_dir / thumb_rel), thumb, [cv2.IMWRITE_JPEG_QUALITY, 80])
        lay = layouts.get(r.settled_frame)
        lay_rel = lay.relative_to(out_dir).as_posix() if lay else None
        e = html.escape
        link = f'<a href="{e(row["link"])}">{e(row["time"])}</a>' if row["link"] else e(row["time"])
        cards.append(f"""
<section class="card {e(row['confidence'])}">
  <header><h2>{e(row['cave'])}-{row['sublevel'] or '?'}</h2><span class="conf">{e(row['confidence'])}</span></header>
  <dl>
    <dt>Video</dt><dd>{link}</dd>
    <dt>Layout seed</dt><dd><code>{e(row['layout_seed'] or '—')}</code></dd>
    <dt>Letter seed</dt><dd><code>{e(row['letter_seed'] or '—')}</code></dd>
    <dt>Letters</dt><dd>{row['letters_measured']} measured · fit {row['fit_rms_px']} px · score {row['score']} (next {row['runner_up_score']})</dd>
    <dt>Sublevel from</dt><dd>{e(row['sublevel_source'])}</dd>
    {f"<dt>Note</dt><dd>{e(row['note'])}</dd>" if row['note'] else ""}
  </dl>
  <div class="imgs">
    {f'<img src="{thumb_rel}" alt="entry screen">' if thumb_rel else ''}
    {f'<img src="{lay_rel}" alt="layout">' if lay_rel else ''}
  </div>
</section>""")

    page = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(title)}</title>
<style>
:root {{ --bg:#f6f6f4; --fg:#1d1d1b; --muted:#6b6b66; --card:#fff; --line:#deded8; --hi:#1f7a3a; --mid:#a86b00; --lo:#b42318; }}
@media (prefers-color-scheme: dark) {{ :root {{ --bg:#161614; --fg:#ececea; --muted:#9a9a94; --card:#20201e; --line:#33332f; --hi:#5cc27a; --mid:#e0a63a; --lo:#f0786d; }} }}
body {{ background:var(--bg); color:var(--fg); font:15px/1.45 system-ui,sans-serif; margin:0; padding:24px 16px; }}
main {{ max-width:1100px; margin:0 auto; }}
h1 {{ font-size:22px; margin:0 0 4px; }} .meta {{ color:var(--muted); margin-bottom:20px; }}
.card {{ background:var(--card); border:1px solid var(--line); border-radius:8px; padding:14px 16px; margin-bottom:14px; }}
.card header {{ display:flex; align-items:baseline; gap:12px; }} .card h2 {{ margin:0; font-size:18px; }}
.conf {{ font-size:12px; text-transform:uppercase; letter-spacing:.05em; font-weight:600; }}
.high .conf {{ color:var(--hi); }} .medium .conf {{ color:var(--mid); }} .low .conf, .none .conf {{ color:var(--lo); }}
dl {{ display:grid; grid-template-columns:max-content 1fr; gap:2px 14px; margin:10px 0; }} dt {{ color:var(--muted); }} dd {{ margin:0; }}
.imgs {{ display:flex; flex-wrap:wrap; gap:10px; }} .imgs img {{ max-width:100%; height:auto; max-height:300px; border-radius:4px; border:1px solid var(--line); }}
code {{ font-size:14px; }} a {{ color:inherit; }}
</style></head><body><main>
<h1>{html.escape(title)}</h1>
<div class="meta">{html.escape(meta.get('summary', ''))}</div>
{''.join(cards)}
</main></body></html>"""
    path = out_dir / "report.html"
    path.write_text(page, encoding="utf-8")
    return path
