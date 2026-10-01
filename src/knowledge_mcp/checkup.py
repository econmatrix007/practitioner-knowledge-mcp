"""Weekly maintenance checkup: inspect, report, propose dates, write tickets.

    uv run python -m knowledge_mcp.checkup        (or: make checkup)

It never installs, upgrades, or changes code or dependencies. Its only write
actions are an optional database backup and files in the maintenance folder
(~/.knowledge-mcp/maintenance/): a report, one ticket and one calendar file
per newly eligible upgrade, and a macOS notification.

Network use is limited to read-only GET requests listed in SECURITY.md: the
PyPI JSON API, the GitHub releases API, python.org, and pip-audit's lookups.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import plistlib
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import tomllib
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

from knowledge_mcp import __version__
from knowledge_mcp.config import REPO_ROOT, load_settings

WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
DEFAULT_POLICY_PATH = Path.home() / ".knowledge-mcp" / "maintenance.toml"
DEFAULT_OUT_DIR = Path.home() / ".knowledge-mcp" / "maintenance"
DEFAULT_BACKUP_DIR = Path.home() / ".knowledge-mcp" / "backups"
SERVICE_PLIST = Path.home() / "Library" / "LaunchAgents" / "com.example.knowledge-mcp.plist"
USER_AGENT = f"practitioner-knowledge-mcp-checkup/{__version__}"
TIMEOUT = 15

CHANGELOGS = {
    "mcp": "https://github.com/modelcontextprotocol/python-sdk/releases",
    "pyyaml": "https://github.com/yaml/pyyaml/blob/main/CHANGES",
    "python": "https://docs.python.org/3/whatsnew/",
}


class PolicyError(ValueError):
    """The maintenance policy file is invalid. The message is safe to show."""


# --- Policy -------------------------------------------------------------------


@dataclass(frozen=True)
class Policy:
    checkup_day: int = 0  # Monday
    checkup_time: tuple[int, int] = (8, 0)
    migration_day: int = 5  # Saturday
    migration_time: tuple[int, int] = (10, 0)
    migration_minutes: int = 60
    soak_days: dict[str, int] = field(
        default_factory=lambda: {"patch": 7, "minor": 14, "major": 30}
    )
    blackouts: tuple[tuple[date, date], ...] = ()
    backup_before_checkup: bool = True
    keep_last: int = 12
    repo: str = ""
    source: str = "defaults"


def _weekday(name: Any, key: str) -> int:
    if not isinstance(name, str) or name.strip().lower() not in WEEKDAYS:
        raise PolicyError(f"{key} must be a weekday name such as 'Saturday', not {name!r}.")
    return WEEKDAYS.index(name.strip().lower())


def _clock(value: Any, key: str) -> tuple[int, int]:
    match = re.fullmatch(r"(\d{1,2}):(\d{2})", str(value).strip())
    if not match or int(match[1]) > 23 or int(match[2]) > 59:
        raise PolicyError(f"{key} must be a 24-hour time such as '08:00', not {value!r}.")
    return int(match[1]), int(match[2])


def _blackout(value: Any) -> tuple[date, date]:
    try:
        start, end = (date.fromisoformat(p.strip()) for p in str(value).split(":"))
    except ValueError:
        raise PolicyError(
            f"blackout dates must look like '2026-12-20:2027-01-04', not {value!r}."
        ) from None
    if end < start:
        raise PolicyError(f"blackout window {value!r} ends before it starts.")
    return start, end


def load_policy(path: Path) -> Policy:
    """Read the policy file. A missing file means defaults (the example's values)."""
    if not path.exists():
        return Policy()
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise PolicyError(f"{path} is not valid TOML: {exc}") from None
    schedule = data.get("schedule", {})
    soak = data.get("soak_days", {})
    backup = data.get("backup", {})
    defaults = Policy()
    soak_days = dict(defaults.soak_days)
    for level in soak_days:
        if level in soak:
            if not isinstance(soak[level], int) or soak[level] < 0:
                raise PolicyError(f"soak_days.{level} must be a whole number of days.")
            soak_days[level] = soak[level]
    minutes = schedule.get("migration_duration_minutes", defaults.migration_minutes)
    if not isinstance(minutes, int) or not 15 <= minutes <= 600:
        raise PolicyError("migration_duration_minutes must be between 15 and 600.")
    keep = backup.get("keep_last", defaults.keep_last)
    if not isinstance(keep, int) or keep < 1:
        raise PolicyError("backup.keep_last must be at least 1.")
    repo = str(data.get("project", {}).get("repo", "") or "").strip()
    if repo and not re.fullmatch(r"[\w.-]+/[\w.-]+", repo):
        raise PolicyError(f"project.repo must look like 'owner/name', not {repo!r}.")
    return Policy(
        checkup_day=_weekday(schedule.get("checkup_day", "Monday"), "checkup_day"),
        checkup_time=_clock(schedule.get("checkup_time", "08:00"), "checkup_time"),
        migration_day=_weekday(schedule.get("migration_day", "Saturday"), "migration_day"),
        migration_time=_clock(schedule.get("migration_time", "10:00"), "migration_time"),
        migration_minutes=minutes,
        soak_days=soak_days,
        blackouts=tuple(_blackout(b) for b in data.get("blackout", {}).get("dates", [])),
        backup_before_checkup=bool(backup.get("before_checkup", True)),
        keep_last=keep,
        repo=repo,
        source=str(path),
    )


# --- Versions and dates ---------------------------------------------------------


def parse_version(text: str) -> tuple[tuple[int, int, int], bool]:
    """Return ((major, minor, patch), is_prerelease) for versions like 2.2.0 or 0.1.0.dev0."""
    match = re.match(r"v?(\d+)(?:\.(\d+))?(?:\.(\d+))?(.*)$", text.strip())
    if not match:
        raise ValueError(f"not a version: {text!r}")
    numbers = (int(match[1]), int(match[2] or 0), int(match[3] or 0))
    return numbers, bool(match[4].strip(".-+ "))


def upgrade_level(current: str, target: str) -> str | None:
    """'major', 'minor', or 'patch' if target is newer than current; otherwise None."""
    (cur, cur_pre), (tgt, tgt_pre) = parse_version(current), parse_version(target)
    if tgt_pre:
        return None  # never propose pre-releases
    if tgt == cur:
        return "patch" if cur_pre else None  # 0.1.0.dev0 -> 0.1.0
    if tgt < cur:
        return None
    if tgt[0] != cur[0]:
        return "major"
    if tgt[1] != cur[1]:
        return "minor"
    return "patch"


def in_blackout(day: date, policy: Policy) -> tuple[date, date] | None:
    for start, end in policy.blackouts:
        if start <= day <= end:
            return start, end
    return None


def next_weekday(on_or_after: date, weekday: int) -> date:
    return on_or_after + timedelta(days=(weekday - on_or_after.weekday()) % 7)


def proposed_date(
    released: date, level: str, policy: Policy, today: date, *, security: bool = False
) -> date:
    """Section 7A: the next migration day on or after release + soak, skipping blackouts.

    Never earlier than tomorrow. A security fix overrides the soak period and
    the weekday: it is proposed for the next calendar day.
    """
    tomorrow = today + timedelta(days=1)
    if security:
        return tomorrow
    earliest = max(released + timedelta(days=policy.soak_days[level]), tomorrow)
    day = next_weekday(earliest, policy.migration_day)
    while (window := in_blackout(day, policy)) is not None:
        day = next_weekday(window[1] + timedelta(days=1), policy.migration_day)
    return day


# --- Findings -------------------------------------------------------------------


@dataclass
class Item:
    name: str
    status: str  # green, yellow, red
    detail: str


@dataclass
class Upgrade:
    package: str
    current: str
    target: str
    level: str
    released: date
    changelog: str
    security_ids: list[str] = field(default_factory=list)

    @property
    def security(self) -> bool:
        return bool(self.security_ids)

    @property
    def plan_required(self) -> bool:
        return self.level == "major"

    @property
    def slug(self) -> str:
        return f"{self.package}-{self.target}"


# --- Read-only lookups ------------------------------------------------------------


def fetch_json(url: str) -> Any:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})  # noqa: S310
    with urllib.request.urlopen(request, timeout=TIMEOUT) as response:  # noqa: S310
        return json.loads(response.read())


