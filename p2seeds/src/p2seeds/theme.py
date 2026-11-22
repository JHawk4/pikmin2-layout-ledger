"""The look shared with the other Pikmin sites (CaveGen3, pikmin-wrs): pale grass background,
leaf-green navigation pill with a sun-orange edge, white rounded panels, the flower logo, and
a suggestion box that posts to the same Google Form as those sites.

apply() puts the theme into a page built by any of the page writers: the colour variables
(after the page's own, so these win), the header with navigation, and the footer.
"""

from __future__ import annotations

import html
import re

SITE = "Pikmin 2 Layout Ledger"

LOGO = ('<svg viewBox="0 0 24 34" width="22" height="31" aria-hidden="true">'
        '<path d="M12 33 C12 26 11.6 20 12 13" stroke="#3c8531" stroke-width="2.2" fill="none" stroke-linecap="round"/>'
        '<path d="M12 25 C8.5 25.5 5 23.5 3.6 20.6 C7.4 19.6 10.6 21.5 12 25 Z" fill="#5fb447" stroke="#3c8531" stroke-width="1"/>'
        + "".join(f'<ellipse cx="{x}" cy="{y}" rx="3.1" ry="4.3" transform="rotate({a} {x} {y})" fill="#ffffff" stroke="#c9c2d6" stroke-width="0.8"/>'
                  for x, y, a in ((12.00, 4.40, 0), (16.37, 7.58, 72), (14.70, 12.72, 144), (9.30, 12.72, 216), (7.63, 7.58, 288)))
        + '<circle cx="12" cy="9" r="3.1" fill="#f2c230" stroke="#d39a12" stroke-width="0.9"/></svg>')

# The page writers use --bg, --fg, --muted, --card, --line, --good, --mid, --bad (+ *bg tints).
CSS = """
:root, :root[data-theme="light"] {
  --bg:#e4eed2; --bg-2:#d3e4b8; --fg:#1d2418; --muted:#5f6b58; --card:#ffffff; --line:#d5dccb; --field:#f7faf1;
  --leaf:#4b9a3c; --leaf-2:#3c8531; --leaf-dark:#2c6a24; --accent:#3c8531; --sun:#f2a01c;
  --good:#2c6a24; --mid:#8a6a1f; --bad:#b3261e; --goodbg:#e3f1dc; --midbg:#f6ecd6; --badbg:#f8e1df; --bar:#c9d3bd;
  --radius:14px; --shadow:0 1px 2px rgba(44,106,36,.12), 0 2px 10px rgba(44,106,36,.08); color-scheme:light;
}
@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) {
  --bg:#141c10; --bg-2:#0d130a; --fg:#e6ece0; --muted:#a3ae98; --card:#1d2619; --line:#34442c; --field:#161e12;
  --leaf-dark:#a6dc8f; --accent:#8fd37a; --good:#8fd37a; --mid:#e0b45a; --bad:#f2b8b5;
  --goodbg:#1e3319; --midbg:#352d19; --badbg:#3b2120; --bar:#3a4a32;
  --shadow:0 1px 2px rgba(0,0,0,.4), 0 2px 10px rgba(0,0,0,.25); color-scheme:dark; } }
html { background:var(--bg); }
body { background:linear-gradient(180deg, var(--bg) 0, var(--bg) 340px, var(--bg-2) 100%) fixed; color:var(--fg);
  font-family:system-ui,-apple-system,"Segoe UI",Roboto,sans-serif; }
a { color:var(--accent); } a:hover { color:var(--leaf-dark); }
.site-header { max-width:1240px; margin:0 auto 14px; display:flex; align-items:center; gap:14px; flex-wrap:wrap; }
.site-logo { display:flex; align-items:center; gap:6px; color:var(--leaf-dark); text-decoration:none; font-weight:800;
  letter-spacing:-.5px; font-size:1.25rem; text-shadow:1px 1px 0 rgba(255,255,255,.8); }
@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) .site-logo { text-shadow:none; } }
.site-nav { display:flex; flex-wrap:wrap; gap:2px; font-size:.92rem; font-weight:700; border-radius:999px; padding:3px;
  background:linear-gradient(135deg, var(--leaf), var(--leaf-2)); box-shadow:inset 4px 0 0 var(--sun); }
.site-nav a { text-decoration:none; color:#fff; padding:3px 12px; border-radius:999px; }
.site-nav a:hover { color:#fff; background:rgba(0,0,0,.15); }
.site-nav a[aria-current="page"] { background:#fff; color:var(--leaf-2); }
.site-cats { display:flex; gap:2px; font-size:.92rem; font-weight:700; border-radius:999px; padding:3px;
  border:2px solid var(--accent); background:var(--card); }
.site-cats a { text-decoration:none; color:var(--accent); padding:1px 12px; border-radius:999px; }
.site-cats a:hover { background:var(--goodbg); }
.site-cats a[aria-current="page"] { background:var(--leaf-2); color:#fff; }
.site-footer { max-width:1240px; margin:28px auto 0; color:var(--muted); font-size:.85rem; }
h1, h2 { color:var(--leaf-dark); }
h2 { padding-bottom:2px; border-bottom:2px solid var(--sun); display:inline-block; }
.tablewrap, .card, .help, .tile, .stat { border-radius:var(--radius) !important; box-shadow:var(--shadow); }
"""

