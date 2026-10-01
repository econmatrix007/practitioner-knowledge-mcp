"""Data layer tests: schema, CRUD, full-text search, stats, seeding, validation."""

from __future__ import annotations

import contextlib
import json
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from knowledge_mcp import config, db

REPO = config.REPO_ROOT

SAMPLE = {
    "title": "Toll pricing smooths peak demand",
    "domain": "Urban Systems",
    "problem": "Roads congest at peak hours.",
    "insight": "A time-varying price shifts flexible trips to off-peak hours.",
    "assumptions": "Some trips are flexible.",
    "tags": ["Pricing", "congestion", "pricing"],
}


# --- Schema -------------------------------------------------------------------


def test_fts5_is_available() -> None:
    options = [r[0] for r in sqlite3.connect(":memory:").execute("PRAGMA compile_options")]
    assert "ENABLE_FTS5" in options


def test_migrate_sets_version_and_is_repeatable(conn: sqlite3.Connection) -> None:
    assert db.schema_version(conn) == db.MIGRATIONS[-1][0]
    assert db.migrate(conn) == db.MIGRATIONS[-1][0]
    rows = conn.execute("SELECT COUNT(*) FROM schema_version").fetchone()[0]
    assert rows == len(db.MIGRATIONS)


def test_connect_creates_parent_folder(tmp_path: Path) -> None:
    path = tmp_path / "nested" / "dir" / "ideas.db"
    db.connect(path).close()
    assert path.exists()


# --- Create and read ------------------------------------------------------------


def test_create_and_get_round_trip(conn: sqlite3.Connection) -> None:
    created = db.create_idea(conn, **SAMPLE)
    assert created["id"] >= 1
    assert created["domain"] == "urban systems"  # normalized to lower case
    assert created["tags"] == ["pricing", "congestion"]  # lower-cased and de-duplicated
    assert created["status"] == "seed"
    assert db.get_idea(conn, created["id"]) == created


def test_get_missing_returns_none(conn: sqlite3.Connection) -> None:
    assert db.get_idea(conn, 999) is None


def test_records_are_json_serializable(seeded: sqlite3.Connection) -> None:
    json.dumps(db.list_ideas(seeded))
    json.dumps(db.search_ideas(seeded, "resilience"))
    json.dumps(db.idea_stats(seeded))


# --- Update -------------------------------------------------------------------


def test_update_subset_of_fields(conn: sqlite3.Connection) -> None:
    idea = db.create_idea(conn, **SAMPLE)
    updated = db.update_idea(conn, idea["id"], {"status": "mature", "tags": ["tolls"]})
    assert updated is not None
    assert updated["status"] == "mature"
    assert updated["tags"] == ["tolls"]
    assert updated["title"] == idea["title"]  # untouched fields keep their values


def test_update_clears_optional_assumptions(conn: sqlite3.Connection) -> None:
    idea = db.create_idea(conn, **SAMPLE)
    updated = db.update_idea(conn, idea["id"], {"assumptions": ""})
    assert updated is not None and updated["assumptions"] is None


def test_update_missing_returns_none(conn: sqlite3.Connection) -> None:
    assert db.update_idea(conn, 999, {"status": "mature"}) is None


@pytest.mark.parametrize(
    "changes",
    [{}, {"id": 5}, {"created_at": "2020-01-01"}, {"title; DROP TABLE ideas": "x"}],
)
def test_update_rejects_bad_fields(conn: sqlite3.Connection, changes: dict) -> None:
    idea = db.create_idea(conn, **SAMPLE)
    with pytest.raises(db.ValidationError):
        db.update_idea(conn, idea["id"], changes)


# --- Full-text search -----------------------------------------------------------


def test_search_finds_and_ranks(seeded: sqlite3.Connection) -> None:
    hits = db.search_ideas(seeded, "lead time variance")
    assert hits, "expected at least one hit"
    assert hits[0]["title"].startswith("Supplier lead-time variance")
    assert "[" in hits[0]["snippet"]  # matched words are highlighted
    scores = [h["score"] for h in hits]
    assert scores == sorted(scores, reverse=True)


def test_search_matches_domain_names(seeded: sqlite3.Connection) -> None:
    hits = db.search_ideas(seeded, "supply chain")
    assert hits and all(h["matched"] == "all words" for h in hits)
    assert {h["domain"] for h in hits} == {"supply chains"}


def test_search_falls_back_to_any_word(seeded: sqlite3.Connection) -> None:
    hits = db.search_ideas(seeded, "chokepoint zzzunknownword")
    assert hits and hits[0]["matched"] == "any word"
    assert hits[0]["title"].startswith("Inventory buffers")


