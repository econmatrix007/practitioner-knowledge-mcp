#!/bin/bash
# Back up the ideas database safely, even while the server is running.
#
# Usage:
#   scripts/backup_db.sh [--keep N]
#
# Copies KNOWLEDGE_MCP_DB (default ~/.knowledge-mcp/ideas.db) with SQLite's
# online backup API, checks the copy with PRAGMA integrity_check, and keeps the
# newest N backups (default 12) in KNOWLEDGE_MCP_BACKUP_DIR (default
# ~/.knowledge-mcp/backups). Exits non-zero if the copy fails its check.
# Compatible with the bash 3.2 that ships with macOS.

set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON="$REPO/.venv/bin/python"
KEEP=12

while [ $# -gt 0 ]; do
  case "$1" in
    --keep) KEEP="${2:?--keep needs a number}"; shift 2 ;;
    -h|--help) sed -n '2,12p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "Error: unknown option: $1" >&2; exit 1 ;;
  esac
done
case "$KEEP" in ''|*[!0-9]*) echo "Error: --keep must be a whole number" >&2; exit 1 ;; esac
[ "$KEEP" -ge 1 ] || { echo "Error: --keep must be at least 1" >&2; exit 1; }
[ -x "$PYTHON" ] || { echo "Error: run 'make install' first." >&2; exit 1; }

KEEP="$KEEP" "$PYTHON" - <<'PY'
import os
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

db = Path(os.environ.get("KNOWLEDGE_MCP_DB") or "~/.knowledge-mcp/ideas.db").expanduser()
dest_dir = Path(os.environ.get("KNOWLEDGE_MCP_BACKUP_DIR") or "~/.knowledge-mcp/backups").expanduser()
keep = int(os.environ["KEEP"])

if not db.is_file():
    sys.exit(f"Error: no database at {db}")
dest_dir.mkdir(parents=True, exist_ok=True)
dest_dir.chmod(0o700)
stamp = datetime.now().strftime("%Y-%m-%d-%H%M%S")
dest = dest_dir / f"{db.stem}-{stamp}.db"
partial = dest.with_suffix(".db.partial")

source = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
target = sqlite3.connect(partial)
try:
    source.backup(target)  # consistent snapshot, safe while the server writes
    result = target.execute("PRAGMA integrity_check").fetchone()[0]
    count = target.execute("SELECT COUNT(*) FROM ideas").fetchone()[0]
finally:
    target.close()
    source.close()
if result != "ok":
    partial.unlink(missing_ok=True)
    sys.exit(f"Error: backup failed its integrity check ({result}). Nothing was kept.")
partial.chmod(0o600)
partial.rename(dest)

backups = sorted(dest_dir.glob(f"{db.stem}-*.db"))
for old in backups[:-keep]:
    old.unlink()
size_kb = dest.stat().st_size / 1024
print(f"Backup OK: {dest} ({count} ideas, {size_kb:.0f} KB, integrity ok)")
print(f"Keeping {min(len(backups), keep)} of the newest backups in {dest_dir}")
PY
