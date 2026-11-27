"""Japanese for the site, switched in the browser (like CaveGen3's English/Japanese switch).

The pages are written in English. Each page loads i18n.js (from the site root), which, when the
reader picks Japanese, walks the page and swaps every piece of English it knows for Japanese,
and keeps doing so for text the page's own scripts add later (chart tooltips, the Gecko code
page). One copy of each page means links, charts and the three sections work the same in both
languages, and pages built by a slow step (the detection pages) are translated without being
rebuilt.

What is looked up: a "phrase", the contents of an element that holds text directly and only
inline markup inside (a paragraph with its links and bold words, a table cell, a heading), as
HTML with the tags' attributes left out; or, where an element mixes text with blocks, each piece
of text on its own; and the title, aria-label, placeholder, alt and data-tip attributes. Every
number becomes a {0}, {1}, ... placeholder, so "12 of 15" and "3 of 9" are one entry ("{0} of
{1}"), and the translation can put the numbers in any order. A tooltip line that is not found
whole is tried piece by piece between " · " separators. Treasure names are swapped for the
game's Japanese names wherever they appear.

The table is ja_table.py (T: english key -> japanese, KEEP: keys left in English on purpose).
`missing()` lists the phrases of some built pages that are in neither (the tests run it), and
`python -m p2seeds i18n <folder>` prints them, ready to translate.

Language choice: ?lang=ja or ?lang=en in the URL, then the reader's last choice (also CaveGen3's,
the same site origin), then the browser's language.
"""

from __future__ import annotations

import html
import json
import re
from html.parser import HTMLParser
from pathlib import Path

DATA = Path(__file__).parent.parent / "data"

# Cave codes as the site writes them ("SH 6"); kept as they are in Japanese.
CODES = ("SCx", "HoB", "WFG", "CoS", "CoC", "HoH", "EC", "FC", "BK", "SH", "GK", "SR", "SC", "DD")
INLINE = {"a", "abbr", "b", "bdi", "br", "cite", "code", "em", "i", "img", "input", "kbd", "mark", "q", "s", "small",
          "span", "strong", "sub", "sup", "time", "u", "wbr"}
VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}
SKIP = {"script", "style", "pre", "textarea", "noscript", "template", "code", "kbd"}
OPAQUE = {"code", "kbd"}           # inside a phrase: shown as an empty tag, their contents kept as they are
ATTRS = ("title", "aria-label", "placeholder", "alt", "label", "data-tip")


def names() -> tuple[dict[str, str], dict[str, str]]:
    """(English treasure and cave names, CaveGen's internal treasure names with spaces for
    underscores as some tooltips show them) -> the game's Japanese names (from CaveGen3)."""
    d = json.loads((DATA / "names_ja.json").read_text(encoding="utf-8"))
    return {**d["treasures"], **d["caves"]}, d["internal"]


def _rx_escape(s: str) -> str:          # an escape both Python and JavaScript read the same way
    return re.sub(r"[.*+?^${}()|\[\]\/]", lambda m: "\\" + m.group(0), s)


def _alts(words) -> str:
    return "|".join(_rx_escape(w) for w in sorted(set(words), key=len, reverse=True))


class Lexicon:
    """What becomes a placeholder: a known name (treasure, cave; an internal treasure name only
    before " (12)" or " or ", as some words are English too; a runner), a cave code, a seed ("0x1A2B3C4D",
    "1A2B3C4D") or a number not inside a word ("12", "+1.5", "1:30:25", "1,000"). Names are
    swapped for Japanese when filled in; everything else is kept. i18n.js runs the same pattern."""

    # (kind, before, after): the guards around each list of names, in the order they are tried
    GUARDS = (("names", "(?<![A-Za-z])", "(?![A-Za-z])"),
              ("internal", "(?<![A-Za-z])", r"(?= \(\d| or )"),
              ("runners", "(?<![A-Za-z0-9_])", "(?![A-Za-z0-9_])"))
    BASE = "|".join([f"(?<![A-Za-z0-9_])(?:{'|'.join(CODES)})(?![A-Za-z0-9_])",
                     r"(?<![A-Za-z0-9_])(?:0x[0-9A-Fa-f]+|(?=[A-F]*[0-9])[0-9A-F]{8})(?![A-Za-z0-9_])",
                     r"(?<![A-Za-z0-9_.])[+\-−]?\d+(?:[.,:]\d+)*(?![A-Za-z0-9_])"])

    def __init__(self, runners=()):
        self.names, internal = names()
        self.runners = sorted({r for r in runners if r and re.search(r"[A-Za-z]", r)})
        self.ja = {**internal, **self.names}
        self.lists = {"names": sorted(self.names), "internal": sorted(internal), "runners": self.runners}
        parts = [f"{before}(?:{_alts(self.lists[kind])}){after}" for kind, before, after in self.GUARDS if self.lists[kind]]
        self.source = "|".join(parts + [self.BASE])
        self.rx = re.compile(self.source)

    def template(self, s: str) -> tuple[str, list[str]]:
        """Whitespace collapsed, the parts above replaced by {0}, {1}, ...; and those parts."""
        s = re.sub(r"\s+", " ", s).strip()
        nums: list[str] = []

        def put(m):
            nums.append(m.group(0))
            return "{%d}" % (len(nums) - 1)
        return self.rx.sub(put, s), nums


