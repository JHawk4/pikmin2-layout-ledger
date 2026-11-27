"""The "Gecko code" page (gecko.html at the site root): pick a game version and a run, get a
Gecko code that gives every sublevel the run has a trusted seed for the run's layout.

The runs' tables and each version's fixed code are embedded as JSON; the page's script joins
them the same way gecko.words does (tests/test_gecko.py runs the script against it)."""

from __future__ import annotations

import html
import json

from . import gecko
from .theme import SITE


def run_data(runs: list[dict], prefix: str) -> list[dict]:
    """One record per run with at least one trusted seed. `prefix` leads from the site root to
    the runs' section ("" or "at/")."""
    out = []
    for r in runs:
        rows = [list(v) for v in gecko.sublevels(r["entries"])]
        if not rows:
            continue
        run = r.get("run", {})
        out.append({"slug": r["slug"], "label": r["runner"], "href": f"{prefix}{r['slug']}/judge.html",
                    "category": "All Treasures" if r.get("kind") == "at" else "Pay Off Debt",
                    "platform": run.get("platform") or "", "region": run.get("region") or "", "rows": rows})
    return out


def versions_data() -> list[dict]:
    return [{"key": v.key, "label": v.label, "gameId": v.game_id, "hook": v.hook, "checked": v.checked,
             "body": gecko.body(v)} for v in gecko.VERSIONS]


JS = r"""
const V = JSON.parse(document.getElementById('gecko-versions').textContent);
const R = JSON.parse(document.getElementById('gecko-runs').textContent);
const $ = id => document.getElementById(id);
const hex = (x, n) => (x >>> 0).toString(16).toUpperCase().padStart(n, '0');
// Same as gecko.words: bl over the table, the table (key, seed; 0 ends it), the body, the return slot.
function words(v, rows) {
  const tab = rows.flatMap(r => [r[2], r[3]]).concat([0]);
  const out = [(0x48000001 | (4 + 4 * tab.length)) >>> 0, ...tab, ...v.body];
  if (out.length % 2 === 0) out.push(0x60000000);
  out.push(0);
  return out;
}
function code(v, rows) {
  const w = words(v, rows);
  const lines = ['C2' + hex(v.hook & 0x01FFFFFF, 6) + ' ' + hex(w.length / 2, 8)];
  for (let i = 0; i < w.length; i += 2) lines.push(hex(w[i], 8) + ' ' + hex(w[i + 1], 8));
  return lines.join('\n');
}
if (typeof module !== 'undefined') module.exports = { words, code };
"""

