"""backup_db.sh: consistent copy, integrity check, pruning, private permissions."""

from __future__ import annotations

import os
import sqlite3
import stat
import subprocess
from pathlib import Path

import pytest

from knowledge_mcp import config, db

SCRIPT = config.REPO_ROOT / "scripts" / "backup_db.sh"


def run(db_path: Path, backups: Path, *args: str) -> subprocess.CompletedProcess[str]:
    env = {
        **os.environ,
        "KNOWLEDGE_MCP_DB": str(db_path),
        "KNOWLEDGE_MCP_BACKUP_DIR": str(backups),
    }
    return subprocess.run(  # noqa: S603 - fixed repo script
        ["/bin/bash", str(SCRIPT), *args], env=env, capture_output=True, text=True, check=False
    )


@pytest.fixture
def seeded_db(isolated_env: Path) -> Path:
    conn = db.connect(isolated_env)
    db.seed_ideas(conn, db.load_seed_file(config.SEED_FILE))
    conn.close()
    return isolated_env


def test_backup_is_complete_and_private(seeded_db: Path, tmp_path: Path) -> None:
    backups = tmp_path / "backups"
    result = run(seeded_db, backups)
    assert result.returncode == 0, result.stderr
    assert "Backup OK" in result.stdout and "12 ideas" in result.stdout
    (copy,) = backups.glob("ideas-*.db")
    assert stat.S_IMODE(copy.stat().st_mode) == 0o600
    assert stat.S_IMODE(backups.stat().st_mode) == 0o700
    conn = sqlite3.connect(copy)
    assert conn.execute("SELECT COUNT(*) FROM ideas").fetchone()[0] == 12
    assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    conn.close()


def test_backup_while_a_connection_is_writing(seeded_db: Path, tmp_path: Path) -> None:
    writer = db.connect(seeded_db)  # WAL mode, like the live server
    writer.execute("UPDATE ideas SET status = 'mature' WHERE id = 2")
    writer.commit()
    result = run(seeded_db, tmp_path / "b")
    writer.close()
    assert result.returncode == 0, result.stderr
    (copy,) = (tmp_path / "b").glob("ideas-*.db")
    row = sqlite3.connect(copy).execute("SELECT status FROM ideas WHERE id = 2").fetchone()
    assert row[0] == "mature"  # committed WAL changes are in the backup


def test_keep_prunes_oldest(seeded_db: Path, tmp_path: Path) -> None:
    backups = tmp_path / "b"
    backups.mkdir()
    for day in ("01", "02", "03"):
        (backups / f"ideas-2020-01-{day}-000000.db").write_bytes(b"old")
    assert run(seeded_db, backups, "--keep", "2").returncode == 0
    names = sorted(p.name for p in backups.glob("ideas-*.db"))
    assert len(names) == 2
    assert names[0] == "ideas-2020-01-03-000000.db"  # newest old one kept, plus today's


@pytest.mark.parametrize("args", [("--keep", "x"), ("--keep", "0"), ("--bogus",)])
def test_bad_options_fail_clearly(seeded_db: Path, tmp_path: Path, args: tuple[str, ...]) -> None:
    result = run(seeded_db, tmp_path / "b", *args)
    assert result.returncode != 0 and "Error" in result.stderr
    assert "Traceback" not in result.stderr


def test_missing_database_fails_clearly(tmp_path: Path) -> None:
    result = run(tmp_path / "none.db", tmp_path / "b")
    assert result.returncode != 0 and "no database" in result.stderr
