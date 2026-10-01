-- Schema version 1: ideas table with FTS5 full-text search.
-- Applied once by db.migrate(); later versions add new migrations, never edit this one.

CREATE TABLE IF NOT EXISTS ideas (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  title       TEXT NOT NULL CHECK (length(title) BETWEEN 3 AND 200),
  domain      TEXT NOT NULL,
  problem     TEXT NOT NULL,          -- the puzzle the idea addresses
  insight     TEXT NOT NULL,          -- the proposed answer or mechanism
  assumptions TEXT,                   -- baseline assumptions, optional
  tags        TEXT NOT NULL DEFAULT '[]'
              CHECK (json_valid(tags) AND json_type(tags) = 'array'),
  status      TEXT NOT NULL DEFAULT 'seed'
              CHECK (status IN ('seed','developing','mature','published','archived')),
  created_at  TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS ideas_domain_idx ON ideas(domain);
CREATE INDEX IF NOT EXISTS ideas_status_idx ON ideas(status);
CREATE INDEX IF NOT EXISTS ideas_created_idx ON ideas(created_at);

-- External-content FTS5 index: stores only the index, reads text from `ideas`.
CREATE VIRTUAL TABLE IF NOT EXISTS ideas_fts USING fts5(
  title, domain, problem, insight, assumptions, tags,
  content='ideas', content_rowid='id',
  tokenize='porter unicode61'
);

-- Triggers keep the index in step with the table.
CREATE TRIGGER IF NOT EXISTS ideas_ai AFTER INSERT ON ideas BEGIN
  INSERT INTO ideas_fts(rowid, title, domain, problem, insight, assumptions, tags)
  VALUES (new.id, new.title, new.domain, new.problem, new.insight, new.assumptions, new.tags);
END;

CREATE TRIGGER IF NOT EXISTS ideas_ad AFTER DELETE ON ideas BEGIN
  INSERT INTO ideas_fts(ideas_fts, rowid, title, domain, problem, insight, assumptions, tags)
  VALUES ('delete', old.id, old.title, old.domain, old.problem, old.insight, old.assumptions, old.tags);
END;

CREATE TRIGGER IF NOT EXISTS ideas_au AFTER UPDATE ON ideas BEGIN
  INSERT INTO ideas_fts(ideas_fts, rowid, title, domain, problem, insight, assumptions, tags)
  VALUES ('delete', old.id, old.title, old.domain, old.problem, old.insight, old.assumptions, old.tags);
  INSERT INTO ideas_fts(rowid, title, domain, problem, insight, assumptions, tags)
  VALUES (new.id, new.title, new.domain, new.problem, new.insight, new.assumptions, new.tags);
END;
