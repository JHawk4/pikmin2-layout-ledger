"""Recover Pikmin 2 seeds from speedrun videos: story mode and Challenge Mode.

The package is organised by approach:

- core (this folder): the RNG (`rng`), caves, the CaveGen / CaveGen3 bridges (`cavegen`, `cg3`,
  `views`), video and feed detection, and the command line (`cli`);
- `story`: story-mode falling letters (entry screens, letter tracking, seed search, the RNG chain,
  route rescue, treasures, the per-run report);
- `challenge`: Challenge Mode (the stage-select Pikmin dive, the results-screen score roll);
- `ledger`: the report site (pages, judge, luck, charts, theme, Japanese, Gecko code).

Modules used to sit flat in this folder; the old names (`p2seeds.chain`, `p2seeds.challenge_dive`,
...) still import, as the very same module objects as their new homes.
"""

import importlib
import importlib.abc
import importlib.util
import sys

# old flat name -> new home (relative to this package)
ALIASES = {
    "analyze": "story.analyze",
    "calibrate": "story.calibrate",
    "chain": "story.chain",
    "challenge_dive": "challenge.dive",
    "challenge_results": "challenge.results",
    "charts": "ledger.charts",
    "debug": "story.debug",
    "details": "story.details",
    "digits": "story.digits",
    "dive_detect": "challenge.dive_detect",
    "dive_rgb": "challenge.dive_rgb",
    "egg": "story.egg",
    "events": "story.events",
    "fit": "story.fit",
    "gecko": "ledger.gecko",
    "gecko_page": "ledger.gecko_page",
    "i18n": "ledger.i18n",
    "ja_table": "ledger.ja_table",
    "judge2": "ledger.judge2",
    "judge_page": "ledger.judge_page",
    "judge_report": "ledger.judge_report",
    "lattice": "story.lattice",
    "letters_model": "story.letters_model",
    "live": "story.live",
    "luck": "ledger.luck",
    "redo": "story.redo",
    "report": "story.report",
    "route_rescue": "story.route_rescue",
    "run_page": "ledger.run_page",
    "search": "story.search",
    "site": "ledger.site",
    "sublevels": "story.sublevels",
    "synth": "story.synth",
    "templates": "story.templates",
    "theme": "ledger.theme",
    "track": "story.track",
    "treasures": "story.treasures",
}


class _Alias(importlib.abc.MetaPathFinder, importlib.abc.Loader):
    """`p2seeds.<old>` resolves to the module at its new home (one module object under both names)."""

    def find_spec(self, fullname, path=None, target=None):
        head, _, old = fullname.rpartition(".")
        if head != __name__ or old not in ALIASES:
            return None
        return importlib.util.spec_from_loader(fullname, self)

    def _target(self, fullname):
        return f"{__name__}.{ALIASES[fullname.rpartition('.')[2]]}"

    def create_module(self, spec):
        return importlib.import_module(self._target(spec.name))

    def exec_module(self, module):
        pass                                     # already executed under its new name

    def get_code(self, fullname):                # `python -m p2seeds.<old>`: run the new home instead
        src = f"import runpy\nrunpy.run_module({self._target(fullname)!r}, run_name='__main__', alter_sys=True)\n"
        return compile(src, f"<{fullname}>", "exec")


if not any(isinstance(f, _Alias) for f in sys.meta_path):
    sys.meta_path.append(_Alias())
