"""Build the MCP server: core tools first, then optional plugins."""

from __future__ import annotations

from mcp.server.mcpserver import MCPServer

from knowledge_mcp import __version__, db
from knowledge_mcp.config import Settings, load_settings
from knowledge_mcp.plugins import load_plugins
from knowledge_mcp.tools import frameworks, ideas

INSTRUCTIONS = (
    "A personal knowledge base. Ideas are stored records with a problem, an insight, "
    "optional assumptions, tags, and a status. Frameworks are reusable analytical "
    "methods stored as Markdown."
)

CORE_TOOLS = (
    "store_idea",
    "get_idea",
    "update_idea",
    "search_ideas",
    "list_ideas",
    "idea_stats",
    "list_frameworks",
    "get_framework",
)


def create_server(settings: Settings | None = None) -> MCPServer:
    settings = settings or load_settings()
    db.connect(settings.db_path).close()  # create or upgrade the database up front
    app = MCPServer(
        "practitioner-knowledge",
        title="Practitioner Knowledge",
        instructions=INSTRUCTIONS,
        version=__version__,
    )
    ideas.register(app, settings)
    frameworks.register(app, settings)
    load_plugins(app, settings)
    return app
