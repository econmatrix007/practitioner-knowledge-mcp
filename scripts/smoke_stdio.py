"""Smoke test: launch the server the way Claude Desktop does and exercise it over stdio.

Usage:
    uv run python scripts/smoke_stdio.py        (or: make smoke)

Sends the parallel list requests that clients make on connect, then calls every
read-only tool. Prints PASS/FAIL with timings. Never writes to the database.
On failure, prints the tail of the server's stderr log.
"""

from __future__ import annotations

import os
import shlex
import shutil
import sys
import tempfile
import time
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

import anyio
from mcp import StdioServerParameters
from mcp.client.client import Client

REPO = Path(__file__).resolve().parents[1]
TIMEOUT = 20.0
results: list[tuple[str, bool, str]] = []


async def step(name: str, action: Callable[[], Awaitable[Any]]) -> Any:
    start = time.monotonic()
    try:
        with anyio.fail_after(TIMEOUT):
            value = await action()
    except TimeoutError:
        results.append((name, False, f"no answer after {TIMEOUT:.0f}s"))
        return None
    except Exception as exc:  # report every failure, keep going
        results.append((name, False, f"{type(exc).__name__}: {exc}"[:200]))
        return None
    results.append((name, True, f"{time.monotonic() - start:.2f}s"))
    return value


async def run(params: StdioServerParameters) -> None:
    async with Client(params, read_timeout_seconds=TIMEOUT) as client:
        await step("resources/list", client.list_resources)
        listed: dict[str, Any] = {}

        async def tools() -> None:
            listed["tools"] = await step("tools/list", client.list_tools)

        async with anyio.create_task_group() as tg:  # the three requests clients send at once
            tg.start_soon(tools)
            tg.start_soon(step, "prompts/list", client.list_prompts)
            tg.start_soon(step, "resources/templates/list", client.list_resource_templates)

        names = sorted(t.name for t in listed["tools"].tools) if listed.get("tools") else []
        results.append(("8 core tools present", len(names) >= 8, ", ".join(names) or "none"))

        async def call(tool: str, args: dict[str, Any]) -> Any:
            result = await client.call_tool(tool, args)
            if result.is_error:
                raise RuntimeError(result.content[0].text)  # type: ignore[union-attr]
            return result.structured_content

        stats = await step("idea_stats", lambda: call("idea_stats", {}))
        listing = await step("list_ideas", lambda: call("list_ideas", {"limit": 1}))
        await step("search_ideas", lambda: call("search_ideas", {"query": "risk"}))
        if listing and listing["results"]:
            first_id = listing["results"][0]["id"]
            await step("get_idea", lambda: call("get_idea", {"id": first_id}))
        frameworks = await step("list_frameworks", lambda: call("list_frameworks", {}))
        if frameworks and frameworks["results"]:
            name = frameworks["results"][0]["name"]
            await step("get_framework", lambda: call("get_framework", {"name": name}))
        if stats:
            results.append(("database", True, f"{stats['total']} ideas"))


def main() -> int:
    uv = shutil.which("uv")
    if uv is None:
        print("uv not found on PATH.", file=sys.stderr)
        return 1
    log = Path(tempfile.mkstemp(prefix="knowledge-mcp-smoke-", suffix=".log")[1])
    server = shlex.join(
        [uv, "--directory", str(REPO), "run", "knowledge-mcp", "--transport", "stdio"]
    )
    params = StdioServerParameters(
        command="/bin/sh",
        args=["-c", f"exec {server} 2>>{shlex.quote(str(log))}"],
        env=dict(os.environ),
    )
    print(f"Server command: {server}")
    print(
        f"Database: {os.environ.get('KNOWLEDGE_MCP_DB', '~/.knowledge-mcp/ideas.db (default)')}\n"
    )
    try:
        anyio.run(run, params)
    except Exception as exc:
        results.append(("connect", False, f"{type(exc).__name__}: {exc}"[:300]))

    for name, ok, detail in results:
        print(f"  {'PASS' if ok else 'FAIL'}  {name:<26} {detail}")
    failed = [r for r in results if not r[1]]
    print(f"\n{len(results) - len(failed)} passed, {len(failed)} failed.")
    if failed:
        print(f"\nLast 25 lines of the server log ({log}):")
        print("\n".join(log.read_text(errors="replace").splitlines()[-25:]) or "(empty)")
        return 1
    log.unlink(missing_ok=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
