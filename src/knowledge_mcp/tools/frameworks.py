"""Two framework tools: list and get. Frameworks are Markdown files with YAML front matter.

Security: `get_framework` only serves names found by listing the frameworks folder.
It never builds a path from user input, rejects path separators and `..`, skips
symlinks and oversized files, and reads nothing outside that folder.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Annotated, Any

import yaml
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp_types import ToolAnnotations
from pydantic import Field

from knowledge_mcp import config
from knowledge_mcp.config import Settings

log = logging.getLogger(__name__)

READ_ONLY = ToolAnnotations(read_only_hint=True, open_world_hint=False)
META_FIELDS = ("name", "title", "category", "use_when")


def parse_framework(text: str) -> tuple[dict[str, Any], str]:
    """Split a Markdown file into (front matter, body). Missing front matter is allowed."""
    if text.startswith("---"):
        parts = text.split("\n---", 1)
        if len(parts) == 2:
            meta = yaml.safe_load(parts[0][3:]) or {}
            if isinstance(meta, dict):
                return meta, parts[1].lstrip("-").lstrip("\n")
    return {}, text


def load_frameworks(folder: Path) -> dict[str, dict[str, Any]]:
    """Read every top-level .md file in `folder`. Keys are file names without .md."""
    found: dict[str, dict[str, Any]] = {}
    if not folder.is_dir():
        log.warning("Frameworks folder not found: %s", folder)
        return found
    for path in sorted(folder.glob("*.md")):
        if path.is_symlink() or not path.is_file():
            continue
        if path.stat().st_size > config.MAX_FRAMEWORK_BYTES:
            log.warning("Skipping oversized framework file: %s", path.name)
            continue
        try:
            meta, body = parse_framework(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, yaml.YAMLError) as exc:
            log.warning("Skipping unreadable framework %s: %s", path.name, exc)
            continue
        name = path.stem
        found[name] = {
            "name": name,
            "title": str(meta.get("title") or name.replace("-", " ").title()),
            "category": str(meta.get("category") or "uncategorized"),
            "use_when": str(meta.get("use_when") or ""),
            "body": body,
        }
    return found


def register(app: MCPServer, settings: Settings) -> None:
    folder = settings.frameworks_dir

    @app.tool(title="List frameworks", annotations=READ_ONLY)
    def list_frameworks(
        category: Annotated[str | None, Field(description="Only this category.")] = None,
    ) -> dict[str, Any]:
        """List the analytical frameworks available, with each one's name, title,
        category, and when to use it."""
        items = [
            {k: fw[k] for k in META_FIELDS}
            for fw in load_frameworks(folder).values()
            if category is None or fw["category"].lower() == category.strip().lower()
        ]
        return {"count": len(items), "results": items}

    @app.tool(title="Get framework", annotations=READ_ONLY)
    def get_framework(
        name: Annotated[
            str, Field(description="Framework name as shown by list_frameworks.", max_length=100)
        ],
    ) -> dict[str, Any]:
        """Return one framework's details and its full Markdown text."""
        name = name.strip()
        if not name or "/" in name or "\\" in name or ".." in name:
            raise ToolError("Invalid framework name. Use a name from list_frameworks.")
        frameworks = load_frameworks(folder)  # the allow-list
        if name not in frameworks:
            raise ToolError(f"No framework named '{name}'. Use list_frameworks to see names.")
        return frameworks[name]
