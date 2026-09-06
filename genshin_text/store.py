from __future__ import annotations

import sqlite3
import re
from pathlib import Path
from typing import Iterator


SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS documents (
    id INTEGER PRIMARY KEY,
    source_key TEXT NOT NULL UNIQUE,
    category TEXT NOT NULL,
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    source_url TEXT NOT NULL,
    payload_path TEXT,
    fetched_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_documents_category ON documents(category);
CREATE VIRTUAL TABLE IF NOT EXISTS documents_fts USING fts5(
    title, category, content, source_key UNINDEXED,
    tokenize='unicode61 remove_diacritics 2'
);
CREATE TABLE IF NOT EXISTS crawl_state (
    source_key TEXT PRIMARY KEY,
    status TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    detail TEXT
);
"""


class Store:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)

    @staticmethod
    def _fts_text(value: str) -> str:
        """Space CJK characters so FTS5 can index them without a CJK tokenizer."""
        tokens = re.findall(r"[\u3400-\u9fff]|[A-Za-z0-9_]+", value)
        return " ".join(tokens)

    @classmethod
    def _fts_expression(cls, query: str) -> str:
        tokens = cls._fts_text(query).split()
        return " AND ".join('"' + token.replace('"', '""') + '"' for token in tokens)

    def close(self) -> None:
        self.conn.close()

    def upsert(
        self, source_key: str, category: str, title: str, content: str,
        source_url: str, payload_path: str | None,
    ) -> None:
        row = self.conn.execute(
            "SELECT id FROM documents WHERE source_key = ?", (source_key,)
        ).fetchone()
        if row:
            self.conn.execute(
                """UPDATE documents SET category=?, title=?, content=?, source_url=?,
                   payload_path=?, fetched_at=CURRENT_TIMESTAMP WHERE id=?""",
                (category, title, content, source_url, payload_path, row["id"]),
            )
            self.conn.execute("DELETE FROM documents_fts WHERE source_key=?", (source_key,))
        self.conn.execute(
            """INSERT INTO documents(source_key,category,title,content,source_url,payload_path)
               VALUES(?,?,?,?,?,?) ON CONFLICT(source_key) DO NOTHING""",
            (source_key, category, title, content, source_url, payload_path),
        )
        self.conn.execute(
            "INSERT INTO documents_fts(title,category,content,source_key) VALUES(?,?,?,?)",
            (self._fts_text(title), self._fts_text(category), self._fts_text(content), source_key),
        )
        self.conn.execute(
            """INSERT INTO crawl_state(source_key,status,updated_at) VALUES(?,'done',CURRENT_TIMESTAMP)
               ON CONFLICT(source_key) DO UPDATE SET status='done', updated_at=CURRENT_TIMESTAMP, detail=NULL""",
            (source_key,),
        )
        self.conn.commit()

    def state(self, source_key: str) -> str | None:
        row = self.conn.execute("SELECT status FROM crawl_state WHERE source_key=?", (source_key,)).fetchone()
        return row["status"] if row else None

    def mark_failure(self, source_key: str, detail: str) -> None:
        self.conn.execute(
            """INSERT INTO crawl_state(source_key,status,detail,updated_at) VALUES(?,'failed',?,CURRENT_TIMESTAMP)
               ON CONFLICT(source_key) DO UPDATE SET status='failed', detail=excluded.detail, updated_at=CURRENT_TIMESTAMP""",
            (source_key, detail[:500]),
        )
        self.conn.commit()

    def categories(self) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT category, count(*) AS count FROM documents GROUP BY category ORDER BY category"
        ).fetchall()

    def get(self, source_key: str) -> sqlite3.Row | None:
        return self.conn.execute("SELECT * FROM documents WHERE source_key=?", (source_key,)).fetchone()

    def search(self, query: str = "", category: str = "", limit: int = 100) -> list[sqlite3.Row]:
        filters: list[str] = []
        values: list[object] = []
        if query.strip():
            # unicode61 has no Chinese word segmentation. LIKE preserves useful
            # character-substring lookup, such as searching "璃月" in "璃月港".
            escaped = query.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            filters.append("(d.title LIKE ? ESCAPE '\\' OR d.content LIKE ? ESCAPE '\\')")
            values.extend((f"%{escaped}%", f"%{escaped}%"))
            expression = self._fts_expression(query)
            if expression:
                filters.append("f.documents_fts MATCH ?")
                values.append(expression)
        if category:
            filters.append("d.category = ?")
            values.append(category)
        where = (" WHERE " + " AND ".join(filters)) if filters else ""
        values.append(limit)
        return self.conn.execute(
            "SELECT d.* FROM documents d JOIN documents_fts f ON f.source_key=d.source_key" + where +
            " ORDER BY d.category, d.title LIMIT ?", values
        ).fetchall()

    def iter_documents(self, query: str = "", category: str = "") -> Iterator[sqlite3.Row]:
        yield from self.search(query, category, limit=1_000_000)
