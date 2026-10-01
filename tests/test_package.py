"""Package smoke tests: install, import, and command-line arguments."""

import pytest

import knowledge_mcp
from knowledge_mcp.__main__ import main


def test_version_is_set() -> None:
    assert knowledge_mcp.__version__ != "0.0.0"


def test_version_flag(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["--version"])
    assert exc.value.code == 0
    assert knowledge_mcp.__version__ in capsys.readouterr().out


def test_http_refuses_all_interfaces(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KNOWLEDGE_MCP_HOST", "0.0.0.0")  # noqa: S104
    assert main(["--transport", "http"]) == 1


def test_bad_config_is_a_clear_error(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("KNOWLEDGE_MCP_PORT", "eighty")
    assert main(["--transport", "http"]) == 1
    err = capsys.readouterr().err
    assert "KNOWLEDGE_MCP_PORT" in err and "Traceback" not in err


def test_unknown_transport_rejected() -> None:
    with pytest.raises(SystemExit):
        main(["--transport", "sse"])
