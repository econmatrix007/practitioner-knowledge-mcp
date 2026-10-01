"""Docs stay true: links resolve, commands exist, required wording is present,
and the code printed in the guides actually runs."""

from __future__ import annotations

import json
import re
from pathlib import Path

import anyio
import pytest
from mcp.client.client import Client

from knowledge_mcp import config, db
from knowledge_mcp.config import Settings
from knowledge_mcp.server import create_server

REPO = config.REPO_ROOT
README = REPO / "README.md"
DOCS = sorted((REPO / "docs").glob("*.md"))
COMMUNITY = [REPO / n for n in ("SECURITY.md", "SUPPORT.md", "CONTRIBUTING.md", "CHANGELOG.md")]
PAGES = [README, *DOCS, *COMMUNITY]

# Files the docs link to before they exist. Empty once every phase has landed.
PENDING: set[str] = set()

NO_TELEMETRY = (
    "The project collects no usage data, sends nothing to the maintainer, and makes "
    "only the read-only version checks listed below."
)


def squash(text: str) -> str:
    return re.sub(r"\s+", " ", text)


@pytest.mark.parametrize("page", PAGES, ids=lambda p: p.name)
def test_no_em_dashes(page: Path) -> None:
    assert "—" not in page.read_text(), f"{page.name} contains an em-dash"


@pytest.mark.parametrize("page", PAGES, ids=lambda p: p.name)
def test_relative_links_resolve(page: Path) -> None:
    text = page.read_text()
    for target in re.findall(r"\]\(([^)#\s]+)(?:#[^)]*)?\)", text):
        if re.match(r"[a-z]+:", target):
            continue  # external URL
        resolved = (page.parent / target).resolve()
        rel = resolved.relative_to(REPO).as_posix()
        assert resolved.exists() or rel in PENDING, f"{page.name}: broken link {target}"


def test_make_targets_mentioned_in_docs_exist() -> None:
    makefile = (REPO / "Makefile").read_text()
    targets = set(re.findall(r"^([a-z][a-z-]*):", makefile, re.M))
    for page in PAGES:
        for target in re.findall(r"`make ([a-z][a-z-]*)", page.read_text()):
            assert target in targets, f"{page.name} mentions missing target: make {target}"


@pytest.mark.parametrize(
    "page", [README, REPO / "docs" / "08-security.md", REPO / "SECURITY.md"], ids=lambda p: p.name
)
def test_no_telemetry_statement_is_verbatim(page: Path) -> None:
    assert NO_TELEMETRY in squash(page.read_text())


def test_readme_length_matches_outline() -> None:
    lines = len(README.read_text().splitlines())
    assert 350 <= lines <= 500, f"README has {lines} lines; the outline asks for 350 to 500"


def test_readme_has_architecture_diagram() -> None:
    assert "```mermaid" in README.read_text()


def test_bridge_version_is_the_same_everywhere() -> None:
    versions = set()
    for path in [*PAGES, REPO / "examples" / "claude_desktop_config.remote.json"]:
        versions |= set(re.findall(r"mcp-remote@(\d+\.\d+\.\d+)", path.read_text()))
    assert len(versions) == 1, f"mcp-remote versions disagree: {sorted(versions)}"


def test_plugin_code_in_guide_runs(tmp_path: Path, isolated_env: Path) -> None:
    """Extract the review_queue plugin from docs/05 and run it as a real plugin."""
    guide = (REPO / "docs" / "05-add-your-own-tools.md").read_text()
    code = next(
        block
        for block in re.findall(r"```python\n(.*?)```", guide, re.S)
        if "review_queue" in block
    )
    plugin = tmp_path / "review_queue.py"
    plugin.write_text(code)

    conn = db.connect(isolated_env)
    db.seed_ideas(conn, db.load_seed_file(config.SEED_FILE))
    conn.execute("UPDATE ideas SET updated_at = datetime('now', '-90 days') WHERE id = 1")
    conn.commit()
    conn.close()

    settings = Settings(
        db_path=isolated_env, frameworks_dir=config.DEFAULT_FRAMEWORKS_DIR, plugins=(str(plugin),)
    )
    app = create_server(settings)

    async def go() -> tuple[object, object]:
        async with Client(app) as client:
            ok = await client.call_tool("review_queue", {"days": 30})
            bad = await client.call_tool("review_queue", {"days": 0})
            return ok, bad

    ok, bad = anyio.run(go)
    assert not ok.is_error, ok.content
    # A bare `-> dict` return arrives as JSON text rather than structured content.
    data = ok.structured_content or json.loads(ok.content[0].text)
    assert [r["id"] for r in data["results"]] == [1]  # idea 1 is 'developing'
    assert bad.is_error and "days must be" in bad.content[0].text


def test_code_of_conduct_has_no_unfilled_template_marker() -> None:
    assert "[INSERT CONTACT METHOD]" not in (REPO / "CODE_OF_CONDUCT.md").read_text()


def test_headless_summary_stays_read_only() -> None:
    """The documented headless job must keep its read-only restrictions."""
    guide = (REPO / "docs" / "09-maintenance-and-upgrades.md").read_text()
    for flag in (
        '--tools "Read,Glob,Grep"',
        '--disallowedTools "mcp__*"',
        "--permission-mode dontAsk",
        "--max-turns",
        "--max-budget-usd",
    ):
        assert guide.count(flag) >= 2, f"{flag} missing from the command or the plist"
    assert "/migrate" not in re.search(r"```xml\n(.*?)```", guide, re.S).group(1)


def test_migrate_command_cannot_run_itself() -> None:
    text = (REPO / ".claude" / "commands" / "migrate.md").read_text()
    assert "disable-model-invocation: true" in text
    for stop in ("Merge into `main`?", "Restart the always-on service", "Close the ticket?"):
        assert stop in text


def test_process_checks_are_scoped_to_the_current_user() -> None:
    """pgrep without -u sees other accounts' apps (for example under Fast User Switching)."""
    for page in PAGES:
        for line in page.read_text().splitlines():
            if "pgrep" in line:
                assert '-u "$USER"' in line, f"{page.name}: unscoped pgrep: {line.strip()}"


def test_claude_config_edits_say_quit_first() -> None:
    guide = (REPO / "docs" / "02-connect-claude-desktop.md").read_text()
    quit_at = guide.index("quit Claude Desktop completely")
    assert quit_at < guide.index("python3 - <<'PYEOF'"), "quit must come before the edit"
    assert "regular new chat" in guide


def test_no_publish_placeholders_remain() -> None:
    """Section 10 decisions are filled in; make release-check enforces the same rule."""
    pages = [*PAGES, REPO / "CODE_OF_CONDUCT.md", REPO / ".github" / "FUNDING.yml"]
    for page in pages:
        text = page.read_text()
        assert not re.search(r"\bOWNER\b|SECURITY_CONTACT_EMAIL", text), page.name
