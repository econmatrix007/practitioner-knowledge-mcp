"""Configuration: paths, limits, and their environment-variable overrides.

Every value has a default. Set an environment variable to override it.

| Setting                 | Env var                            | Default                   |
|-------------------------|------------------------------------|---------------------------|
| Database file           | KNOWLEDGE_MCP_DB                   | ~/.knowledge-mcp/ideas.db |
| Frameworks folder       | KNOWLEDGE_MCP_FRAMEWORKS           | <repo>/frameworks         |
| Plugin modules          | KNOWLEDGE_MCP_PLUGINS              | (none)                    |
| HTTP bind address       | KNOWLEDGE_MCP_HOST                 | 127.0.0.1                 |
| HTTP port               | KNOWLEDGE_MCP_PORT                 | 8765                      |
| Bearer token            | KNOWLEDGE_MCP_TOKEN                | (none: no token required) |
| Bearer token file       | KNOWLEDGE_MCP_TOKEN_FILE           | (none)                    |
| Extra allowed Host names| KNOWLEDGE_MCP_ALLOWED_HOSTS        | (none)                    |
| Allow 0.0.0.0 / ::      | KNOWLEDGE_MCP_ALLOW_ALL_INTERFACES | 0 (refuse)                |

KNOWLEDGE_MCP_PLUGINS is a comma-separated list of Python module names
(`my_tools.extra`) or paths to .py files (`~/my-tools/extra.py`).
KNOWLEDGE_MCP_ALLOWED_HOSTS is a comma-separated list of extra host names clients
may use to reach the HTTP server, such as a Tailscale name (`mini.example.ts.net`).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

DEFAULT_DB_PATH = Path.home() / ".knowledge-mcp" / "ideas.db"
DEFAULT_FRAMEWORKS_DIR = REPO_ROOT / "frameworks"
SEED_FILE = REPO_ROOT / "seed" / "sample_ideas.json"

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765
MIN_TOKEN_LENGTH = 24

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


class ConfigError(ValueError):
    """A setting is invalid. The message names the env var and is safe to show."""


@dataclass(frozen=True)
class Settings:
    db_path: Path
    frameworks_dir: Path
    plugins: tuple[str, ...] = ()
    host: str = DEFAULT_HOST
    port: int = DEFAULT_PORT
    token: str | None = None
    allowed_hosts: tuple[str, ...] = ()
    allow_all_interfaces: bool = False


def _csv(value: str) -> tuple[str, ...]:
    return tuple(p.strip() for p in value.split(",") if p.strip())


def _port(value: str | None) -> int:
    if not value:
        return DEFAULT_PORT
    if not value.isdigit() or not 1 <= int(value) <= 65535:
        raise ConfigError(f"KNOWLEDGE_MCP_PORT must be a number from 1 to 65535, not {value!r}.")
    return int(value)


def _token(value: str | None, file: str | None) -> str | None:
    if value and file:
        raise ConfigError("Set KNOWLEDGE_MCP_TOKEN or KNOWLEDGE_MCP_TOKEN_FILE, not both.")
    if file:
        path = Path(file).expanduser()
        try:
            value = path.read_text(encoding="utf-8").strip()
        except OSError as exc:
            raise ConfigError(f"Cannot read KNOWLEDGE_MCP_TOKEN_FILE ({path}): {exc}") from None
    if not value:
        return None
    value = value.strip()
    if len(value) < MIN_TOKEN_LENGTH:
        raise ConfigError(
            f"The bearer token must be at least {MIN_TOKEN_LENGTH} characters. "
            "Generate one with: python3 -c 'import secrets; print(secrets.token_urlsafe(32))'"
        )
    return value


def load_settings() -> Settings:
    """Read settings from the environment, falling back to defaults."""
    env = os.environ.get
    db = env("KNOWLEDGE_MCP_DB")
    fw = env("KNOWLEDGE_MCP_FRAMEWORKS")
    return Settings(
        db_path=Path(db).expanduser() if db else DEFAULT_DB_PATH,
        frameworks_dir=Path(fw).expanduser() if fw else DEFAULT_FRAMEWORKS_DIR,
        plugins=_csv(env("KNOWLEDGE_MCP_PLUGINS", "")),
        host=(env("KNOWLEDGE_MCP_HOST") or DEFAULT_HOST).strip(),
        port=_port(env("KNOWLEDGE_MCP_PORT")),
        token=_token(env("KNOWLEDGE_MCP_TOKEN"), env("KNOWLEDGE_MCP_TOKEN_FILE")),
        allowed_hosts=_csv(env("KNOWLEDGE_MCP_ALLOWED_HOSTS", "")),
        allow_all_interfaces=env("KNOWLEDGE_MCP_ALLOW_ALL_INTERFACES", "0").strip() == "1",
    )
