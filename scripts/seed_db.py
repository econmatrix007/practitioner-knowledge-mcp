"""Load the fictional sample ideas into the database.

Usage:
    uv run python scripts/seed_db.py [path/to/ideas.json]

Defaults to seed/sample_ideas.json. Ideas whose title and domain already exist
are skipped, so running this twice never creates duplicates.
"""

from __future__ import annotations

import sys
from pathlib import Path

from knowledge_mcp import config, db


def main(argv: list[str]) -> int:
    seed_path = Path(argv[1]) if len(argv) > 1 else config.SEED_FILE
    settings = config.load_settings()
    try:
        records = db.load_seed_file(seed_path)
        conn = db.connect(settings.db_path)
        result = db.seed_ideas(conn, records)
        total = conn.execute("SELECT COUNT(*) FROM ideas").fetchone()[0]
        conn.close()
    except (OSError, ValueError, KeyError) as exc:
        print(f"Seeding failed: {exc}", file=sys.stderr)
        return 1
    print(f"Seeded {settings.db_path} from {seed_path.name}")
    print(f"Inserted: {result['inserted']}. Skipped (already present): {result['skipped']}.")
    print(f"Ideas stored: {total}.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