PAGE_JS = r"""
for (const v of V) $('version').add(new Option(v.label + (v.checked ? '' : ' (untested)'), v.key));
const groups = {};
for (const [i, r] of R.entries()) {
  const g = groups[r.category] || (groups[r.category] = document.createElement('optgroup'));
  g.label = r.category;
  g.appendChild(new Option(`${r.label}${r.platform && r.platform !== 'GameCube' ? ' · ' + r.platform : ''} · ${r.rows.length} sublevels`, i));
}
for (const g of Object.values(groups)) $('run').appendChild(g);
function show() {
  const v = V.find(x => x.key === $('version').value), r = R[+$('run').value];
  if (!v || !r) return;
  const name = `Layouts of ${r.label} (${r.category}) [Pikmin 2 Layout Ledger]`;
  $('code').value = '$' + name + '\n' + code(v, r.rows);
  $('summary').innerHTML = `${r.rows.length} sublevels get <a href="${r.href}">this run's layouts</a>; any other sublevel stays random.`
    + (v.checked ? '' : ' <b>This version\'s addresses come from the decomp\'s symbol map and have not been tried on a real copy of the game yet.</b>')
    + (/Wii/.test(r.platform) !== v.gameId.startsWith('R92') ? ` This run was played on ${r.platform || 'GameCube'}, so on ${v.gameId.startsWith('R92') ? 'the Wii' : 'GameCube'} its seeds give the run's layouts only where the two versions' cave files are the same.` : '');
  $('rows').innerHTML = r.rows.map(x => `<tr><td>${x[0]} ${x[1]}</td><td><code>${hex(x[3], 8)}</code></td>`
    + `<td><a href="https://jhawk4.github.io/CaveGen3/?sublevel=pikmin2:${x[0]}-${x[1]}&seed=${hex(x[3], 8)}${r.category === 'Pay Off Debt' ? '&judge=judge2' : ''}">CaveGen3</a></td></tr>`).join('');
  $('gameid').textContent = v.gameId;
}
$('version').addEventListener('change', show);
$('run').addEventListener('change', show);
$('copy').addEventListener('click', async () => {
  try { await navigator.clipboard.writeText($('code').value); $('copied').textContent = 'Copied.'; }
  catch { $('code').select(); $('copied').textContent = 'Press Ctrl+C to copy.'; }
});
$('gct').addEventListener('click', () => {
  // A .gct file (Nintendont, Wii code loaders): 00D0C0DE 00D0C0DE, the code, F0000000 00000000.
  const v = V.find(x => x.key === $('version').value), r = R[+$('run').value];
  const lines = code(v, r.rows).split('\n').map(l => l.split(' '));
  const w = ['00D0C0DE', '00D0C0DE', ...lines.flat(), 'F0000000', '00000000'];
  const buf = new Uint8Array(w.length * 4);
  w.forEach((x, i) => { const n = parseInt(x, 16); buf.set([n >>> 24, (n >>> 16) & 255, (n >>> 8) & 255, n & 255], 4 * i); });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(new Blob([buf], { type: 'application/octet-stream' }));
  a.download = v.gameId + '.gct'; a.click(); setTimeout(() => URL.revokeObjectURL(a.href), 1000);
});
const pre = new URLSearchParams(location.search).get('run');
const at = R.findIndex(r => r.slug === pre);
if (at >= 0) $('run').value = at;
show();
"""


def page(runs_by_section: list[tuple[list[dict], str]]) -> str:
    runs = [x for runs, prefix in runs_by_section for x in run_data(runs, prefix)]
    unsupported = "".join(f"<li>{html.escape(a)}: {html.escape(b)}</li>" for a, b in gecko.UNSUPPORTED)
    data = lambda x: json.dumps(x, separators=(",", ":")).replace("</", "<\\/")
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Gecko code · {SITE}</title>
<style>
* {{ box-sizing:border-box; }} body {{ margin:0; padding:20px 16px 40px; line-height:1.45; }}
main {{ max-width:860px; margin:0 auto; }}
.card {{ background:var(--card); border:1px solid var(--line); border-top:4px solid var(--sun); padding:14px; margin:14px 0; }}
.pick {{ display:grid; grid-template-columns:1fr 1fr; gap:12px; }}
@media (max-width:640px) {{ .pick {{ grid-template-columns:1fr; }} }}
.field {{ display:flex; flex-direction:column; gap:4px; min-width:0; }} .field > span {{ font-size:.8rem; color:var(--muted); }}
select, textarea, button {{ font:inherit; color:inherit; background:var(--field); border:1px solid var(--line);
  border-radius:6px; padding:6px 10px; min-height:36px; max-width:100%; }}
textarea {{ width:100%; font-family:ui-monospace,Consolas,monospace; font-size:.9rem; resize:vertical; }}
button.primary {{ background:linear-gradient(135deg, var(--leaf), var(--leaf-2)); color:#fff; border-color:var(--leaf-2);
  font-weight:700; cursor:pointer; }}