SUGGEST_FORM = "https://docs.google.com/forms/d/e/1FAIpQLSepPb6F7_Y6DlLoHn-nqpy2KG3BqaMLfDLAdArL9B5iyEt_LA/formResponse"


CATEGORIES = (("pod", "Pay Off Debt", ""), ("at", "All Treasures", "at/"))


def category_of(kind: str | None) -> str:
    """The site section a run of this judge kind belongs to."""
    return "at" if kind == "at" else "pod"


def header(prefix: str = "", run: str | None = None, active: str = "runs", category: str = "pod") -> str:
    """Site header. `prefix` leads from the page to its section's root ("" or "../"); on a run's
    pages `run` names it and its two pages appear in the navigation. Each category has its own
    section (Pay Off Debt at the site root, All Treasures under at/), with a switch between them."""
    root = prefix + next(("../" * sub.count("/") for key, _, sub in CATEGORIES if key == category), "")
    links = [("runs", f"{prefix}index.html", "All runs")]
    if run:
        links += [("judge", "judge.html", "Layouts"), ("detection", "report.html", "Seed detection")]
    else:
        links += [("layouts", "layouts.html", "Layouts"), ("detection", "detection.html", "Detection"),
                  ("timesave", "timesave.html", "Time saved")]
        if category == "pod":
            links.append(("pokos", "pokos.html", "Pokos"))
        links += [("howjudge", "how-judge.html", "The judge"), ("accuracy", "accuracy.html", "Judge accuracy"),
                  ("seeds", "seeds.html", "Seed check")]
    links.append(("gecko", f"{root}gecko.html", "Gecko code"))
    links.append(("suggest", f"{root}suggest.html", "Suggestion box"))
    nav = "".join(f'<a href="{href}"{" aria-current=page" if key == active else ""}'
                  f'{" class=nav-suggest" if key == "suggest" else ""}>{label}</a>' for key, href, label in links)
    cats = "".join(f'<a href="{root}{sub}index.html"{" aria-current=page" if key == category else ""}>{label}</a>'
                   for key, label, sub in CATEGORIES)
    return (f'<header class="site-header"><a class="site-logo" href="{root}index.html">{LOGO}{SITE}</a>'
            f'<nav class="site-cats" aria-label="Category">{cats}</nav>'
            f'<nav class="site-nav">{nav}</nav></header>')


FOOTER = ('<footer class="site-footer">Layouts, pictures, treasures and the judge from '
          '<a href="https://jhawk4.github.io/CaveGen3/">CaveGen3</a>; runs from '
          '<a href="https://www.speedrun.com/pikmin2">speedrun.com</a>. '
          'Source: <a href="https://github.com/JHawk4/pikmin2-layout-ledger">github.com/JHawk4/pikmin2-layout-ledger</a>.</footer>')

# The suggestion box remembers which page it was opened from (the hidden "page" field).
NAV_JS = """<script>
for (const a of document.querySelectorAll('a.nav-suggest')) a.addEventListener('click', () => {
  const p = location.pathname.split('/').filter(Boolean); const here = p.slice(-2).join('/');
  const u = new URL(a.href); u.searchParams.set('from', here); a.href = u.toString(); });
</script>"""


