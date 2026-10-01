"""Configuration: paths, limits, and their environment-variable overrides.

Every value has a default. Set an environment variable to override it.

| Setting          | Env var                    | Default                     |
|------------------|----------------------------|-----------------------------|
| Database file    | KNOWLEDGE_MCP_DB           | ~/.knowledge-mcp/ideas.db   |
| Frameworks folder| KNOWLEDGE_MCP_FRAMEWORKS   | <repo>/frameworks           |
| Plugin modules   | KNOWLEDGE_MCP_PLUGINS      | (none)                      |

KNOWLEDGE_MCP_PLUGINS is a comma-separated list of Python module names
(`my_tools.extra`) or paths to .py files (`~/my-tools/extra.py`).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

DEFAULT_DB_PATH = Path.home() / ".knowledge-mcp" / "ideas.db"
DEFAULT_FRAMEWORKS_DIR = REPO_ROOT / "frameworks"
SEED_FILE = REPO_ROOT / "seed" / "sample_ideas.json"

# Input limits (HANDOFF Section 5, rule 2).
MAX_TITLE = 200
MIN_TITLE = 3
MAX_TEXT = 20_000
MAX_DOMAIN = 100
MAX_TAGS = 20
MAX_TAG_LENGTH = 50
MAX_QUERY = 500
MAX_LIMIT = 100
MAX_FRAMEWORK_BYTES = 200_000

STATUSES = ("seed", "developing", "mature", "published", "archived")


@dataclass(frozen=True)
class Settings:
    db_path: Path
    frameworks_dir: Path
    plugins: tuple[str, ...] = ()


def load_settings() -> Settings:
    """Read settings from the environment, falling back to defaults."""
    db = os.environ.get("KNOWLEDGE_MCP_DB")
    fw = os.environ.get("KNOWLEDGE_MCP_FRAMEWORKS")
    plugins = os.environ.get("KNOWLEDGE_MCP_PLUGINS", "")
    return Settings(
        db_path=Path(db).expanduser() if db else DEFAULT_DB_PATH,
        frameworks_dir=Path(fw).expanduser() if fw else DEFAULT_FRAMEWORKS_DIR,
        plugins=tuple(p.strip() for p in plugins.split(",") if p.strip()),
    )