button {{ cursor:pointer; }}
.buttons {{ display:flex; align-items:center; gap:10px; flex-wrap:wrap; margin-top:8px; }} .muted, #copied {{ color:var(--muted); }}
table {{ border-collapse:collapse; width:100%; font-size:.9rem; }} td {{ padding:3px 8px; border-bottom:1px solid var(--line); }}
.tablewrap {{ background:var(--card); border:1px solid var(--line); padding:6px 8px; max-height:340px; overflow:auto; }}
li {{ margin:3px 0; }}
</style></head><body><main>
<h1>Gecko code: play a run's layouts</h1>
<p class="intro">Pick your copy of the game and a run. The code below makes every cave sublevel that run has a
trusted seed for come out with the run's layout, so you can practise the same caves the runner had. Sublevels the
run doesn't have (or whose seed wasn't read with confidence) stay random. Story mode only; challenge mode and 2-player
battle are left alone. Each time it sets a sublevel's layout it plays a short
sound (the "GO" from 2-player battle's card slot, as Meeo's set-seed code does).</p>
<div class="card">
<div class="pick">
<label class="field"><span>Game version</span><select id="version"></select></label>
<label class="field"><span>Run</span><select id="run"></select></label>
</div>
<p id="summary"></p>
<textarea id="code" rows="12" readonly aria-label="Gecko code"></textarea>
<div class="buttons"><button class="primary" id="copy">Copy code</button>
<button id="gct">Download .gct</button><span id="copied" role="status" aria-live="polite"></span></div>
</div>

<h2>Using it</h2>
<p><b>Dolphin</b>: right-click the game, Properties, Gecko Codes, Add New Code; paste the code (the first line, starting
with $, is its name), save, and tick it. Cheats must be on: Config, General, Enable Cheats. Then start the game.</p>
<p><b>Nintendont</b> (Wii or Wii U): download the .gct and copy it to <code>codes/<span id="gameid">GPVE01</span>.gct</code> on
your SD card or USB drive, then turn on Cheats in Nintendont's settings. On a Wii, the Wii version's .gct works with
a cheat-code loader such as Gecko OS or USB Loader GX. Nintendont keeps cheats in a small space, so a
run with many sublevels can be too long for it.</p>
<p>The layout is set each time the sublevel is made, so dying, leaving and re-entering, or reloading the cave gives the
same layout again. Where the runner went through a sublevel more than once (All Treasures runners farm purple Pikmin
in Bulblax Kingdom first), it is the layout of their first visit. Only the layout is fixed: enemies, eggs and anything else random after the sublevel loads behave as
usual.</p>

<h2>Sublevels in this code</h2>
<div class="tablewrap"><table><tbody id="rows"></tbody></table></div>

<h2>Versions</h2>
<p>The versions marked untested use addresses from the <a href="https://github.com/projectPiki/pikmin2">Pikmin 2
decompilation</a>'s symbol maps; the USA release and the USA demo 1 build were also checked against real copies of
the game. The Wii version (New Play Control!) has no decompilation; its addresses were found in a memory dump of the
USA game and checked against an unmodified copy. If an untested one doesn't work for you, please say so in the suggestion box. Not supported:</p>
<ul>{unsupported}</ul>

<details><summary>How it works</summary>
<p>Pikmin 2 makes each sublevel from its global random number generator. This code hooks
<code>MapUnitGenerator::createMapPartsList</code> (on both GameCube and Wii), just before the game's first draw for the layout (the same place
as Meeo's set-seed code, whose seeds CaveGen uses). There it reads the cave and floor from the story mode section
and, if the run has a seed for that sublevel, writes it into the generator's state and plays the sound. Seeds are the layout seeds this
site shows on each run's page; the CaveGen3 links show what each one should look like. Details:
<a href="https://github.com/JHawk4/pikmin2-layout-ledger/blob/main/docs/gecko-code.md">docs/gecko-code.md</a>.</p>
</details>
</main>
<script type="application/json" id="gecko-versions">{data(versions_data())}</script>
<script type="application/json" id="gecko-runs">{data(runs)}</script>
<script>{JS}{PAGE_JS}</script>
</body></html>"""
