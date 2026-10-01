"""Database layer: connection, migrations, validation, and queries for ideas.

Rules (HANDOFF Section 5):
- Parameterized SQL only. The few dynamic fragments below come from fixed
  allow-lists in this module, never from user input.
- Inputs are validated and capped before they reach SQLite.
- Functions return plain, JSON-serializable dicts and lists.
"""

from __future__ import annotations

import json
import re
import sqlite3
from collections.abc import Iterable, Mapping
from importlib.resources import files
from pathlib import Path
from typing import Any

from knowledge_mcp import config


class ValidationError(ValueError):
    """Raised when input fails validation. The message is safe to show users."""


# Ordered list of (version, SQL). Append new versions; never edit old ones.
MIGRATIONS: list[tuple[int, str]] = [
    (1, files("knowledge_mcp").joinpath("schema.sql").read_text(encoding="utf-8")),
]

EDITABLE_FIELDS = ("title", "domain", "problem", "insight", "assumptions", "tags", "status")
COLUMNS = "id, title, domain, problem, insight, assumptions, tags, status, created_at, updated_at"


# --- Connection and migrations ------------------------------------------------


def connect(path: Path | str) -> sqlite3.Connection:
    """Open the database, creating its folder if needed, and apply migrations."""
    if str(path) != ":memory:":
        Path(path).expanduser().parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    if str(path) != ":memory:":
        conn.execute("PRAGMA journal_mode = WAL")
    migrate(conn)
    return conn


def schema_version(conn: sqlite3.Connection) -> int:
    conn.execute("CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL)")
    row = conn.execute("SELECT MAX(version) FROM schema_version").fetchone()
    return int(row[0] or 0)


def migrate(conn: sqlite3.Connection) -> int:
    """Apply any migrations newer than the stored version. Returns the final version."""
    current = schema_version(conn)
    for version, sql in MIGRATIONS:
        if version > current:
            # One transaction per migration: schema change and version bump land together.
            # `version` is an int from the constant MIGRATIONS list, not user input.
            try:
                conn.executescript(
                    f"BEGIN;\n{sql}\nINSERT INTO schema_version(version) VALUES ({int(version)});\n"
                    "COMMIT;"
                )
            except sqlite3.Error:
                conn.rollback()
                raise
            current = version
    return current


# --- Validation ---------------------------------------------------------------


def _text(name: str, value: Any, *, max_len: int, min_len: int = 1) -> str:
    if not isinstance(value, str):
        raise ValidationError(f"{name} must be text.")
    value = value.strip()
    if len(value) < min_len:
        raise ValidationError(f"{name} must be at least {min_len} characters.")
    if len(value) > max_len:
        raise ValidationError(f"{name} must be at most {max_len} characters.")
    return value


def _optional_text(name: str, value: Any, *, max_len: int) -> str | None:
    if value is None:
        return None
    value = _text(name, value, max_len=max_len, min_len=0)
    return value or None


def _domain(value: Any) -> str:
    return _text("domain", value, max_len=config.MAX_DOMAIN).lower()


def _tags(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str) or not isinstance(value, Iterable):
        raise ValidationError("tags must be a list of text values.")
    seen: list[str] = []
    for tag in value:
        tag = _text("tag", tag, max_len=config.MAX_TAG_LENGTH).lower()
        if tag not in seen:
            seen.append(tag)
    if len(seen) > config.MAX_TAGS:
        raise ValidationError(f"At most {config.MAX_TAGS} tags are allowed.")
    return seen


def _status(value: Any) -> str:
    if value not in config.STATUSES:
        raise ValidationError(f"status must be one of: {', '.join(config.STATUSES)}.")
    return value


