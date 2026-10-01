"""Checkup: policy math, version levels, tickets, calendar files, and a full stubbed run."""

from __future__ import annotations

import hashlib
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from knowledge_mcp import checkup, config, db
from knowledge_mcp.checkup import Policy, PolicyError, Upgrade

THU = date(2026, 10, 1)  # a Thursday
POLICY = Policy(blackouts=((date(2026, 12, 20), date(2027, 1, 4)),))  # Saturday migrations


# --- Policy file ----------------------------------------------------------------


def test_example_policy_loads_with_documented_values() -> None:
    policy = checkup.load_policy(config.REPO_ROOT / "maintenance.example.toml")
    assert policy.checkup_day == 0 and policy.checkup_time == (8, 0)
    assert policy.migration_day == 5 and policy.migration_time == (10, 0)
    assert policy.soak_days == {"patch": 7, "minor": 14, "major": 30}
    assert policy.blackouts == ((date(2026, 12, 20), date(2027, 1, 4)),)
    assert policy.backup_before_checkup and policy.keep_last == 12


def test_missing_policy_means_defaults(tmp_path: Path) -> None:
    assert checkup.load_policy(tmp_path / "none.toml").source == "defaults"


@pytest.mark.parametrize(
    "toml",
    [
        '[schedule]\ncheckup_day = "Funday"',
        '[schedule]\ncheckup_time = "25:00"',
        "[soak_days]\nminor = -1",
        '[blackout]\ndates = ["2027-01-04:2026-12-20"]',
        '[blackout]\ndates = ["next week"]',
        "[backup]\nkeep_last = 0",
        '[project]\nrepo = "not a repo"',
        "this is = = not toml",
    ],
)
def test_invalid_policy_is_rejected_clearly(tmp_path: Path, toml: str) -> None:
    path = tmp_path / "maintenance.toml"
    path.write_text(toml)
    with pytest.raises(PolicyError):
        checkup.load_policy(path)


# --- Versions -------------------------------------------------------------------


@pytest.mark.parametrize(
    ("current", "target", "level"),
    [
        ("2.2.0", "2.2.1", "patch"),
        ("2.2.0", "2.3.0", "minor"),
        ("2.2.0", "3.0.0", "major"),
        ("2.2.0", "2.2.0", None),
        ("2.3.0", "2.2.9", None),
        ("0.1.0.dev0", "0.1.0", "patch"),
        ("2.2.0", "2.3.0rc1", None),  # never propose pre-releases
        ("3.12.3", "3.14.0", "minor"),
        ("6.0", "6.0.3", "patch"),
    ],
)
def test_upgrade_level(current: str, target: str, level: str | None) -> None:
    assert checkup.upgrade_level(current, target) == level


# --- Proposed-date rule (Section 7A) ------------------------------------------------


@pytest.mark.parametrize(
    ("released", "level", "expected"),
    [
        (date(2026, 9, 20), "minor", date(2026, 10, 10)),  # soak ends Sun 4 Oct -> Sat 10
        (date(2026, 9, 28), "patch", date(2026, 10, 10)),  # soak ends Mon 5 Oct -> Sat 10
        (date(2026, 9, 26), "patch", date(2026, 10, 3)),  # soak ends Sat 3 Oct -> that day
        (date(2025, 1, 1), "minor", date(2026, 10, 3)),  # long past -> next Saturday
        (date(2026, 9, 30), "major", date(2026, 10, 31)),  # soak ends Fri 30 Oct -> Sat 31
        (date(2026, 12, 1), "minor", date(2026, 12, 19)),  # soak ends Tue 15 Dec -> Sat 19
    ],
)
def test_proposed_date(released: date, level: str, expected: date) -> None:
    assert checkup.proposed_date(released, level, POLICY, THU) == expected


def test_blackout_window_is_skipped() -> None:
    # Soak ends Mon 21 Dec, inside the blackout; first Saturday after 4 Jan is 9 Jan.
    assert checkup.proposed_date(date(2026, 12, 7), "minor", POLICY, THU) == date(2027, 1, 9)


