"""Story-mode caves: names as shown on the entry screen, CaveGen ids, sublevel counts.

Each cave appears once per game language. The Japanese names come from CaveGen's
files/jp_cave_names.txt; every character, kana or kanji, falls as one letter.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Cave:
    name: str        # exactly as the falling letters spell it
    cavegen: str     # CaveGen's short name, e.g. "WFG"
    sublevels: int
    lang: str = "en"
    english: str = ""  # English name, for display (defaults to `name`)

    @property
    def label(self) -> str:
        return self.english or self.name

    @property
    def num_chars(self) -> int:
        return len(self.name)

    @property
    def is_space(self) -> list[bool]:
        return [ch == " " for ch in self.name]


CAVES = [
    Cave("Emergence Cave", "EC", 2),
    Cave("Subterranean Complex", "SCx", 9),
    Cave("Frontier Cavern", "FC", 8),
    Cave("Hole of Beasts", "HoB", 5),
    Cave("White Flower Garden", "WFG", 5),
    Cave("Bulblax Kingdom", "BK", 7),
    Cave("Snagret Hole", "SH", 7),
    Cave("Citadel of Spiders", "CoS", 5),
    Cave("Glutton's Kitchen", "GK", 6),
    Cave("Shower Room", "SR", 7),
    Cave("Submerged Castle", "SC", 5),
    Cave("Cavern of Chaos", "CoC", 10),
    Cave("Hole of Heroes", "HoH", 15),
    Cave("Dream Den", "DD", 14),
]

_JA = {
    "EC": "始まりの洞窟", "HoB": "けだものの穴", "CoS": "クモの根城", "WFG": "白い花園",
    "SCx": "地下の秘密基地", "FC": "辺境の洞窟", "BK": "デメマダラの王国", "GK": "食神の台所",
    "SR": "シャワールーム", "SH": "ヘビガラスの穴", "SC": "水中の城", "CoC": "混沌の魔窟",
    "HoH": "百戦錬磨の穴", "DD": "夢の穴",
}
CAVES_EN = list(CAVES)
CAVES_JA = [Cave(_JA[c.cavegen], c.cavegen, c.sublevels, "ja", c.name) for c in CAVES_EN]
CAVES = CAVES_EN + CAVES_JA

BY_NAME = {c.name.lower(): c for c in CAVES}
BY_ID = {c.cavegen.lower(): c for c in CAVES_EN}


def get(name_or_id: str) -> Cave:
    key = name_or_id.strip().lower()
    return BY_NAME.get(key) or BY_ID[key]
