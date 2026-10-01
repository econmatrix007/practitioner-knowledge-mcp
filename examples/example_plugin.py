"""Example plugin: export one idea as Markdown.

Load it by setting KNOWLEDGE_MCP_PLUGINS to this file's absolute path, for
example in the "env" block of Claude Desktop's config:

    "KNOWLEDGE_MCP_PLUGINS": "/Users/you/dev/practitioner-knowledge-mcp/examples/example_plugin.py"

A plugin is a module with a register(app, settings) function. Inside it, define
tools with @app.tool() exactly as the core tools do.
"""

from __future__ import annotations

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from knowledge_mcp import db
from knowledge_mcp.config import Settings


def register(app: MCPServer, settings: Settings) -> None:
    @app.tool(title="Idea as Markdown")
    def idea_as_markdown(id: int) -> str:  # noqa: A002
        """Return one idea formatted as a Markdown note, ready to paste into a document."""
        conn = db.connect(settings.db_path)
        try:
            idea = db.get_idea(conn, id)
        except db.ValidationError as exc:
            raise ToolError(str(exc)) from None
        finally:
            conn.close()
        if idea is None:
            raise ToolError(f"No idea with id {id}.")
        lines = [
            f"# {idea['title']}",
            f"*{idea['domain']} · {idea['status']} · tags: {', '.join(idea['tags']) or 'none'}*",
            "",
            "## Problem",
            idea["problem"],
            "",
            "## Insight",
            idea["insight"],
        ]
        if idea["assumptions"]:
            lines += ["", "## Assumptions", idea["assumptions"]]
        return "\n".join(lines)
