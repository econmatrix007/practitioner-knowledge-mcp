"""launchd installer tests. Only --dry-run runs here; launchd itself is macOS-only."""

from __future__ import annotations

import plistlib
import subprocess
from typing import Any

import pytest

from knowledge_mcp import config

INSTALLER = config.REPO_ROOT / "deploy" / "macos" / "install_launchd.sh"


def run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 - fixed repo script
        ["/bin/bash", str(INSTALLER), *args], capture_output=True, text=True, check=False
    )


def render(*args: str) -> dict[str, Any]:
    result = run("install", "server", "--dry-run", *args)
    assert result.returncode == 0, result.stderr
    return plistlib.loads(result.stdout.encode())


def test_defaults_keep_service_local_and_restarting() -> None:
    plist = render()
    env = plist["EnvironmentVariables"]
    assert env["KNOWLEDGE_MCP_HOST"] == "127.0.0.1"
    assert env["KNOWLEDGE_MCP_PORT"] == "8765"
    assert env["KNOWLEDGE_MCP_TOKEN_FILE"].endswith("/.knowledge-mcp/token")
    assert "KNOWLEDGE_MCP_ALLOWED_HOSTS" not in env  # empty entries are dropped
    assert "KNOWLEDGE_MCP_PLUGINS" not in env
    assert plist["KeepAlive"] is True and plist["RunAtLoad"] is True
    assert plist["ProgramArguments"][1:] == ["--transport", "http"]
    assert plist["ProgramArguments"][0].endswith("/.venv/bin/knowledge-mcp")
    assert plist["StandardErrorPath"].endswith("/Library/Logs/knowledge-mcp/server.err.log")


def test_options_are_rendered_and_paths_escaped() -> None:
    plist = render(
        "--host",
        "100.101.102.103",
        "--port",
        "9001",
        "--allowed-hosts",
        "mini.example.ts.net",
        "--db",
        "/Users/someone/My Notes & More/ideas.db",
        "--label",
        "org.example.knowledge",
    )
    env = plist["EnvironmentVariables"]
    assert env["KNOWLEDGE_MCP_HOST"] == "100.101.102.103"
    assert env["KNOWLEDGE_MCP_PORT"] == "9001"
    assert env["KNOWLEDGE_MCP_ALLOWED_HOSTS"] == "mini.example.ts.net"
    assert env["KNOWLEDGE_MCP_DB"] == "/Users/someone/My Notes & More/ideas.db"
    assert plist["Label"] == "org.example.knowledge"


def test_no_token_option_drops_token_file() -> None:
    assert "KNOWLEDGE_MCP_TOKEN_FILE" not in render("--no-token")["EnvironmentVariables"]


def test_plist_never_contains_a_token_value() -> None:
    text = run("install", "server", "--dry-run").stdout
    assert "KNOWLEDGE_MCP_TOKEN<" not in text  # only the file path, never the secret


@pytest.mark.parametrize(
    "args", [("install", "server", "--bogus"), ("install", "nothing"), ("explode", "server")]
)
def test_bad_arguments_fail_clearly(args: tuple[str, ...]) -> None:
    result = run(*args)
    assert result.returncode != 0
    assert "Traceback" not in result.stderr


@pytest.mark.parametrize(
    ("args", "message"),
    [
        (("--host", "0.0.0.0"), "all interfaces"),  # noqa: S104
        (("--host", "100.101.102.103", "--no-token"), "without a bearer token"),
        (("--port", "99999"), "KNOWLEDGE_MCP_PORT"),
    ],
)
def test_unsafe_config_is_refused_with_a_clear_message(args: tuple[str, ...], message: str) -> None:
    result = run("install", "server", "--dry-run", *args)
    assert result.returncode != 0
    assert message in result.stderr
    assert "Nothing was installed" in result.stderr
    assert "Traceback" not in result.stderr
    assert result.stdout == ""  # no plist rendered


def test_tailscale_address_with_token_is_accepted() -> None:
    env = render("--host", "100.101.102.103")["EnvironmentVariables"]
    assert env["KNOWLEDGE_MCP_HOST"] == "100.101.102.103"


def test_plugins_are_passed_to_the_service() -> None:
    plugin = str(config.REPO_ROOT / "examples" / "example_plugin.py")
    env = render("--plugins", plugin)["EnvironmentVariables"]
    assert env["KNOWLEDGE_MCP_PLUGINS"] == plugin
