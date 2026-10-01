"""check_private.sh against throwaway git repositories with planted problems."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

from knowledge_mcp import config

SCRIPT = config.REPO_ROOT / "scripts" / "check_private.sh"
PLANTED_NAME = "Zephyrine Holdings"  # fictional private name planted in test repos


def git(repo: Path, *args: str) -> None:
    subprocess.run(  # noqa: S603 - fixed git binary, test-controlled args
        ["git", *args],  # noqa: S607
        cwd=repo,
        check=True,
        capture_output=True,
        env={
            **os.environ,
            "GIT_AUTHOR_NAME": "Test",
            "GIT_AUTHOR_EMAIL": "test@example.com",
            "GIT_COMMITTER_NAME": "Test",
            "GIT_COMMITTER_EMAIL": "test@example.com",
        },
    )


def commit(repo: Path, files: dict[str, str], message: str = "change") -> None:
    for name, text in files.items():
        path = repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", message)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    path = tmp_path / "repo"
    path.mkdir()
    git(path, "init", "-q", "-b", "main")
    commit(path, {"README.md": "A clean project.\n"}, "initial")
    return path


@pytest.fixture
def terms(tmp_path: Path) -> Path:
    path = tmp_path / "terms.txt"
    path.write_text(f"# private names\n\n{PLANTED_NAME}\nproject-bluefin\n")
    return path


def run(repo: Path, terms: Path | None, *args: str) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "GITLEAKS": "/nonexistent"}
    env["PRIVATE_TERMS_FILE"] = str(terms) if terms else str(repo / "missing.txt")
    return subprocess.run(  # noqa: S603 - fixed repo script
        ["/bin/bash", str(SCRIPT), *args], cwd=repo, env=env, capture_output=True, text=True
    )


def test_clean_repo_passes(repo: Path, terms: Path) -> None:
    result = run(repo, terms)
    assert result.returncode == 0, result.stdout
    assert "no deny-list terms" in result.stdout


def test_term_in_tracked_file_fails_and_is_masked(repo: Path, terms: Path) -> None:
    commit(repo, {"notes.md": f"Meeting with {PLANTED_NAME.lower()} next week.\n"})
    result = run(repo, terms)
    assert result.returncode == 1
    assert "notes.md:1" in result.stdout
    assert "[private term #1]" in result.stdout
    assert PLANTED_NAME.lower() not in result.stdout.lower()  # never printed


def test_term_removed_from_files_is_still_found_in_history(repo: Path, terms: Path) -> None:
    commit(repo, {"draft.md": "Code name: Project-Bluefin\n"})
    (repo / "draft.md").unlink()
    git(repo, "commit", "-qam", "remove draft")
    result = run(repo, terms)
    assert result.returncode == 1
    assert "history" in result.stdout and "[private term #2]" in result.stdout
    assert "bluefin" not in result.stdout.lower()


@pytest.mark.parametrize(
    "where",
    ["message", "file name", "branch"],
)
def test_term_in_metadata_is_found(repo: Path, terms: Path, where: str) -> None:
    if where == "message":
        commit(repo, {"a.md": "x\n"}, f"Notes from {PLANTED_NAME}")
    elif where == "file name":
        commit(repo, {"zephyrine holdings plan.md": "x\n"})
    else:
        git(repo, "branch", "project-bluefin-work")
    result = run(repo, terms)
    assert result.returncode == 1, result.stdout
    assert "zephyrine" not in result.stdout.lower() and "bluefin" not in result.stdout.lower()


@pytest.mark.parametrize("name", ["ideas.db", "data/export.csv", "HANDOFF.md", ".env", "x.sqlite3"])
def test_private_files_fail_even_after_deletion(repo: Path, terms: Path, name: str) -> None:
    commit(repo, {name: "private\n"})
    assert run(repo, terms).returncode == 1
    git(repo, "rm", "-q", name)
    git(repo, "commit", "-qm", "remove")
    result = run(repo, terms)
    assert result.returncode == 1
    assert "git history" in result.stdout


def test_terms_with_regex_characters_match_literally(repo: Path, tmp_path: Path) -> None:
    special = tmp_path / "special.txt"
    special.write_text("A+B (Partners)\n")
    commit(repo, {"a.md": "AAB Partners\n"})  # would match if treated as a regex
    assert run(repo, special).returncode == 0
    commit(repo, {"b.md": "Hired a+b (partners) today\n"})
    assert run(repo, special).returncode == 1


def test_missing_deny_list_warns_normally_but_fails_release(repo: Path) -> None:
    normal = run(repo, None)
    assert normal.returncode == 0 and "WARN" in normal.stdout
    release = run(repo, None, "--release")
    assert release.returncode == 1 and "required for release" in release.stdout


def test_missing_gitleaks_fails_release(repo: Path, terms: Path) -> None:
    result = run(repo, terms, "--release")
    assert result.returncode == 1 and "gitleaks not found" in result.stdout


def find_gitleaks() -> str | None:
    found = shutil.which("gitleaks")
    if found:
        return found
    cache = Path.home() / ".cache" / "pre-commit"
    for path in cache.glob("repo*/golangenv-*/bin/gitleaks"):
        return str(path)
    return None


@pytest.mark.skipif(find_gitleaks() is None, reason="gitleaks binary not available")
def test_gitleaks_finds_a_leaked_header_in_history(repo: Path, terms: Path) -> None:
    import secrets

    token = secrets.token_urlsafe(32)
    commit(repo, {"remote-headers": f"Authorization: Bearer {token}\n"})
    (repo / "remote-headers").unlink()
    git(repo, "commit", "-qam", "oops, remove")
    shutil.copy(config.REPO_ROOT / ".gitleaks.toml", repo / ".gitleaks.toml")
    env = {**os.environ, "GITLEAKS": find_gitleaks() or "", "PRIVATE_TERMS_FILE": str(terms)}
    result = subprocess.run(  # noqa: S603
        ["/bin/bash", str(SCRIPT)], cwd=repo, env=env, capture_output=True, text=True
    )
    assert result.returncode == 1
    assert "gitleaks found secrets" in result.stdout
    assert token not in result.stdout  # gitleaks output is redacted
