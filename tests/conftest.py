"""Shared fixtures: every test gets its own throwaway database."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest

from knowledge_mcp import config, db


@pytest.fixture(autouse=True)
def isolated_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point KNOWLEDGE_MCP_DB at a temp file so no test can touch a real database."""
    path = tmp_path / "ideas.db"
    monkeypatch.setenv("KNOWLEDGE_MCP_DB", str(path))
    return path


@pytest.fixture
def conn(isolated_env: Path) -> Iterator[sqlite3.Connection]:
    connection = db.connect(isolated_env)
    yield connection
    connection.close()


@pytest.fixture
def seeded(conn: sqlite3.Connection) -> sqlite3.Connection:
    db.seed_ideas(conn, db.load_seed_file(config.SEED_FILE))
    return conn
