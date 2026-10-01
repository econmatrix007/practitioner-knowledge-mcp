"""HTTP transport tests: bind rules, Host checks, bearer token, and a live server."""

from __future__ import annotations

import json
import os
import secrets
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import anyio
import httpx2
import pytest
from mcp.client.client import Client
from mcp.client.streamable_http import streamable_http_client

from knowledge_mcp import config
from knowledge_mcp.config import ConfigError, Settings
from knowledge_mcp.http_server import check_bind, is_loopback, transport_security
from knowledge_mcp.server import CORE_TOOLS

TOKEN = secrets.token_urlsafe(32)  # generated per run; never a literal secret


def settings(**overrides: Any) -> Settings:
    base: dict[str, Any] = {"db_path": Path("x.db"), "frameworks_dir": Path("fw")}
    return Settings(**{**base, **overrides})


# --- Configuration --------------------------------------------------------------


@pytest.mark.parametrize("host", ["0.0.0.0", "::", ""])  # noqa: S104
def test_refuses_all_interfaces_by_default(host: str) -> None:
    with pytest.raises(ConfigError, match="all interfaces"):
        check_bind(settings(host=host))


def test_all_interfaces_needs_explicit_opt_in() -> None:
    check_bind(settings(host="0.0.0.0", allow_all_interfaces=True))  # noqa: S104


@pytest.mark.parametrize("host", ["127.0.0.1", "100.101.102.103", "::1", "localhost"])
def test_specific_addresses_are_allowed(host: str) -> None:
    check_bind(settings(host=host))


def test_loopback_detection() -> None:
    assert is_loopback("127.0.0.1") and is_loopback("::1") and is_loopback("localhost")
    assert not is_loopback("100.101.102.103")
    assert not is_loopback("mini.example.ts.net")


def test_host_allow_list_includes_bind_address_and_extras() -> None:
    sec = transport_security(
        settings(host="100.101.102.103", allowed_hosts=("mini.example.ts.net",))
    )
    assert sec.enable_dns_rebinding_protection
    for name in ("127.0.0.1:*", "localhost:*", "100.101.102.103:*", "mini.example.ts.net:*"):
        assert name in sec.allowed_hosts
    assert "evil.example:*" not in sec.allowed_hosts


def test_ipv6_bind_address_is_bracketed() -> None:
    assert "[fd7a:115c::1]:*" in transport_security(settings(host="fd7a:115c::1")).allowed_hosts


@pytest.mark.parametrize(
    ("env", "message"),
    [
        ({"KNOWLEDGE_MCP_PORT": "0"}, "KNOWLEDGE_MCP_PORT"),
        ({"KNOWLEDGE_MCP_PORT": "70000"}, "KNOWLEDGE_MCP_PORT"),
        ({"KNOWLEDGE_MCP_TOKEN": "short"}, "at least"),
        ({"KNOWLEDGE_MCP_TOKEN": TOKEN, "KNOWLEDGE_MCP_TOKEN_FILE": "/x"}, "not both"),
        ({"KNOWLEDGE_MCP_TOKEN_FILE": "/no/such/token"}, "Cannot read"),
    ],
)
def test_invalid_settings_are_rejected(
    monkeypatch: pytest.MonkeyPatch, env: dict[str, str], message: str
) -> None:
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    with pytest.raises(ConfigError, match=message):
        config.load_settings()


def test_token_file_is_read_and_stripped(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    token_file = tmp_path / "token"
    token_file.write_text(TOKEN + "\n")
    monkeypatch.setenv("KNOWLEDGE_MCP_TOKEN_FILE", str(token_file))
    assert config.load_settings().token == TOKEN


# --- Live server ----------------------------------------------------------------


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


@pytest.fixture
def server(isolated_env: Path) -> Iterator[str]:
    """Run `knowledge-mcp --transport http` with a token; yield its base URL."""
    port = free_port()
    env = {
        **os.environ,
        "KNOWLEDGE_MCP_DB": str(isolated_env),
        "KNOWLEDGE_MCP_PORT": str(port),
        "KNOWLEDGE_MCP_TOKEN": TOKEN,
    }
    proc = subprocess.Popen(  # noqa: S603 - fixed interpreter and module
        [sys.executable, "-m", "knowledge_mcp", "--transport", "http"],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )
    base = f"http://127.0.0.1:{port}"
    try:
        deadline = time.monotonic() + 20
        while True:
            try:
                with urllib.request.urlopen(f"{base}/healthz", timeout=1):  # noqa: S310
                    break
            except (urllib.error.URLError, ConnectionError):
                if proc.poll() is not None or time.monotonic() > deadline:
                    err = proc.stderr.read().decode() if proc.stderr else ""
                    pytest.fail(f"server did not start:\n{err[-2000:]}")
                time.sleep(0.2)
        yield base
    finally:
        proc.terminate()
        proc.wait(timeout=10)


def raw_post(url: str, headers: dict[str, str]) -> int:
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "ping"}).encode()
    request = urllib.request.Request(  # noqa: S310
        url,
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            **headers,
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=5) as response:  # noqa: S310
            return int(response.status)
    except urllib.error.HTTPError as exc:
        return int(exc.code)


def test_health_needs_no_token(server: str) -> None:
    with urllib.request.urlopen(f"{server}/healthz", timeout=5) as response:  # noqa: S310
        assert json.loads(response.read()) == {"status": "ok"}


@pytest.mark.parametrize(
    "headers",
    [{}, {"Authorization": f"Bearer {secrets.token_urlsafe(32)}"}, {"Authorization": TOKEN}],
)
def test_mcp_rejects_missing_or_wrong_token(server: str, headers: dict[str, str]) -> None:
    assert raw_post(f"{server}/mcp", headers) == 401


def test_mcp_rejects_forged_host_header(server: str) -> None:
    status = raw_post(f"{server}/mcp", {"Authorization": f"Bearer {TOKEN}", "Host": "evil.example"})
    assert 400 <= status < 500 and status != 401


def test_client_with_token_lists_and_calls_tools(server: str) -> None:
    async def go() -> tuple[list[str], Any]:
        http = httpx2.AsyncClient(headers={"Authorization": f"Bearer {TOKEN}"})
        async with http, Client(streamable_http_client(f"{server}/mcp", http_client=http)) as c:
            names = [t.name for t in (await c.list_tools()).tools]
            stats = (await c.call_tool("idea_stats", {})).structured_content
            return names, stats

    names, stats = anyio.run(go)
    assert sorted(names) == sorted(CORE_TOOLS)
    assert stats["total"] == 0
