"""Example configs stay valid, safe, and consistent with the docs that cite them."""

from __future__ import annotations

import json
import re

from knowledge_mcp import config

REPO = config.REPO_ROOT
STDIO = REPO / "examples" / "claude_desktop_config.stdio.json"
REMOTE = REPO / "examples" / "claude_desktop_config.remote.json"
REMOTE_DOC = REPO / "docs" / "04-remote-access-tailscale.md"


def entry(path: object) -> dict:
    return json.loads(path.read_text())["mcpServers"]["practitioner-knowledge"]  # type: ignore[attr-defined]


def test_stdio_example_runs_stdio_transport() -> None:
    args = entry(STDIO)["args"]
    assert args[-2:] == ["--transport", "stdio"]


def test_remote_example_uses_pinned_bridge_and_header_file() -> None:
    args = entry(REMOTE)["args"]
    assert re.fullmatch(r"mcp-remote@\d+\.\d+\.\d+", args[1]), "pin an exact mcp-remote version"
    assert args[args.index("--transport") + 1] == "http-only"
    assert "--header-file" in args and "--header" not in args
    url = args[2]
    assert url.startswith("http://100.") and url.endswith(":8765/mcp")  # a Tailscale address


def test_no_example_contains_a_secret() -> None:
    for path in (STDIO, REMOTE):
        text = path.read_text()
        assert "Bearer" not in text
        assert 'KNOWLEDGE_MCP_TOKEN"' not in text


def test_remote_doc_matches_example_version() -> None:
    pinned = entry(REMOTE)["args"][1]
    assert pinned in REMOTE_DOC.read_text(), "docs/04 must cite the same mcp-remote version"