def test_search_with_no_match_returns_empty(seeded: sqlite3.Connection) -> None:
    assert db.search_ideas(seeded, "zzzunknownword") == []


def test_search_uses_stemming(seeded: sqlite3.Connection) -> None:
    # "chokepoints" should match "chokepoint" through the porter stemmer.
    assert db.search_ideas(seeded, "chokepoints")


def test_search_domain_filter_and_limit(seeded: sqlite3.Connection) -> None:
    hits = db.search_ideas(seeded, "risk", domain="Public Finance", limit=1)
    assert len(hits) == 1
    assert hits[0]["domain"] == "public finance"


def test_search_tracks_updates(conn: sqlite3.Connection) -> None:
    idea = db.create_idea(conn, **SAMPLE)
    assert db.search_ideas(conn, "toll")
    db.update_idea(conn, idea["id"], {"title": "Cordon charges smooth peak demand"})
    assert not db.search_ideas(conn, "toll")
    assert db.search_ideas(conn, "cordon")


def test_search_index_stays_consistent(seeded: sqlite3.Connection) -> None:
    seeded.execute("INSERT INTO ideas_fts(ideas_fts) VALUES ('integrity-check')")
    seeded.execute("DELETE FROM ideas WHERE id = 1")
    seeded.execute("INSERT INTO ideas_fts(ideas_fts) VALUES ('integrity-check')")


@pytest.mark.parametrize(
    "query", ['"unbalanced', "NEAR(", "title:*", "a OR", "-", "'); DROP TABLE ideas; --"]
)
def test_search_treats_operators_as_text(seeded: sqlite3.Connection, query: str) -> None:
    # A clear ValidationError is fine; a raw sqlite3 error would fail the test.
    with contextlib.suppress(db.ValidationError):
        db.search_ideas(seeded, query)
    assert seeded.execute("SELECT COUNT(*) FROM ideas").fetchone()[0] == 12


@pytest.mark.parametrize("query", ["", "   ", "!!!", "x" * (config.MAX_QUERY + 1)])
def test_search_rejects_empty_or_huge_queries(seeded: sqlite3.Connection, query: str) -> None:
    with pytest.raises(db.ValidationError):
        db.search_ideas(seeded, query)


# --- List -----------------------------------------------------------------------


def test_list_newest_first_with_paging(seeded: sqlite3.Connection) -> None:
    first = db.list_ideas(seeded, limit=5)
    second = db.list_ideas(seeded, limit=5, offset=5)
    assert len(first) == 5 and len(second) == 5
    assert {i["id"] for i in first}.isdisjoint({i["id"] for i in second})
    ids = [i["id"] for i in db.list_ideas(seeded)]
    assert ids == sorted(ids, reverse=True)


def test_list_filters(seeded: sqlite3.Connection) -> None:
    by_tag = db.list_ideas(seeded, tag="Resilience")
    assert by_tag and all("resilience" in i["tags"] for i in by_tag)
    by_status = db.list_ideas(seeded, status="mature")
    assert by_status and all(i["status"] == "mature" for i in by_status)
    combo = db.list_ideas(seeded, domain="supply chains", tag="inventory")
    assert len(combo) == 2


def test_list_caps_limit(seeded: sqlite3.Connection) -> None:
    for i in range(config.MAX_LIMIT + 5):
        db.create_idea(seeded, **{**SAMPLE, "title": f"Filler idea {i}"})
    assert len(db.list_ideas(seeded, limit=10_000)) == config.MAX_LIMIT


# --- Stats ----------------------------------------------------------------------


def test_stats(seeded: sqlite3.Connection) -> None:
    stats = db.idea_stats(seeded)
    assert stats["total"] == 12
    assert stats["by_domain"] == {
        "public finance": 3,
        "strategy": 3,
        "supply chains": 3,
        "urban systems": 3,
    }
    assert sum(stats["by_status"].values()) == 12
    # "measurement" and "resilience" tie at 4; ties sort alphabetically.
    assert stats["top_tags"][:2] == [
        {"tag": "measurement", "count": 4},
        {"tag": "resilience", "count": 4},
    ]


def test_stats_on_empty_database(conn: sqlite3.Connection) -> None:
    assert db.idea_stats(conn) == {"total": 0, "by_domain": {}, "by_status": {}, "top_tags": []}


# --- Validation -----------------------------------------------------------------


