from __future__ import annotations

import sqlite3
import time
from pathlib import Path
from typing import Any


class CloudState:
    """云端任务状态库；每个主页独立保存作品状态和分页游标。"""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.path, timeout=30)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.execute("PRAGMA synchronous=FULL")
        self.connection.execute(
            """
            CREATE TABLE IF NOT EXISTS works (
                aweme_id TEXT PRIMARY KEY,
                status TEXT NOT NULL,
                title TEXT,
                video_path TEXT,
                md_path TEXT,
                error TEXT,
                updated_at INTEGER NOT NULL
            )
            """
        )
        self.connection.execute(
            """
            CREATE TABLE IF NOT EXISTS metadata (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
            """
        )
        self.connection.commit()

    def close(self) -> None:
        self.connection.close()

    def __enter__(self) -> "CloudState":
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        self.close()

    def get_meta(self, key: str, default: str | None = None) -> str | None:
        row = self.connection.execute(
            "SELECT value FROM metadata WHERE key = ?", (key,)
        ).fetchone()
        return str(row["value"]) if row else default

    def set_meta(self, key: str, value: Any) -> None:
        self.connection.execute(
            """
            INSERT INTO metadata(key, value) VALUES(?, ?)
            ON CONFLICT(key) DO UPDATE SET value=excluded.value
            """,
            (key, str(value)),
        )
        self.connection.commit()

    def get_cursor(self, default: int = 0) -> int:
        value = self.get_meta("cursor")
        if value is None:
            return default
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    def set_cursor(self, cursor: int | str) -> None:
        self.set_meta("cursor", cursor)

    def get_work(self, aweme_id: str) -> dict | None:
        row = self.connection.execute(
            "SELECT * FROM works WHERE aweme_id = ?", (str(aweme_id),)
        ).fetchone()
        return dict(row) if row else None

    def mark_work(
        self,
        aweme_id: str,
        status: str,
        title: str | None = None,
        video_path: str | None = None,
        md_path: str | None = None,
        error: str | None = None,
    ) -> None:
        self.connection.execute(
            """
            INSERT INTO works(
                aweme_id, status, title, video_path, md_path, error, updated_at
            ) VALUES(?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(aweme_id) DO UPDATE SET
                status=excluded.status,
                title=COALESCE(excluded.title, works.title),
                video_path=COALESCE(excluded.video_path, works.video_path),
                md_path=COALESCE(excluded.md_path, works.md_path),
                error=excluded.error,
                updated_at=excluded.updated_at
            """,
            (
                str(aweme_id),
                status,
                title,
                video_path,
                md_path,
                error,
                int(time.time()),
            ),
        )
        self.connection.commit()

    def status_counts(self) -> dict[str, int]:
        rows = self.connection.execute(
            "SELECT status, COUNT(*) AS count FROM works GROUP BY status"
        ).fetchall()
        return {str(row["status"]): int(row["count"]) for row in rows}