def _id(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValidationError("id must be a positive whole number.")
    return value


def _limit(value: Any, default: int) -> int:
    if value is None:
        return default
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValidationError("limit must be a positive whole number.")
    return min(value, config.MAX_LIMIT)


def _offset(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValidationError("offset must be zero or a positive whole number.")
    return value


def _fts_terms(query: Any) -> list[str]:
    """Split free text into quoted FTS5 terms.

    Each word is quoted, so FTS5 operators and punctuation in user input are
    treated as plain text rather than query syntax.
    """
    query = _text("query", query, max_len=config.MAX_QUERY)
    words = re.findall(r"\w+", query)
    if not words:
        raise ValidationError("query must contain at least one word.")
    return [f'"{w}"' for w in words]


# --- Row conversion -----------------------------------------------------------


def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    record = dict(row)
    record["tags"] = json.loads(record["tags"])
    return record


# --- Queries ------------------------------------------------------------------


def create_idea(
    conn: sqlite3.Connection,
    *,
    title: str,
    domain: str,
    problem: str,
    insight: str,
    assumptions: str | None = None,
    tags: Iterable[str] | None = None,
    status: str = "seed",
) -> dict[str, Any]:
    values = (
        _text("title", title, max_len=config.MAX_TITLE, min_len=config.MIN_TITLE),
        _domain(domain),
        _text("problem", problem, max_len=config.MAX_TEXT),
        _text("insight", insight, max_len=config.MAX_TEXT),
        _optional_text("assumptions", assumptions, max_len=config.MAX_TEXT),
        json.dumps(_tags(tags)),
        _status(status),
    )
    with conn:
        cur = conn.execute(
            "INSERT INTO ideas (title, domain, problem, insight, assumptions, tags, status) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            values,
        )
    created = get_idea(conn, int(cur.lastrowid or 0))
    assert created is not None  # noqa: S101 - just inserted
    return created


def get_idea(conn: sqlite3.Connection, idea_id: int) -> dict[str, Any] | None:
    row = conn.execute(
        f"SELECT {COLUMNS} FROM ideas WHERE id = ?",  # noqa: S608 - COLUMNS is a constant
        (_id(idea_id),),
    ).fetchone()
    return _row_to_dict(row) if row else None


def update_idea(
    conn: sqlite3.Connection, idea_id: int, changes: Mapping[str, Any]
) -> dict[str, Any] | None:
    """Update any subset of editable fields. Returns the new record, or None if not found."""
    idea_id = _id(idea_id)
    unknown = set(changes) - set(EDITABLE_FIELDS)
    if unknown:
        raise ValidationError(f"Cannot update field(s): {', '.join(sorted(unknown))}.")
    if not changes:
        raise ValidationError("No fields to update.")

    validators = {
        "title": lambda v: _text("title", v, max_len=config.MAX_TITLE, min_len=config.MIN_TITLE),
        "domain": _domain,
        "problem": lambda v: _text("problem", v, max_len=config.MAX_TEXT),
        "insight": lambda v: _text("insight", v, max_len=config.MAX_TEXT),
        "assumptions": lambda v: _optional_text("assumptions", v, max_len=config.MAX_TEXT),
        "tags": lambda v: json.dumps(_tags(v)),
        "status": _status,
    }
    # Column names come from EDITABLE_FIELDS (checked above), never from user text.
    fields = [f for f in EDITABLE_FIELDS if f in changes]
    assignments = ", ".join(f"{f} = ?" for f in fields)
    params = [validators[f](changes[f]) for f in fields]

    with conn:
        cur = conn.execute(
            f"UPDATE ideas SET {assignments}, updated_at = datetime('now') WHERE id = ?",  # noqa: S608
            (*params, idea_id),
        )
    if cur.rowcount == 0:
        return None
    return get_idea(conn, idea_id)


def search_ideas(
    conn: sqlite3.Connection, query: str, *, domain: str | None = None, limit: int = 10
) -> list[dict[str, Any]]:
    """Full-text search ranked by BM25 (best match first), with a highlighted snippet.

    Tries to match every word first. If nothing matches, falls back to any word,
    still ranked, so a loose query returns the closest ideas instead of nothing.
    Each hit's `matched` field says which rule found it: "all words" or "any word".
    """
    terms = _fts_terms(query)
    domain_value = _domain(domain) if domain is not None else None
    limit = _limit(limit, 10)
    attempts = [(" AND ".join(terms), "all words")]
    if len(terms) > 1:
        attempts.append((" OR ".join(terms), "any word"))
    for match, label in attempts:
        rows = _run_search(conn, match, domain_value, limit)
        if rows:
            return [_search_hit(row, label) for row in rows]
    return []


# FTS5 column order in ideas_fts. Snippets prefer the idea's text over its labels.
FTS_COLUMNS = ("title", "domain", "problem", "insight", "assumptions", "tags")
SNIPPET_PREFERENCE = ("problem", "insight", "assumptions", "title")
OPEN, CLOSE = "\x02", "\x03"  # internal highlight markers; never present in stored text
EXCERPT_WORDS = 20


def _run_search(
    conn: sqlite3.Connection, match: str, domain: str | None, limit: int
) -> list[sqlite3.Row]:
    params: list[Any] = [match]
    domain_clause = ""
    if domain is not None:
        domain_clause = "AND i.domain = ?"
        params.append(domain)
    params.append(limit)
    # One highlighted snippet per column, using control characters as markers so a
    # bracket that is already in the text (tags are stored as JSON) is never mistaken
    # for a highlight. FTS_COLUMNS is a constant, so the f-string adds no user input.
    snippets = ", ".join(
        f"snippet(ideas_fts, {n}, char(2), char(3), '...', 16) AS s_{name}"
        for n, name in enumerate(FTS_COLUMNS)
    )
    # Column weights: title 5, domain 1, problem 2, insight 2, assumptions 1, tags 1.
    return conn.execute(
        f"""
        SELECT i.id, i.title, i.domain, i.status, i.tags, i.problem, {snippets},
               bm25(ideas_fts, 5.0, 1.0, 2.0, 2.0, 1.0, 1.0) AS score
        FROM ideas_fts JOIN ideas AS i ON i.id = ideas_fts.rowid
        WHERE ideas_fts MATCH ? {domain_clause}
        ORDER BY score
        LIMIT ?
        """,  # noqa: S608 - snippets and domain_clause are built from constants
        params,
    ).fetchall()


def _snippet(row: sqlite3.Row) -> tuple[str, list[str]]:
    """Pick the most useful snippet and list the fields that matched.

    Prefers a highlighted passage from the problem, insight, assumptions, or title.
    When only the domain or tags matched, a highlight would just repeat the label,
    so the snippet is the opening of the problem statement instead.
    """
    matched = [name for name in FTS_COLUMNS if OPEN in (row[f"s_{name}"] or "")]
    for name in SNIPPET_PREFERENCE:
        if name in matched:
            text = row[f"s_{name}"]
            return text.replace(OPEN, "[").replace(CLOSE, "]"), matched
    words = row["problem"].split()
    excerpt = " ".join(words[:EXCERPT_WORDS]) + ("..." if len(words) > EXCERPT_WORDS else "")
    return excerpt, matched


def _search_hit(row: sqlite3.Row, matched: str) -> dict[str, Any]:
    snippet, fields = _snippet(row)
    record = {
        "id": row["id"],
        "title": row["title"],
        "domain": row["domain"],
        "status": row["status"],
        "tags": json.loads(row["tags"]),
        "snippet": snippet,
        "matched_fields": fields,
        "score": round(-row["score"], 4),  # bm25 is negative; flip so higher is better
        "matched": matched,
    }
    return record


def list_ideas(
    conn: sqlite3.Connection,
    *,
    domain: str | None = None,
    tag: str | None = None,
    status: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """List ideas newest first, with optional filters."""
    clauses: list[str] = []
    params: list[Any] = []
    if domain is not None:
        clauses.append("domain = ?")
        params.append(_domain(domain))
    if tag is not None:
        clauses.append("EXISTS (SELECT 1 FROM json_each(ideas.tags) WHERE value = ?)")
        params.append(_tags([tag])[0])
    if status is not None:
        clauses.append("status = ?")
        params.append(_status(status))
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    params += [_limit(limit, 20), _offset(offset)]
    rows = conn.execute(
        f"SELECT {COLUMNS} FROM ideas {where} "  # noqa: S608 - fixed fragments only
        "ORDER BY created_at DESC, id DESC LIMIT ? OFFSET ?",
        params,
    ).fetchall()
    return [_row_to_dict(r) for r in rows]


def idea_stats(conn: sqlite3.Connection, *, top_tags: int = 10) -> dict[str, Any]:
    """Totals, counts by domain and by status, and the most-used tags."""
    total = conn.execute("SELECT COUNT(*) FROM ideas").fetchone()[0]
    by_domain = conn.execute(
        "SELECT domain, COUNT(*) AS n FROM ideas GROUP BY domain ORDER BY n DESC, domain"
    ).fetchall()
    by_status = conn.execute(
        "SELECT status, COUNT(*) AS n FROM ideas GROUP BY status ORDER BY n DESC, status"
    ).fetchall()
    tags = conn.execute(
        "SELECT j.value AS tag, COUNT(*) AS n FROM ideas, json_each(ideas.tags) AS j "
        "GROUP BY j.value ORDER BY n DESC, tag LIMIT ?",
        (top_tags,),
    ).fetchall()
    return {
        "total": total,
        "by_domain": {r["domain"]: r["n"] for r in by_domain},
        "by_status": {r["status"]: r["n"] for r in by_status},
        "top_tags": [{"tag": r["tag"], "count": r["n"]} for r in tags],
    }


# --- Seeding ------------------------------------------------------------------


def seed_ideas(conn: sqlite3.Connection, records: Iterable[Mapping[str, Any]]) -> dict[str, int]:
    """Insert records whose (title, domain) pair is not already present.

    Safe to run any number of times: existing ideas are skipped, never duplicated
    or overwritten.
    """
    inserted = skipped = 0
    for rec in records:
        exists = conn.execute(
            "SELECT 1 FROM ideas WHERE title = ? AND domain = ?",
            (str(rec.get("title", "")).strip(), str(rec.get("domain", "")).strip().lower()),
        ).fetchone()
        if exists:
            skipped += 1
            continue
        create_idea(
            conn,
            title=rec["title"],
            domain=rec["domain"],
            problem=rec["problem"],
            insight=rec["insight"],
            assumptions=rec.get("assumptions"),
            tags=rec.get("tags"),
            status=rec.get("status", "seed"),
        )
        inserted += 1
    return {"inserted": inserted, "skipped": skipped}


def load_seed_file(path: Path | str) -> list[dict[str, Any]]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValidationError("Seed file must contain a JSON list of ideas.")
    return data