@pytest.mark.parametrize(
    "override",
    [
        {"title": "ab"},
        {"title": "x" * (config.MAX_TITLE + 1)},
        {"problem": ""},
        {"insight": "y" * (config.MAX_TEXT + 1)},
        {"domain": "   "},
        {"status": "done"},
        {"tags": "not-a-list"},
        {"tags": [f"t{i}" for i in range(config.MAX_TAGS + 1)]},
        {"tags": ["z" * (config.MAX_TAG_LENGTH + 1)]},
        {"tags": [42]},
    ],
)
def test_create_rejects_invalid_input(conn: sqlite3.Connection, override: dict) -> None:
    with pytest.raises(db.ValidationError):
        db.create_idea(conn, **{**SAMPLE, **override})


@pytest.mark.parametrize("bad_id", [0, -1, "1", 1.5, True, None])
def test_rejects_bad_ids(conn: sqlite3.Connection, bad_id: object) -> None:
    with pytest.raises(db.ValidationError):
        db.get_idea(conn, bad_id)  # type: ignore[arg-type]


# --- Seeding --------------------------------------------------------------------


def test_seed_file_is_well_formed() -> None:
    records = db.load_seed_file(config.SEED_FILE)
    assert len(records) == 12
    assert len({r["domain"] for r in records}) == 4
    assert len({(r["title"], r["domain"]) for r in records}) == 12


def test_seeding_is_idempotent(conn: sqlite3.Connection) -> None:
    records = db.load_seed_file(config.SEED_FILE)
    assert db.seed_ideas(conn, records) == {"inserted": 12, "skipped": 0}
    assert db.seed_ideas(conn, records) == {"inserted": 0, "skipped": 12}
    assert db.idea_stats(conn)["total"] == 12


def test_seeding_keeps_user_edits(conn: sqlite3.Connection) -> None:
    records = db.load_seed_file(config.SEED_FILE)
    db.seed_ideas(conn, records)
    db.update_idea(conn, 1, {"status": "archived"})
    db.seed_ideas(conn, records)
    assert db.get_idea(conn, 1)["status"] == "archived"  # type: ignore[index]


def _run(script: str, db_path: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 - fixed interpreter and repo script
        [sys.executable, str(REPO / "scripts" / script)],
        capture_output=True,
        text=True,
        env={"KNOWLEDGE_MCP_DB": str(db_path), "PATH": ""},
        check=False,
    )


def test_scripts_end_to_end(isolated_env: Path) -> None:
    init = _run("init_db.py", isolated_env)
    assert init.returncode == 0, init.stderr
    assert "Ideas stored: 0." in init.stdout

    first = _run("seed_db.py", isolated_env)
    assert first.returncode == 0, first.stderr
    assert "Inserted: 12. Skipped (already present): 0." in first.stdout

    second = _run("seed_db.py", isolated_env)
    assert "Inserted: 0. Skipped (already present): 12." in second.stdout
    assert "Ideas stored: 12." in second.stdout


# --- Snippets -------------------------------------------------------------------


def test_snippet_prefers_matching_passage_from_idea_text(seeded: sqlite3.Connection) -> None:
    (hit,) = db.search_ideas(seeded, "chokepoint")
    assert "[chokepoint]" in hit["snippet"]
    assert hit["snippet"] != "[chokepoint]"  # a passage, not just the matched word
    assert {"title", "insight"} <= set(hit["matched_fields"])


def test_domain_only_match_shows_problem_opening(seeded: sqlite3.Connection) -> None:
    hits = db.search_ideas(seeded, "supply chain")
    assert len(hits) == 3
    for hit in hits:
        assert hit["matched_fields"] == ["domain"]
        assert "[supply]" not in hit["snippet"]  # no echo of the domain label
        idea = db.get_idea(seeded, hit["id"])
        assert idea is not None and idea["problem"].startswith(hit["snippet"].rstrip("."))


def test_tags_only_match_never_shows_raw_json(seeded: sqlite3.Connection) -> None:
    hits = db.search_ideas(seeded, "credibility")
    tags_only = [h for h in hits if h["matched_fields"] == ["tags"]]
    assert tags_only, "expected at least one idea matching only by tag"
    for hit in tags_only:
        assert not hit["snippet"].startswith('["')


def test_snippets_contain_no_internal_markers(seeded: sqlite3.Connection) -> None:
    for query in ("supply chain", "risk", "chokepoint", "credible commitment"):
        for hit in db.search_ideas(seeded, query, limit=20):
            assert "\x02" not in hit["snippet"] and "\x03" not in hit["snippet"]


def test_long_problem_excerpt_is_trimmed(conn: sqlite3.Connection) -> None:
    long_problem = " ".join(f"word{i}" for i in range(60))
    db.create_idea(conn, title="Label only", domain="zzdomain", problem=long_problem, insight="x")
    (hit,) = db.search_ideas(conn, "zzdomain")
    assert hit["snippet"].endswith("...")
    assert len(hit["snippet"].split()) == db.EXCERPT_WORDS