def test_date_just_before_blackout_is_kept() -> None:
    # Soak ends Sat 19 Dec, the day before the blackout starts.
    assert checkup.proposed_date(date(2026, 12, 5), "minor", POLICY, THU) == date(2026, 12, 19)


def test_security_overrides_soak_and_weekday() -> None:
    proposed = checkup.proposed_date(date(2026, 9, 30), "major", POLICY, THU, security=True)
    assert proposed == date(2026, 10, 2)  # the next calendar day, a Friday


def test_never_proposes_today_or_earlier() -> None:
    saturday = date(2026, 10, 3)
    assert checkup.proposed_date(date(2025, 1, 1), "patch", POLICY, saturday) == date(2026, 10, 10)


# --- Tickets and calendar files ---------------------------------------------------

UP = Upgrade("mcp", "2.2.0", "3.0.0", "major", date(2026, 9, 20), "https://example.com/changes")


def test_ticket_has_every_required_field() -> None:
    text = checkup.ticket_text(UP, date(2026, 10, 24), POLICY)
    for needed in (
        "| Current version | 2.2.0 |",
        "| Target version | 3.0.0 |",
        "| Semver level | major |",
        "| Released | 2026-09-20 |",
        "Saturday 24 October 2026, 10:00, 60 minutes",
        "https://example.com/changes",
        "PLAN REQUIRED",
        "## Risk notes",
        "## Rollback",
        "upgrade/mcp-3.0.0",
        "**Status:** open",
    ):
        assert needed in text


def test_security_ticket_is_flagged() -> None:
    sec = Upgrade("starlette", "1.7.0", "1.7.1", "patch", THU, "u", ["GHSA-xxxx-yyyy-zzzz"])
    text = checkup.ticket_text(sec, date(2026, 10, 2), POLICY)
    assert "**Flags:** SECURITY" in text and "GHSA-xxxx-yyyy-zzzz" in text


def test_ics_is_valid_rfc5545() -> None:
    ticket = Path("/Users/someone/.knowledge-mcp/maintenance/" + "x" * 80 + ".md")
    now = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)
    text = checkup.ics_text(UP, date(2026, 10, 24), POLICY, ticket, now)
    assert text.endswith("\r\n") and "\n" not in text.replace("\r\n", "")
    lines = text.split("\r\n")[:-1]
    assert all(len(line.encode()) <= 75 for line in lines), "lines must fold at 75 octets"
    unfolded = text.replace("\r\n ", "")
    for needed in (
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:",
        "BEGIN:VEVENT",
        "UID:ticket-mcp-3.0.0@practitioner-knowledge-mcp",
        "DTSTAMP:20261001T120000Z",
        "DTSTART:20261024T100000",
        "DTEND:20261024T110000",
        "SUMMARY:Upgrade mcp 2.2.0 to 3.0.0",
        "END:VEVENT",
        "END:VCALENDAR",
    ):
        assert needed in unfolded
    assert str(ticket) in unfolded


def test_ics_escapes_special_characters() -> None:
    assert checkup._ics_escape("a,b;c\\d\ne") == "a\\,b\\;c\\\\d\\ne"


def test_notification_summarizes_counts() -> None:
    findings = checkup.Findings(
        items=[
            checkup.Item("database", "green", "integrity ok"),
            checkup.Item("last backup", "green", "2 day(s) old: x.db"),
        ]
    )
    tickets = [(UP, date(2026, 10, 17), True)]
    assert checkup.notification_text(findings, tickets) == (
        "1 upgrade proposed for Sat Oct 17; DB healthy; backup 2 days old"
    )
    sec = Upgrade("starlette", "1.7.0", "1.7.1", "patch", THU, "u", ["GHSA-1"])
    message = checkup.notification_text(findings, [(sec, date(2026, 10, 2), True)])
    assert message.startswith("SECURITY: starlette fix proposed")