def _iso_date(text: str) -> date:
    return datetime.fromisoformat(text.replace("Z", "+00:00")).date()


def latest_pypi(name: str) -> tuple[str, date]:
    data = fetch_json(f"https://pypi.org/pypi/{name}/json")
    latest = data["info"]["version"]
    files = data["releases"].get(latest) or []
    released = _iso_date(files[0]["upload_time"]) if files else date.today()
    return latest, released


def latest_python(releases: list[dict[str, Any]] | None = None) -> tuple[str, date]:
    """Newest stable Python 3 release from python.org's release list."""
    if releases is None:
        releases = fetch_json(
            "https://www.python.org/api/v2/downloads/release/?is_published=true&pre_release=false"
        )
    best: tuple[tuple[int, int, int], str, date] | None = None
    for release in releases:
        match = re.fullmatch(r"Python (3\.\d+\.\d+)", str(release.get("name", "")).strip())
        if not match or release.get("pre_release"):
            continue
        numbers = parse_version(match[1])[0]
        if best is None or numbers > best[0]:
            best = (numbers, match[1], _iso_date(release["release_date"]))
    if best is None:
        raise ValueError("no stable Python 3 release found")
    return best[1], best[2]


def latest_github_release(repo: str) -> tuple[str, date, str] | None:
    """Latest release of owner/name, or None when the repository has no releases yet."""
    try:
        data = fetch_json(f"https://api.github.com/repos/{repo}/releases/latest")
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return None
        raise
    return data["tag_name"].lstrip("v"), _iso_date(data["published_at"]), data["html_url"]


