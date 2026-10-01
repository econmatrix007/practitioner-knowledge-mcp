"""Six idea tools: store, get, update, search, list, and stats."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Annotated, Any, Literal

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp_types import ToolAnnotations
from pydantic import Field

from knowledge_mcp import db
from knowledge_mcp.config import Settings

Status = Literal["seed", "developing", "mature", "published", "archived"]

READ_ONLY = ToolAnnotations(read_only_hint=True, open_world_hint=False)
WRITE = ToolAnnotations(read_only_hint=False, destructive_hint=False, open_world_hint=False)


def register(app: MCPServer, settings: Settings) -> None:
    @contextmanager
    def connection() -> Iterator[sqlite3.Connection]:
        # One short-lived connection per call: tool handlers run on worker threads.
        conn = db.connect(settings.db_path)
        try:
            yield conn
        except db.ValidationError as exc:
            raise ToolError(str(exc)) from None
        finally:
            conn.close()

    @app.tool(title="Store idea", annotations=WRITE)
    def store_idea(
        title: Annotated[str, Field(description="Short title, 3 to 200 characters.")],
        domain: Annotated[str, Field(description="Subject area, such as 'public finance'.")],
        problem: Annotated[str, Field(description="The puzzle or question the idea addresses.")],
        insight: Annotated[str, Field(description="The proposed answer or mechanism.")],
        assumptions: Annotated[
            str | None, Field(description="Baseline assumptions the idea depends on.")
        ] = None,
        tags: Annotated[list[str] | None, Field(description="Up to 20 short tags.")] = None,
        status: Annotated[Status, Field(description="Maturity of the idea.")] = "seed",
    ) -> dict[str, Any]:
        """Save a new idea to the knowledge base. Returns its id and the stored record."""
        with connection() as conn:
            idea = db.create_idea(
                conn,
                title=title,
                domain=domain,
                problem=problem,
                insight=insight,
                assumptions=assumptions,
                tags=tags,
                status=status,
            )
        return {"id": idea["id"], "idea": idea}

    @app.tool(title="Get idea", annotations=READ_ONLY)
    def get_idea(
        id: Annotated[int, Field(description="The idea's id.", ge=1)],  # noqa: A002
    ) -> dict[str, Any]:
        """Return the full record for one idea."""
        with connection() as conn:
            idea = db.get_idea(conn, id)
        if idea is None:
            raise ToolError(f"No idea with id {id}.")
        return idea

    @app.tool(title="Update idea", annotations=WRITE)
    def update_idea(
        id: Annotated[int, Field(description="The idea's id.", ge=1)],  # noqa: A002
        title: str | None = None,
        domain: str | None = None,
        problem: str | None = None,
        insight: str | None = None,
        assumptions: Annotated[
            str | None, Field(description="Pass an empty string to clear.")
        ] = None,
        tags: Annotated[list[str] | None, Field(description="Replaces the existing tags.")] = None,
        status: Status | None = None,
    ) -> dict[str, Any]:
        """Change one or more fields of an existing idea. Omitted fields stay as they are.
        Returns the updated record."""
        given = {
            "title": title,
            "domain": domain,
            "problem": problem,
            "insight": insight,
            "assumptions": assumptions,
            "tags": tags,
            "status": status,
        }
        changes = {k: v for k, v in given.items() if v is not None}
        with connection() as conn:
            idea = db.update_idea(conn, id, changes)
        if idea is None:
            raise ToolError(f"No idea with id {id}.")
        return idea

    @app.tool(title="Search ideas", annotations=READ_ONLY)
    def search_ideas(
        query: Annotated[str, Field(description="Words to look for.")],
        domain: Annotated[str | None, Field(description="Only search this domain.")] = None,
        limit: Annotated[int, Field(description="Maximum results, 1 to 100.", ge=1)] = 10,
    ) -> dict[str, Any]:
        """Full-text search across titles, domains, problems, insights, assumptions, and tags.
        Results are ranked best match first and include a snippet with matched words in
        [brackets]. If no idea contains every word, ideas containing any word are returned
        instead, and each result's `matched` field says which rule applied."""
        with connection() as conn:
            hits = db.search_ideas(conn, query, domain=domain, limit=limit)
        return {"count": len(hits), "results": hits}

    @app.tool(title="List ideas", annotations=READ_ONLY)
    def list_ideas(
        domain: str | None = None,
        tag: str | None = None,
        status: Status | None = None,
        limit: Annotated[int, Field(description="Maximum results, 1 to 100.", ge=1)] = 20,
        offset: Annotated[int, Field(description="Results to skip, for paging.", ge=0)] = 0,
    ) -> dict[str, Any]:
        """List ideas, newest first, optionally filtered by domain, tag, or status."""
        with connection() as conn:
            ideas = db.list_ideas(
                conn, domain=domain, tag=tag, status=status, limit=limit, offset=offset
            )
        return {"count": len(ideas), "offset": offset, "results": ideas}

    @app.tool(title="Idea statistics", annotations=READ_ONLY)
    def idea_stats() -> dict[str, Any]:
        """Return the total number of ideas, counts by domain and by status, and the
        most-used tags."""
        with connection() as conn:
            return db.idea_stats(conn)
