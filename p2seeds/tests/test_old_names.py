"""The flat module names from before the story/challenge/ledger split still import (p2seeds.ALIASES)."""

import importlib
import subprocess
import sys

import pytest

import p2seeds


@pytest.mark.parametrize("old", sorted(p2seeds.ALIASES))
def test_old_name_is_the_new_module(old):
    new = importlib.import_module(f"p2seeds.{p2seeds.ALIASES[old]}")
    assert importlib.import_module(f"p2seeds.{old}") is new
    assert getattr(p2seeds, old) is new


def test_from_import_and_attributes():
    from p2seeds import challenge_dive, chain
    from p2seeds.challenge import dive
    from p2seeds.story import chain as story_chain

    assert challenge_dive is dive and chain is story_chain
    from p2seeds.chain import link  # noqa: F401  (a name inside an old module)


def test_run_old_name_as_main():
    out = subprocess.run([sys.executable, "-m", "p2seeds.live", "--help"], capture_output=True, text=True)
    assert out.returncode == 0 and "--render" in out.stdout