def repo_slug(policy: Policy) -> str | None:
    if policy.repo:
        return policy.repo
    try:
        url = subprocess.run(  # noqa: S603 - fixed read-only git command
            ["git", "-C", str(REPO_ROOT), "remote", "get-url", "origin"],  # noqa: S607
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None
    match = re.search(r"github\.com[:/]([\w.-]+/[\w.-]+?)(?:\.git)?$", url)
    return match[1] if match else None


def audit_dependencies() -> list[dict[str, Any]]:
    """Run pip-audit on every package installed in the project's environment.

    The package list comes from this Python process itself, so the check needs
    no other tools on PATH. That matters under launchd, whose PATH is minimal.
    """
    from importlib.metadata import distributions

    pip_audit = Path(sys.executable).parent / "pip-audit"
    if not pip_audit.exists():
        raise FileNotFoundError("pip-audit is not installed; run 'make install'")
    pins = sorted(
        {
            f"{d.metadata['Name']}=={d.version}"
            for d in distributions()
            if d.metadata["Name"] and d.metadata["Name"].lower() != "practitioner-knowledge-mcp"
        }
    )
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as handle:
        handle.write("\n".join(pins) + "\n")
        requirements = Path(handle.name)
    try:
        result = subprocess.run(  # noqa: S603 - fixed binary in the project venv
            [
                str(pip_audit),
                "-r",
                str(requirements),
                "--no-deps",
                "--disable-pip",
                "--format",
                "json",
                "--progress-spinner",
                "off",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
    finally:
        requirements.unlink(missing_ok=True)
    if result.returncode not in (0, 1) or not result.stdout.strip():
        detail = result.stderr.strip().splitlines()[-1] if result.stderr.strip() else "failed"
        raise RuntimeError(detail)
    return [d for d in json.loads(result.stdout)["dependencies"] if d.get("vulns")]


def installed(name: str) -> str:
    try:
        return version(name)
    except PackageNotFoundError:
        return "not installed"


# --- Inspections ------------------------------------------------------------------


@dataclass
class Findings:
    items: list[Item] = field(default_factory=list)
    upgrades: list[Upgrade] = field(default_factory=list)


def check_versions(
    findings: Findings, policy: Policy, *, offline: bool, stubs: dict[str, tuple[str, date]]
) -> None:
    """Item 1 and 3: installed vs latest for mcp, pyyaml, Python, and this project."""
    py = platform.python_version()
    targets: list[tuple[str, str, Any]] = [
        ("mcp", installed("mcp"), lambda: latest_pypi("mcp")),
        ("pyyaml", installed("PyYAML"), lambda: latest_pypi("pyyaml")),
        ("python", py, latest_python),
    ]
    slug = repo_slug(policy)
    for name, current, lookup in targets:
        _compare(findings, name, current, lookup, policy, offline, stubs, CHANGELOGS[name])

    project = "practitioner-knowledge-mcp"
    if project in stubs:
        latest_v, released = stubs[project]
        _record(findings, project, __version__, latest_v, released, "(stub)")
    elif offline or not slug:
        reason = "offline" if offline else "no GitHub repository configured"
        findings.items.append(
            Item(project, "yellow", f"{__version__} installed; skipped ({reason})")
        )
    else:
        try:
            release = latest_github_release(slug)
        except (OSError, ValueError, KeyError) as exc:
            findings.items.append(Item(project, "yellow", f"lookup failed: {exc}"))
        else:
            if release is None:
                findings.items.append(
                    Item(
                        project,
                        "green",
                        f"{__version__}; no releases found "
                        "(none yet, or the repository is not public)",
                    )
                )
            else:
                _record(findings, project, __version__, release[0], release[1], release[2])

    try:
        from mcp.types import LATEST_PROTOCOL_VERSION

        findings.items.append(
            Item(
                "MCP protocol",
                "green",
                f"installed SDK announces {LATEST_PROTOCOL_VERSION}; "
                "a newer SDK's protocol changes are listed in its ticket's changelog",
            )
        )
    except ImportError:
        findings.items.append(Item("MCP protocol", "yellow", "could not read from installed SDK"))


def _compare(findings, name, current, lookup, policy, offline, stubs, changelog) -> None:  # noqa: ANN001
    if name in stubs:
        latest_v, released = stubs[name]
        changelog = f"{changelog} (stubbed for testing)"
    elif offline:
        findings.items.append(Item(name, "yellow", f"{current} installed; skipped (offline)"))
        return
    else:
        try:
            latest_v, released = lookup()
        except (OSError, ValueError, KeyError) as exc:
            findings.items.append(
                Item(name, "yellow", f"{current} installed; lookup failed: {exc}")
            )
            return
    _record(findings, name, current, latest_v, released, changelog)


def _record(findings, name, current, latest_v, released, changelog) -> None:  # noqa: ANN001
    level = upgrade_level(current, latest_v)
    if level is None:
        findings.items.append(Item(name, "green", f"{current} is current (latest {latest_v})"))
        return
    findings.items.append(
        Item(
            name,
            "red" if level == "major" else "yellow",
            f"{current} installed; {latest_v} available ({level}, released {released})",
        )
    )
    findings.upgrades.append(Upgrade(name, current, latest_v, level, released, changelog))


def check_vulnerabilities(findings: Findings, *, offline: bool) -> None:
    """Item 2: known vulnerabilities. A fix becomes a SECURITY ticket."""
    if offline:
        findings.items.append(Item("vulnerabilities", "yellow", "skipped (offline)"))
        return
    try:
        vulnerable = audit_dependencies()
    except (OSError, RuntimeError, ValueError, subprocess.CalledProcessError) as exc:
        findings.items.append(Item("vulnerabilities", "yellow", f"pip-audit failed: {exc}"))
        return
    if not vulnerable:
        findings.items.append(
            Item("vulnerabilities", "green", "pip-audit: no known vulnerabilities")
        )
        return
    for dep in vulnerable:
        ids = [v["id"] for v in dep["vulns"]]
        fixes = sorted(
            {f for v in dep["vulns"] for f in v.get("fix_versions", [])},
            key=lambda f: parse_version(f)[0],
        )
        findings.items.append(
            Item(
                f"vulnerability: {dep['name']}",
                "red",
                f"{dep['version']} affected by {', '.join(ids)}",
            )
        )
        if fixes:
            level = upgrade_level(dep["version"], fixes[-1]) or "patch"
            findings.upgrades.append(
                Upgrade(
                    dep["name"].lower(),
                    dep["version"],
                    fixes[-1],
                    level,
                    date.today(),
                    f"https://pypi.org/project/{dep['name']}/{fixes[-1]}/",
                    ids,
                )
            )


def check_database(findings: Findings, db_path: Path, backup_dir: Path, today: date) -> None:
    """Item 4: integrity, size, row count, and age of the last backup."""
    if not db_path.exists():
        findings.items.append(Item("database", "red", f"not found at {db_path}"))
    else:
        try:
            conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
            result = conn.execute("PRAGMA integrity_check").fetchone()[0]
            count = conn.execute("SELECT COUNT(*) FROM ideas").fetchone()[0]
            conn.close()
        except sqlite3.Error as exc:
            findings.items.append(Item("database", "red", f"cannot read: {exc}"))
        else:
            size_kb = db_path.stat().st_size / 1024
            status = "green" if result == "ok" else "red"
            findings.items.append(
                Item("database", status, f"integrity {result}; {count} ideas; {size_kb:.0f} KB")
            )
    backups = sorted(backup_dir.glob("*.db"), key=lambda p: p.stat().st_mtime)
    if not backups:
        findings.items.append(Item("last backup", "yellow", "no backups found"))
        return
    age = (today - datetime.fromtimestamp(backups[-1].stat().st_mtime).date()).days
    status = "green" if age <= 8 else "yellow" if age <= 30 else "red"
    findings.items.append(Item("last backup", status, f"{age} day(s) old: {backups[-1].name}"))


def check_server(findings: Findings, plist_path: Path = SERVICE_PLIST) -> None:
    """Item 5: ping the always-on service if it is installed."""
    if not plist_path.exists():
        findings.items.append(Item("server", "green", "always-on service not installed (skipped)"))
        return
    try:
        env = plistlib.loads(plist_path.read_bytes()).get("EnvironmentVariables", {})
        host = env.get("KNOWLEDGE_MCP_HOST", "127.0.0.1")
        port = env.get("KNOWLEDGE_MCP_PORT", "8765")
        url = f"http://{'[' + host + ']' if ':' in host else host}:{port}/healthz"
        with urllib.request.urlopen(url, timeout=5) as response:  # noqa: S310 - local service
            ok = json.loads(response.read()).get("status") == "ok"
    except (OSError, ValueError, plistlib.InvalidFileException) as exc:
        findings.items.append(Item("server", "red", f"not answering: {exc}"))
        return
    findings.items.append(Item("server", "green" if ok else "red", f"{url} answered"))


def check_disk(findings: Findings, db_path: Path) -> None:
    """Item 6: free space on the database volume."""
    folder = db_path.parent if db_path.parent.exists() else Path.home()
    free_gb = shutil.disk_usage(folder).free / 1024**3
    status = "green" if free_gb >= 5 else "yellow" if free_gb >= 1 else "red"
    findings.items.append(Item("disk space", status, f"{free_gb:.1f} GB free"))


# --- Outputs ----------------------------------------------------------------------

ICON = {"green": "🟢 green", "yellow": "🟡 yellow", "red": "🔴 red"}


def write_report(
    out: Path,
    today: date,
    findings: Findings,
    tickets: list[tuple[Upgrade, date, bool]],
    policy: Policy,
) -> Path:
    lines = [
        f"# Maintenance checkup, {today:%A %d %B %Y}",
        "",
        f"Policy: {policy.source}",
        "",
        "| Item | Status | Detail |",
        "|---|---|---|",
        *[f"| {i.name} | {ICON[i.status]} | {i.detail} |" for i in findings.items],
        "",
        "## Proposed upgrades",
        "",
    ]
    if not tickets:
        lines.append("None. Everything is current, or still within its soak period.")
    for up, when, created in tickets:
        flags = " ".join(
            f
            for f, on in (("**SECURITY**", up.security), ("**PLAN REQUIRED**", up.plan_required))
            if on
        )
        state = "new ticket" if created else "existing ticket"
        lines.append(
            f"- {up.package} {up.current} to {up.target} ({up.level}) {flags}".rstrip()
            + f": proposed {when:%a %d %b %Y}; {state} `ticket-{up.slug}.md`"
        )
    lines += [
        "",
        "Nothing was installed or upgraded. To act on a ticket, open Claude Code "
        "in the project folder and run `/migrate`.",
    ]
    path = out / f"report-{today.isoformat()}.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def ticket_text(up: Upgrade, when: date, policy: Policy) -> str:
    risk = {
        "patch": "Bug fixes. Low risk.",
        "minor": "New features; may deprecate APIs. Read the changelog for deprecations.",
        "major": "Breaking changes are expected. PLAN REQUIRED: `/migrate` drafts a plan "
        "and waits for your approval before changing anything.",
    }[up.level]
    if up.security:
        risk += f" Fixes security advisories: {', '.join(up.security_ids)}."
    start = f"{policy.migration_time[0]:02d}:{policy.migration_time[1]:02d}"
    flags = [f for f, on in (("SECURITY", up.security), ("PLAN REQUIRED", up.plan_required)) if on]
    blackout = in_blackout(when, policy)
    return "\n".join(
        [
            f"# Upgrade ticket: {up.package} {up.current} to {up.target}",
            "",
            f"**Flags:** {', '.join(flags) or 'none'}",
            "",
            "**Status:** open",
            "",
            "| Field | Value |",
            "|---|---|",
            f"| Package | {up.package} |",
            f"| Current version | {up.current} |",
            f"| Target version | {up.target} |",
            f"| Semver level | {up.level} |",
            f"| Released | {up.released.isoformat()} |",
            f"| Proposed date | {when:%A %d %B %Y}, {start}, {policy.migration_minutes} minutes |",
            f"| Changelog | {up.changelog} |",
            f"| Branch | `upgrade/{up.slug}` |",
            "",
            "## Risk notes",
            "",
            risk,
            *(
                [
                    "",
                    f"Note: this security date falls inside a blackout window "
                    f"({blackout[0]} to {blackout[1]}). Security fixes override blackouts.",
                ]
                if blackout
                else []
            ),
            "",
            "## How to run it",
            "",
            "1. Open Claude Code in the project folder.",
            "2. Run `/migrate` and choose this ticket.",
            "3. It backs up the database, works on a separate branch, runs every check, "
            "and stops for your approval before merging or restarting anything.",
            "",
            "## Rollback",
            "",
            "1. `git checkout main` (your working version is untouched until you merge).",
            f"2. `git branch -D upgrade/{up.slug}` to discard the attempt.",
            "3. `make install` to restore the locked packages.",
            "4. If the service was restarted: "
            "`launchctl kickstart -k gui/$(id -u)/com.example.knowledge-mcp`.",
            "5. If data changed: restore the backup taken at the start "
            "(docs/07-backup-and-single-source-of-truth.md).",
            "",
            "## Findings",
            "",
            "_`/migrate` adds notes here._",
            "",
        ]
    )


def _fold(line: str) -> str:
    """RFC 5545 line folding: at most 75 octets per line, continuation lines start with a space."""
    out, current = [], b""
    for char in line:
        encoded = char.encode()
        if len(current) + len(encoded) > (75 if not out else 74):
            out.append(current.decode())
            current = b""
        current += encoded
    out.append(current.decode())
    return "\r\n ".join(out)


def _ics_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def ics_text(up: Upgrade, when: date, policy: Policy, ticket: Path, now: datetime) -> str:
    start = datetime.combine(when, datetime.min.time()).replace(
        hour=policy.migration_time[0], minute=policy.migration_time[1]
    )
    end = start + timedelta(minutes=policy.migration_minutes)
    prefix = "SECURITY: " if up.security else ""
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//practitioner-knowledge-mcp//checkup//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "BEGIN:VEVENT",
        f"UID:ticket-{up.slug}@practitioner-knowledge-mcp",
        f"DTSTAMP:{now.astimezone(UTC):%Y%m%dT%H%M%SZ}",
        f"DTSTART:{start:%Y%m%dT%H%M%S}",  # floating local time, as Calendar expects
        f"DTEND:{end:%Y%m%dT%H%M%S}",
        "SUMMARY:" + _ics_escape(f"{prefix}Upgrade {up.package} {up.current} to {up.target}"),
        "DESCRIPTION:"
        + _ics_escape(
            f"Open Claude Code in the project folder and run /migrate.\nTicket: {ticket}"
        ),
        "END:VEVENT",
        "END:VCALENDAR",
    ]
    return "\r\n".join(_fold(line) for line in lines) + "\r\n"


def notification_text(findings: Findings, tickets: list[tuple[Upgrade, date, bool]]) -> str:
    new = [(u, d) for u, d, created in tickets if created]
    parts = []
    security = [u for u, _ in new if u.security]
    if security:
        parts.append(f"SECURITY: {', '.join(u.package for u in security)} fix proposed")
    if new:
        first = min(d for _, d in new)
        parts.append(
            f"{len(new)} upgrade{'s' if len(new) > 1 else ''} proposed for {first:%a %b %-d}"
        )
    else:
        parts.append("No new upgrades")
    db = next((i for i in findings.items if i.name == "database"), None)
    parts.append("DB healthy" if db and db.status == "green" else "DB needs attention")
    backup = next((i for i in findings.items if i.name == "last backup"), None)
    if backup:
        match = re.match(r"(\d+) day", backup.detail)
        parts.append(f"backup {match[1]} days old" if match else "no backup")
    return "; ".join(parts)


def notify(message: str) -> None:
    """Show a macOS notification. Elsewhere, print it."""
    if sys.platform != "darwin":
        print(f"Notification: {message}")
        return
    script = f'display notification {json.dumps(message)} with title "Knowledge MCP checkup"'
    # The message is our own text, JSON-quoted so AppleScript reads it as one string.
    subprocess.run(  # noqa: S603
        ["osascript", "-e", script],  # noqa: S607 - macOS system binary
        check=False,
        capture_output=True,
    )


def run_backup(policy: Policy) -> Item:
    script = REPO_ROOT / "scripts" / "backup_db.sh"
    result = subprocess.run(  # noqa: S603 - fixed repo script
        ["/bin/bash", str(script), "--keep", str(policy.keep_last)],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode == 0:
        return Item("backup", "green", result.stdout.strip().splitlines()[0])
    return Item("backup", "red", (result.stderr or result.stdout).strip()[:200])


# --- Entry point ------------------------------------------------------------------


def parse_stub(text: str) -> tuple[str, tuple[str, date]]:
    """NAME=VERSION@YYYY-MM-DD, for testing what a newer release would produce."""
    match = re.fullmatch(r"([\w.-]+)=([\w.]+)@(\d{4}-\d{2}-\d{2})", text)
    if not match:
        raise argparse.ArgumentTypeError("use NAME=VERSION@YYYY-MM-DD, e.g. mcp=2.3.0@2026-09-20")
    return match[1].lower(), (match[2], date.fromisoformat(match[3]))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="knowledge-mcp-checkup", description=__doc__.split("\n")[0]
    )
    parser.add_argument(
        "--policy",
        type=Path,
        default=Path(os.environ.get("KNOWLEDGE_MCP_MAINTENANCE_POLICY", DEFAULT_POLICY_PATH)),
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path(os.environ.get("KNOWLEDGE_MCP_MAINTENANCE_DIR", DEFAULT_OUT_DIR)),
    )
    parser.add_argument("--offline", action="store_true", help="skip every network lookup")
    parser.add_argument(
        "--stub",
        type=parse_stub,
        action="append",
        default=[],
        metavar="NAME=VERSION@DATE",
        help="pretend NAME's latest release is VERSION, released DATE (testing)",
    )
    parser.add_argument(
        "--today",
        type=date.fromisoformat,
        default=None,
        help="run as if today were this date (testing)",
    )
    parser.add_argument("--no-backup", action="store_true")
    parser.add_argument("--no-notify", action="store_true")
    parser.add_argument(
        "--validate-policy",
        action="store_true",
        help="check the policy file and print the schedule, then exit",
    )
    args = parser.parse_args(argv)

    try:
        policy = load_policy(args.policy)
    except PolicyError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    if args.validate_policy:
        print(
            json.dumps(
                {
                    "source": policy.source,
                    "weekday": policy.checkup_day,
                    "hour": policy.checkup_time[0],
                    "minute": policy.checkup_time[1],
                }
            )
        )
        return 0

    today = args.today or date.today()
    settings = load_settings()
    backup_dir = Path(os.environ.get("KNOWLEDGE_MCP_BACKUP_DIR", DEFAULT_BACKUP_DIR))
    args.out.mkdir(parents=True, exist_ok=True)
    findings = Findings()
    if policy.source == "defaults":
        findings.items.append(
            Item(
                "policy",
                "yellow",
                f"no {args.policy}; using defaults (copy maintenance.example.toml)",
            )
        )
    if policy.backup_before_checkup and not args.no_backup:
        findings.items.append(run_backup(policy))

    stubs = dict(args.stub)
    check_versions(findings, policy, offline=args.offline, stubs=stubs)
    check_vulnerabilities(findings, offline=args.offline)
    check_database(findings, settings.db_path, backup_dir, today)
    check_server(findings)
    check_disk(findings, settings.db_path)

    tickets: list[tuple[Upgrade, date, bool]] = []
    now = datetime.now(UTC)
    for up in findings.upgrades:
        when = proposed_date(up.released, up.level, policy, today, security=up.security)
        ticket = args.out / f"ticket-{up.slug}.md"
        created = not ticket.exists()  # one ticket per upgrade; never regenerate
        if created:
            ticket.write_text(ticket_text(up, when, policy), encoding="utf-8")
            (args.out / f"ticket-{up.slug}.ics").write_text(
                ics_text(up, when, policy, ticket, now), encoding="utf-8", newline=""
            )
        tickets.append((up, when, created))

    report = write_report(args.out, today, findings, tickets, policy)
    message = notification_text(findings, tickets)
    if not args.no_notify:
        notify(message)
    print(f"Report: {report}")
    for up, when, created in tickets:
        print(f"{'New' if created else 'Existing'} ticket: ticket-{up.slug}.md (proposed {when})")
    print(message)
    return 0


if __name__ == "__main__":
    sys.exit(main())