def test_python_release_list_parsing() -> None:
    sample = [
        {"name": "Python 3.13.1", "release_date": "2024-12-03T00:00:00Z", "pre_release": False},
        {"name": "Python 3.14.0", "release_date": "2026-10-07T00:00:00Z", "pre_release": False},
        {"name": "Python 3.15.0a1", "release_date": "2026-10-14T00:00:00Z", "pre_release": True},
        {"name": "Python 2.7.18", "release_date": "2020-04-20T00:00:00Z", "pre_release": False},
    ]
    assert checkup.latest_python(sample) == ("3.14.0", date(2026, 10, 7))


# --- Full run ---------------------------------------------------------------------


def snapshot() -> str:
    from importlib.metadata import distributions

    lock = (config.REPO_ROOT / "uv.lock").read_bytes()
    pkgs = sorted(f"{d.metadata['Name']}=={d.version}" for d in distributions())
    return hashlib.sha256(lock + "\n".join(pkgs).encode()).hexdigest()


def test_stubbed_run_writes_report_ticket_and_ics_and_upgrades_nothing(
    tmp_path: Path, isolated_env: Path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    conn = db.connect(isolated_env)
    db.seed_ideas(conn, db.load_seed_file(config.SEED_FILE))
    conn.close()
    monkeypatch.setenv("KNOWLEDGE_MCP_BACKUP_DIR", str(tmp_path / "backups"))
    monkeypatch.setattr(checkup, "SERVICE_PLIST", tmp_path / "absent.plist")
    sent: list[str] = []  # record notifications instead of showing them (osascript on macOS)
    monkeypatch.setattr(checkup, "notify", sent.append)
    out = tmp_path / "maintenance"
    before = snapshot()
    args = [
        "--policy",
        str(config.REPO_ROOT / "maintenance.example.toml"),
        "--out",
        str(out),
        "--offline",
        "--stub",
        "mcp=2.3.0@2026-09-20",
        "--today",
        "2026-10-01",
    ]

    assert checkup.main(args) == 0
    assert snapshot() == before, "the checkup must never install or upgrade anything"
    report = (out / "report-2026-10-01.md").read_text()
    assert "2.3.0 available (minor" in report and "Nothing was installed" in report
    ticket = out / "ticket-mcp-2.3.0.md"
    assert "Saturday 10 October 2026" in ticket.read_text()
    assert (out / "ticket-mcp-2.3.0.ics").read_bytes().count(b"\r\n") > 10
    assert list((tmp_path / "backups").glob("ideas-*.db")), "backup runs before checkup"
    assert sent == ["1 upgrade proposed for Sat Oct 10; DB healthy; backup 0 days old"]
    capsys.readouterr()

    # A second run keeps the existing ticket instead of regenerating it.
    ticket.write_text("my notes")
    assert checkup.main(args) == 0
    assert ticket.read_text() == "my notes"
    assert "Existing ticket: ticket-mcp-2.3.0.md" in capsys.readouterr().out


def test_bad_policy_exits_with_clear_error(tmp_path: Path, capsys) -> None:
    bad = tmp_path / "m.toml"
    bad.write_text('[schedule]\nmigration_day = "Someday"')
    assert checkup.main(["--policy", str(bad), "--offline", "--no-notify"]) == 1
    assert "migration_day must be a weekday" in capsys.readouterr().err


def test_validate_policy_prints_schedule(capsys) -> None:
    path = str(config.REPO_ROOT / "maintenance.example.toml")
    assert checkup.main(["--policy", path, "--validate-policy"]) == 0
    assert '"weekday": 0, "hour": 8, "minute": 0' in capsys.readouterr().out


def test_notify_uses_osascript_on_macos(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str]] = []
    monkeypatch.setattr(checkup.sys, "platform", "darwin")
    monkeypatch.setattr(checkup.subprocess, "run", lambda cmd, **kw: calls.append(cmd))
    checkup.notify('Say "hi"; 1 upgrade')
    assert calls[0][:2] == ["osascript", "-e"]
    assert calls[0][2] == (
        'display notification "Say \\"hi\\"; 1 upgrade" with title "Knowledge MCP checkup"'
    )


def test_notify_prints_elsewhere(monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    monkeypatch.setattr(checkup.sys, "platform", "linux")
    checkup.notify("hello")
    assert capsys.readouterr().out == "Notification: hello\n"