LEX = Lexicon()


def template(s: str, lex: Lexicon | None = None) -> tuple[str, list[str]]:
    return (lex or LEX).template(s)


# ---- A small DOM, enough to walk the generated pages the way i18n.js walks them in the browser ----

class Node:
    __slots__ = ("tag", "attrs", "children", "parent")

    def __init__(self, tag, attrs=None, parent=None):
        self.tag, self.attrs, self.children, self.parent = tag, dict(attrs or {}), [], parent


class _Builder(HTMLParser):
    AUTO_CLOSE = {"li": {"li"}, "td": {"td", "th"}, "th": {"td", "th"}, "tr": {"tr", "td", "th"}, "p": {"p"},
                  "option": {"option"}, "dt": {"dt", "dd"}, "dd": {"dt", "dd"}}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = Node("#root")
        self.cur = self.root

    def handle_starttag(self, tag, attrs):
        closes = self.AUTO_CLOSE.get(tag)
        if closes:
            n = self.cur
            while n is not self.root and n.tag not in ("table", "ul", "ol", "dl", "select", "tbody", "thead"):
                if n.tag in closes:
                    self.cur = n.parent
                    break
                n = n.parent
        node = Node(tag, [(k, v or "") for k, v in attrs], self.cur)
        self.cur.children.append(node)
        if tag not in VOID:
            self.cur = node

    def handle_startendtag(self, tag, attrs):
        node = Node(tag, [(k, v or "") for k, v in attrs], self.cur)
        self.cur.children.append(node)

    def handle_endtag(self, tag):
        n = self.cur
        while n is not self.root and n.tag != tag:
            n = n.parent
        if n is not self.root:
            self.cur = n.parent

    def handle_data(self, data):
        self.cur.children.append(data)


def parse(page: str) -> Node:
    b = _Builder()
    b.feed(page)
    b.close()
    return b.root


def _skipped(n: Node) -> bool:
    return n.tag in SKIP or n.attrs.get("translate") == "no" or "notranslate" in n.attrs.get("class", "").split()


def _all_inline(n: Node) -> bool:
    return all(isinstance(c, str) or (c.tag in INLINE and (c.tag in OPAQUE or _all_inline(c))) for c in n.children)


def is_phrase(n: Node) -> bool:
    return any(isinstance(c, str) and c.strip() for c in n.children) and _all_inline(n)


def phrase_html(n: Node) -> str:
    """The element's contents as the table writes them: tags without attributes, code emptied."""
    out = []
    for c in n.children:
        if isinstance(c, str):
            out.append(html.escape(c, quote=False))
        elif c.tag in VOID:
            out.append(f"<{c.tag}>")
        elif c.tag in OPAQUE or _skipped(c):
            out.append(f"<{c.tag}></{c.tag}>")
        else:
            out.append(f"<{c.tag}>{phrase_html(c)}</{c.tag}>")
    return "".join(out)


WORD = r"(?<![A-Za-z0-9_])[A-Za-z]{2,}(?![A-Za-z0-9_])"
UNWORDED = r"<[^>]*>|\{\d+\}|https?://\S+"


def _wanted(key: str) -> bool:
    """Anything with a word in it; numbers, symbols, single letters, links and names_like_this need nothing."""
    return bool(re.search(WORD, re.sub(UNWORDED, " ", key)))


