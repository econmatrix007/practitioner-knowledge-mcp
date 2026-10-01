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


def test_http_transport_not_yet_available() -> None:
    assert main(["--transport", "http"]) == 2


def test_unknown_transport_rejected() -> None:
    with pytest.raises(SystemExit):
        main(["--transport", "sse"])