def apply(page: str, prefix: str = "", run: str | None = None, active: str = "runs", category: str = "pod") -> str:
    """The page with the theme's CSS (last, so it wins), header and footer added."""
    page = page.replace("</style>", CSS + "</style>", 1)
    page = re.sub(r"<body([^>]*)>", lambda m: f"<body{m.group(1)}>" + header(prefix, run, active, category), page, count=1)
    return page.replace("</body>", FOOTER + NAV_JS + "</body>", 1)


def reheader(page: str, prefix: str = "", run: str | None = None, active: str = "runs", category: str = "pod") -> str:
    """A themed page with its header written again (pages built before the category switch, or
    by a slow step such as the detection page, which isn't rebuilt with the site)."""
    return re.sub(r'<header class="site-header">.*?</header>', lambda m: header(prefix, run, active, category),
                  page, count=1, flags=re.S)


def suggest_page() -> str:
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Suggestion box · {SITE}</title>
<style>
* {{ box-sizing:border-box; }} body {{ margin:0; padding:20px 16px 40px; line-height:1.45; }}
main {{ max-width:680px; margin:0 auto; }}
.suggest {{ display:flex; flex-direction:column; gap:12px; background:var(--card); border:1px solid var(--line);
  border-top:4px solid var(--sun); border-radius:var(--radius); box-shadow:var(--shadow); padding:14px; }}
.field {{ display:flex; flex-direction:column; gap:4px; }} .field > span {{ font-size:.8rem; color:var(--muted); }}
input, textarea, button {{ font:inherit; color:inherit; background:var(--field); border:1px solid var(--line);
  border-radius:6px; padding:6px 10px; min-height:36px; }}
textarea {{ resize:vertical; }}
button.primary {{ background:linear-gradient(135deg, var(--leaf), var(--leaf-2)); color:#fff; border-color:var(--leaf-2);
  font-weight:700; cursor:pointer; }}
.buttons {{ display:flex; align-items:center; gap:12px; }} .status {{ color:var(--muted); }}
</style></head><body><main>
<h1>Suggestion box</h1>
<p>Spotted a wrong seed, a misread poko count, a run that is missing, or have an idea for this site? Leave a note.
It goes privately to the site's maker (through a Google Form) and is not published. Both other fields are optional.</p>
<!-- The same Google Form as the other Pikmin sites; "page" tells them apart. -->
<form id="suggest" class="suggest" action="{SUGGEST_FORM}" method="POST">
  <label class="field"><span>Name (optional)</span>
    <input name="entry.1125475916" maxlength="80" placeholder="e.g. your speedrun.com name"></label>
  <label class="field"><span>Suggestion</span>
    <textarea name="entry.1148029577" rows="7" maxlength="4000" required></textarea></label>
  <label class="field"><span>How to reach you (optional)</span>
    <input name="entry.303778019" maxlength="120" placeholder="Discord username or email, if you'd like a reply"></label>
  <input type="hidden" name="entry.1626566187" id="suggest-page">
  <div class="buttons"><button type="submit" class="primary">Send</button>
    <span id="suggest-status" class="status" role="status" aria-live="polite"></span></div>
</form>
</main>
<script>
const form = document.getElementById('suggest'), status = document.getElementById('suggest-status');
form.addEventListener('submit', async (e) => {{
  e.preventDefault();
  document.getElementById('suggest-page').value = 'pikmin2-layout-ledger/' + (new URLSearchParams(location.search).get('from') || '');
  const button = form.querySelector('button'); button.disabled = true; status.textContent = 'Sending…';
  try {{
    // Google Forms doesn't allow reading the reply, so a sent request counts as success.
    await fetch(form.action, {{ method: 'POST', body: new FormData(form), mode: 'no-cors' }});
    form.reset(); status.textContent = 'Thanks! Your suggestion was sent.';
  }} catch {{ status.textContent = "Sorry, it couldn't be sent. Please try again later."; }}
  finally {{ button.disabled = false; }}
}});
</script>
</body></html>"""


def esc(s) -> str:
    return html.escape(str(s))