def phrases(page: str, lex: Lexicon | None = None) -> list[tuple[str, str]]:
    """(kind, key) for every piece of English on a page, in the order i18n.js meets them:
    kind is "phrase", "text" (text beside blocks) or "attr" (an attribute value; data-tip line by line)."""
    found: list[tuple[str, str]] = []

    def attrs(n: Node):
        for a in ATTRS:
            v = n.attrs.get(a)
            if v:
                for line in (v.split("\n") if a == "data-tip" else [v]):
                    k = template(line, lex)[0]
                    if _wanted(k):
                        found.append(("attr", k))

    def walk(n: Node):
        if not isinstance(n, Node) or _skipped(n):
            return
        attrs(n)
        if n.tag != "#root" and is_phrase(n):
            k = template(phrase_html(n), lex)[0]
            if _wanted(k):
                found.append(("phrase", k))
            for d in _descendants(n):
                attrs(d)
            return
        for c in n.children:
            if isinstance(c, str):
                k = template(c, lex)[0]
                if c.strip() and _wanted(k) and n.tag not in ("#root", "html", "head"):
                    found.append(("text", k))
            else:
                walk(c)
    walk(parse(page))
    return found


def _descendants(n: Node):
    for c in n.children:
        if isinstance(c, Node):
            yield c
            yield from _descendants(c)


# ---- The table ----

def load() -> dict:
    from . import ja_table
    return {"t": dict(ja_table.T), "keep": list(ja_table.KEEP)}


def covered(key: str, table: dict) -> bool:
    """Would i18n.js translate this key (or is it meant to stay English)? A key with no words
    left needs nothing (its names are swapped on their own)."""
    t, keep = table["t"], set(table["keep"])
    if key in t or key in keep or not _wanted(key):
        return True
    if " · " in key:          # i18n.js translates what it can of a tooltip line, each part on its own
        return all(p in t or p in keep or not _wanted(p) for p in map(_renumber, key.split(" · ")))
    parts = re.split(SPLIT, key)      # a list of known notes: all of them, or none
    return len(parts) > 1 and all(_renumber(p) in t for p in parts)


def _renumber(part: str) -> str:
    """A piece of a key with its placeholders counted from {0} again, as i18n.js templates it."""
    n = iter(range(1000))
    return re.sub(r"\{\d+\}", lambda m: "{%d}" % next(n), part)


# Where a list of notes (the detection pages' notes, "; "-joined readings) splits; joined again with "、".
SPLIT = r", (?![^(]*\))|; | (?=seed confirmed|seed found|\(its own read|\(a linked seed)"


def missing(pages: list[str], table: dict | None = None, lex: Lexicon | None = None) -> list[str]:
    """Keys on these pages that i18n.js would leave in English, without a "keep" entry, once each."""
    table = table or load()
    out: dict[str, None] = {}
    for page in pages:
        for _, k in phrases(page, lex):
            if not covered(k, table):
                out.setdefault(k)
    return list(out)


def site_pages(root: Path) -> list[Path]:
    return sorted(p for p in Path(root).rglob("*.html"))


# ---- In the browser ----

def js(table: dict | None = None, lex: Lexicon | None = None) -> str:
    """i18n.js: the table and the code that applies it."""
    table, lex = table or load(), lex or LEX
    data = json.dumps({"t": table["t"], "names": lex.ja, "lists": lex.lists, "guards": Lexicon.GUARDS, "base": lex.BASE,
                       "runners": lex.runners, "keep": table["keep"],
                       "split": SPLIT, "word": WORD, "unworded": UNWORDED}, ensure_ascii=False, separators=(",", ":"))
    return RUNTIME.replace("/*TABLE*/null", data)


def write_js(dest: Path, runners=()) -> Path:
    """i18n.js at `dest`; `runners` (the runners' names) are kept as they are wherever they appear."""
    dest = Path(dest)
    dest.write_text(js(lex=Lexicon(runners)), encoding="utf-8")
    return dest


def js_data(path: Path) -> dict:
    """The data a written i18n.js carries (to check its site's pages with the same runners)."""
    text = Path(path).read_text(encoding="utf-8")
    start = text.index("const DATA = ") + len("const DATA = ")
    return json.JSONDecoder().raw_decode(text[start:])[0]


