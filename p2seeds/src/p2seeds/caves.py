"""Story-mode caves: names as shown on the entry screen, CaveGen ids, sublevel counts."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Cave:
    name: str        # exactly as the falling letters spell it (English)
    cavegen: str     # CaveGen's short name, e.g. "WFG"
    sublevels: int

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

BY_NAME = {c.name.lower(): c for c in CAVES}
BY_ID = {c.cavegen.lower(): c for c in CAVES}


def get(name_or_id: str) -> Cave:
    key = name_or_id.strip().lower()
    return BY_NAME.get(key) or BY_ID[key]
