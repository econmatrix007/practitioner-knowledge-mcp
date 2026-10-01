"""Scaffold smoke tests: the package installs and imports."""

import knowledge_mcp
from knowledge_mcp.__main__ import main


def test_version_is_set() -> None:
    assert knowledge_mcp.__version__ != "0.0.0"


def test_entry_point_runs() -> None:
    assert main() == 0