def check(root: Path, table: dict | None = None) -> list[str]:
    """Missing keys over a built site folder (one with i18n.js at its top)."""
    root = Path(root)
    js_file = root / "i18n.js"
    lex = Lexicon(js_data(js_file)["runners"] if js_file.exists() else ())
    return missing([p.read_text(encoding="utf-8") for p in site_pages(root)], table, lex)


# The header's part: the switch, and a script that hides the page until it is in Japanese (no
# flash of English), with i18n.js loaded at the end of parsing. `root` leads to the site root.
def header_html(root: str) -> str:
    return (f'<button type="button" id="lang-toggle" class="lang-toggle" lang="ja" title="日本語で表示">日本語</button>'
            '<style>html.i18n-wait body{visibility:hidden}'
            '.lang-toggle{margin-left:auto;font:inherit;font-size:.88rem;font-weight:700;color:var(--accent,#3c8531);'
            'background:var(--card,#fff);border:2px solid var(--accent,#3c8531);border-radius:999px;padding:1px 12px;'
            'min-height:30px;cursor:pointer}.lang-toggle:hover{background:var(--goodbg,#e3f1dc)}</style>'
            '<script>(function(){var l=null;try{var q=new URLSearchParams(location.search).get("lang");'
            'l=q==="ja"||q==="en"?q:localStorage.getItem("ledger-lang")||localStorage.getItem("cavegen3-lang");}catch(e){}'
            'if(l!=="ja"&&l!=="en")l=(navigator.language||"").toLowerCase().indexOf("ja")===0?"ja":"en";'
            'if(l==="ja"){var h=document.documentElement;h.classList.add("i18n-wait");h.lang="ja";'
            'setTimeout(function(){h.classList.remove("i18n-wait")},3000);}})();</script>'
            f'<script src="{root}i18n.js" defer></script>')


def add_switch(page: str, root: str) -> str:
    """A themed page built before the switch existed, with it added to the end of its header."""
    if 'id="lang-toggle"' in page or '<header class="site-header">' not in page:
        return page
    return page.replace("</header>", header_html(root) + "</header>", 1)


