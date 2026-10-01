"""Command-line entry point.

    uv run knowledge-mcp --transport stdio
    uv run python -m knowledge_mcp --transport stdio

In stdio mode, stdout carries the MCP protocol, so all logging goes to stderr.
"""

from __future__ import annotations

import argparse
import logging
import sys

from knowledge_mcp import __version__


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="knowledge-mcp", description="Personal knowledge MCP server."
    )
    parser.add_argument(
        "--transport",
        choices=["stdio", "http"],
        default="stdio",
        help="stdio for a local client such as Claude Desktop (default).",
    )
    parser.add_argument("--version", action="version", version=f"knowledge-mcp {__version__}")
    args = parser.parse_args(argv)

    logging.basicConfig(
        stream=sys.stderr,
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    if args.transport == "http":
        print("The HTTP transport arrives in Phase 4. Use --transport stdio.", file=sys.stderr)
        return 2

    from knowledge_mcp.server import create_server

    try:
        app = create_server()
    except Exception as exc:  # startup errors: show a clear message, not a traceback
        print(f"knowledge-mcp could not start: {exc}", file=sys.stderr)
        return 1
    app.run(transport="stdio")
    return 0


if __name__ == "__main__":
    sys.exit(main())
