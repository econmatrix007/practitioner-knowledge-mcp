"""Create the ideas database (or upgrade it to the latest schema).

Usage:
    uv run python scripts/init_db.py

Uses KNOWLEDGE_MCP_DB if set, otherwise ~/.knowledge-mcp/ideas.db.
Safe to run more than once: existing data is never touched.
"""

from __future__ import annotations

import sys

from knowledge_mcp import config, db


def main() -> int:
    settings = config.load_settings()
    conn = db.connect(settings.db_path)
    version = db.schema_version(conn)
    count = conn.execute("SELECT COUNT(*) FROM ideas").fetchone()[0]
    conn.close()
    print(f"Database ready: {settings.db_path}")
    print(f"Schema version: {version}. Ideas stored: {count}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