RUNTIME = r"""// Japanese for the Pikmin 2 Layout Ledger. Built by p2seeds/i18n.py; see there for how it works.
(() => {
const DATA = /*TABLE*/null;
const T = DATA.t;
// The placeholder pattern (Lexicon in i18n.py). One regex over every name is slow here, so each
// string gets one over just the names whose first run of letters it contains: the same matches.
const firstRun = n => (n.match(/[A-Za-z]+/) || [""])[0];
const BY_RUN = {};
for (const [kind] of DATA.guards) for (const n of DATA.lists[kind]) ((BY_RUN[firstRun(n)] ||= {})[kind] ||= []).push(n);
const rxEscape = s => s.replace(/[.*+?^${}()|[\]\\\/]/g, "\\$&");
const tokenCache = new Map();
function tokenFor(s) {
  const found = {};
  for (const w of new Set(s.match(/[A-Za-z]+/g) || [])) {
    const by = BY_RUN[w];
    if (by) for (const kind in by) (found[kind] ||= []).push(...by[kind]);
  }
  const parts = [];
  for (const [kind, before, after] of DATA.guards) {
    if (!found[kind]) continue;
    const alts = [...new Set(found[kind])].sort((a, b) => b.length - a.length).map(rxEscape).join("|");
    parts.push(`${before}(?:${alts})${after}`);
  }
  const src = parts.concat([DATA.base]).join("|");
  if (!tokenCache.has(src)) tokenCache.set(src, new RegExp(src, "g"));
  return tokenCache.get(src);
}
const INLINE = new Set("a abbr b bdi br cite code em i img input kbd mark q s small span strong sub sup time u wbr".split(" "));
const VOID = new Set("area base br col embed hr img input link meta source track wbr".split(" "));
const SKIP = new Set("script style pre textarea noscript template code kbd".split(" "));
const OPAQUE = new Set(["code", "kbd"]);
const ATTRS = ["title", "aria-label", "placeholder", "alt", "label", "data-tip"];
const KEY = "ledger-lang";
const missing = window.__i18nMissing = new Set();      // English met that the table lacks (for checking)
const KEEP = new Set(DATA.keep);

function pickLanguage() {
  try {
    const q = new URLSearchParams(location.search).get("lang");
    if (q === "ja" || q === "en") return q;
    const saved = localStorage.getItem(KEY) || localStorage.getItem("cavegen3-lang");
    if (saved === "ja" || saved === "en") return saved;
  } catch (e) { /* storage unavailable: fall through */ }
  return (navigator.language || "").toLowerCase().startsWith("ja") ? "ja" : "en";
}

function template(s) {
  const nums = [];
  s = s.replace(/\s+/g, " ").trim();
  const key = s.replace(tokenFor(s), m => { nums.push(m); return "{" + (nums.length - 1) + "}"; });
  return [key, nums];
}
const fill = (ja, nums) => ja.replace(/\{(\d+)\}/g, (m, i) => +i < nums.length ? DATA.names[nums[+i]] ?? nums[+i] : m);
const named = nums => nums.some(n => n in DATA.names);
const WORD = new RegExp(DATA.word), UNWORDED = new RegExp(DATA.unworded, "g"), SPLIT = new RegExp(DATA.split);
const wanted = key => WORD.test(key.replace(UNWORDED, " "));

// A plain string (no markup) in Japanese, or null.
const memo = new Map();
function tr(s) {
  if (memo.has(s)) return memo.get(s);
  const j = tr0(s);
  if (memo.size < 50000) memo.set(s, j);
  return j;
}
function tr0(s) {
  const [key, nums] = template(s);
  if (key in T) return fill(T[key], nums);
  if (!wanted(key)) return named(nums) ? fill(key, nums) : null;      // only names: just those
  if (key.includes(" · ")) {
    const parts = s.replace(/\s+/g, " ").trim().split(" · ");
    if (parts.length === key.split(" · ").length) {
      let any = false;
      const out = parts.map(p => { const j = tr(p); if (j !== null) any = true; return j ?? p; });
      if (any) return out.join(" · ");
    }
  }
  const parts = s.replace(/\s+/g, " ").trim().split(SPLIT);      // a list of known notes: all of them, or none
  if (parts.length > 1) {
    const out = parts.map(p => { const [k, n] = template(p); return k in T ? fill(T[k], n) : null; });
    if (out.every(x => x !== null)) return out.join("、");
  }
  if (!KEEP.has(key)) missing.add(key);
  return null;
}

const skipped = el => SKIP.has(el.localName) || el.getAttribute("translate") === "no" || el.classList.contains("notranslate")
  || el.id === "lang-toggle";
function allInline(el) {
  for (const c of el.childNodes) {
    if (c.nodeType !== 1) continue;
    if (!INLINE.has(c.localName)) return false;
    if (!OPAQUE.has(c.localName) && !allInline(c)) return false;
  }
  return true;
}
const isPhrase = el => [...el.childNodes].some(c => c.nodeType === 3 && c.data.trim()) && allInline(el);
const esc = s => s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
function phraseHtml(el) {
  let out = "";
  for (const c of el.childNodes) {
    if (c.nodeType === 3) out += esc(c.data);
    else if (c.nodeType === 1) {
      const t = c.localName;
      if (VOID.has(t)) out += `<${t}>`;
      else if (OPAQUE.has(t) || skipped(c)) out += `<${t}></${t}>`;
      else out += `<${t}>${phraseHtml(c)}</${t}>`;
    }
  }
  return out;
}

function translateAttrs(el) {
  for (const a of ATTRS) {
    const v = el.getAttribute(a);
    if (!v) continue;
    const lines = a === "data-tip" ? v.split("\n") : [v];
    let changed = false;
    const out = lines.map(l => { const j = tr(l); if (j !== null && j !== l) changed = true; return j ?? l; });
    if (changed) el.setAttribute(a, out.join("\n"));
  }
}

// Put the Japanese phrase into `el`, reusing its own elements (links keep their href, inputs their
// listeners): the i-th <a> of the translation is the i-th <a> of the original, and so on.
function applyPhrase(el, ja) {
  const pools = {};
  el.querySelectorAll("*").forEach(d => (pools[d.localName] ||= []).push(d));
  const tpl = document.createElement("template");
  tpl.innerHTML = ja;
  const adopt = parent => {
    for (const c of [...parent.childNodes]) {
      if (c.nodeType !== 1) continue;
      const orig = (pools[c.localName] || []).shift();
      if (!orig) { adopt(c); continue; }
      if (OPAQUE.has(c.localName) || (VOID.has(c.localName))) { parent.replaceChild(orig, c); continue; }
      adopt(c);
      if (c.childNodes.length || !orig.childNodes.length) orig.replaceChildren(...c.childNodes);
      parent.replaceChild(orig, c);
    }
  };
  adopt(tpl.content);
  el.replaceChildren(tpl.content);
}

function walk(el) {
  if (skipped(el)) return;
  translateAttrs(el);
  if (el !== document.body && isPhrase(el)) {
    const [key, nums] = template(phraseHtml(el));
    const ja = key in T ? T[key] : !wanted(key) && named(nums) ? key : null;
    if (ja === null && !wanted(key)) { el.querySelectorAll("*").forEach(translateAttrs); return; }
    if (ja !== null) {
      applyPhrase(el, fill(ja, nums));
      el.querySelectorAll("*").forEach(translateAttrs);
      return;
    }
    if (!el.querySelector("*")) {            // plain text: the tooltip line and name fallbacks
      const j = tr(el.textContent);
      if (j !== null) el.textContent = j;
      return;
    }
    missing.add(key);
  }
  for (const c of [...el.childNodes]) {
    if (c.nodeType === 3) {
      if (!c.data.trim()) continue;
      const j = tr(c.data);
      if (j !== null) c.data = c.data.match(/^\s*/)[0] + j + c.data.match(/\s*$/)[0];
    } else if (c.nodeType === 1) walk(c);
  }
}

let lang = pickLanguage();
let observer = null;
let busy = false;

function translatePage() {
  const t0 = performance.now();
  busy = true;
  document.documentElement.lang = "ja";
  const title = tr(document.title);
  if (title) document.title = title;
  walk(document.body);
  busy = false;
  window.__i18nMs = performance.now() - t0;
  // text the page's own scripts add later: chart tooltips, readouts, the Gecko code page
  observer = new MutationObserver(records => {
    if (busy) return;
    busy = true;
    for (const r of records) {
      if (r.type === "characterData") {
        const n = r.target, p = n.parentElement;
        if (p && !p.closest("script,style,pre,textarea,code,kbd,.notranslate,[translate=no]")) {
          const j = tr(n.data);
          if (j !== null && j !== n.data) n.data = j;
        }
      } else for (const n of r.addedNodes) {
        if (n.nodeType === 1) {
          const p = n.parentElement;
          if (p && p.closest("script,style,pre,textarea,code,kbd,.notranslate,[translate=no]")) continue;
          walk(n);
        } else if (n.nodeType === 3 && n.data.trim() && n.parentElement && !n.parentElement.closest("script,style,pre,textarea,code,kbd")) {
          const p = n.parentElement;
          if (isPhrase(p) && p !== document.body) walk(p);
          else { const j = tr(n.data); if (j !== null && j !== n.data) n.data = j; }
        }
      }
    }
    observer.takeRecords();
    busy = false;
  });
  observer.observe(document.body, { subtree: true, childList: true, characterData: true });
}

function setLanguage(next) {
  try { localStorage.setItem(KEY, next); } catch (e) { /* not saved; this page still switches */ }
  const p = new URLSearchParams(location.search);
  if (p.has("lang")) { p.set("lang", next); history.replaceState(null, "", "?" + p.toString() + location.hash); }
  if (next === "en") { location.reload(); return; }      // the page as written
  lang = next;
  translatePage();
  updateToggle();
}

function updateToggle() {
  const b = document.getElementById("lang-toggle");
  if (!b) return;
  b.textContent = lang === "ja" ? "English" : "日本語";
  b.lang = lang === "ja" ? "en" : "ja";
  b.title = lang === "ja" ? "Show in English" : "日本語で表示";
}

function start() {
  const b = document.getElementById("lang-toggle");
  if (b) b.addEventListener("click", () => setLanguage(lang === "ja" ? "en" : "ja"));
  if (lang === "ja") {
    try { translatePage(); } finally { document.documentElement.classList.remove("i18n-wait"); }
  } else {
    document.documentElement.lang = "en";
    document.documentElement.classList.remove("i18n-wait");
  }
  updateToggle();
}
window.ledgerI18n = { tr, template, walk, setLanguage, get lang() { return lang; } };
if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start); else start();
})();
"""
