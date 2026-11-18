from __future__ import annotations

import sqlite3
import time
from pathlib import Path
from typing import Any


class TaskState:
    """统一任务状态库，以 platform + content_id 作为跨平台唯一键。"""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.path, timeout=30)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.execute("PRAGMA synchronous=FULL")
        self._initialize()

    def _initialize(self) -> None:
        existing = self.connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='works'"
        ).fetchone()
        legacy_table = False
        if existing:
            columns = {
                row["name"]
                for row in self.connection.execute("PRAGMA table_info(works)").fetchall()
            }
            if "platform" not in columns or "content_id" not in columns:
                self.connection.execute("ALTER TABLE works RENAME TO works_legacy")
                legacy_table = True

        self.connection.execute(
            """
            CREATE TABLE IF NOT EXISTS works (
                platform TEXT NOT NULL,
                content_id TEXT NOT NULL,
                status TEXT NOT NULL,
                title TEXT,
                video_path TEXT,
                md_path TEXT,
                error TEXT,
                updated_at INTEGER NOT NULL,
                PRIMARY KEY (platform, content_id)
            )
            """
        )
        if legacy_table:
            legacy_columns = {
                row["name"]
                for row in self.connection.execute("PRAGMA table_info(works_legacy)").fetchall()
            }
            legacy_id = "aweme_id" if "aweme_id" in legacy_columns else "content_id"
            self.connection.execute(
                f"""
                INSERT OR REPLACE INTO works(
                    platform, content_id, status, title, video_path, md_path, error, updated_at
                )
                SELECT 'douyin', CAST({legacy_id} AS TEXT), status, title,
                       video_path, md_path, error, updated_at
                FROM works_legacy
                """
            )
            self.connection.execute("DROP TABLE works_legacy")

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

    def __enter__(self) -> "TaskState":
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

    def get_work(self, content_id: str, platform: str = "douyin") -> dict | None:
        row = self.connection.execute(
            "SELECT * FROM works WHERE platform = ? AND content_id = ?",
            (platform, str(content_id)),
        ).fetchone()
        return dict(row) if row else None

    def mark_work(
        self,
        content_id: str,
        status: str,
        title: str | None = None,
        video_path: str | None = None,
        md_path: str | None = None,
        error: str | None = None,
        platform: str = "douyin",
    ) -> None:
        self.connection.execute(
            """
            INSERT INTO works(
                platform, content_id, status, title, video_path, md_path, error, updated_at
            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(platform, content_id) DO UPDATE SET
                status=excluded.status,
                title=COALESCE(excluded.title, works.title),
                video_path=COALESCE(excluded.video_path, works.video_path),
                md_path=COALESCE(excluded.md_path, works.md_path),
                error=excluded.error,
                updated_at=excluded.updated_at
            """,
            (
                platform, str(content_id), status, title, video_path, md_path,
                error, int(time.time()),
            ),
        )
        self.connection.commit()

    def status_counts(self, platform: str | None = None) -> dict[str, int]:
        if platform is None:
            rows = self.connection.execute(
                "SELECT status, COUNT(*) AS count FROM works GROUP BY status"
            ).fetchall()
        else:
            rows = self.connection.execute(
                "SELECT status, COUNT(*) AS count FROM works "
                "WHERE platform = ? GROUP BY status",
                (platform,),
            ).fetchall()
        return {str(row["status"]): int(row["count"]) for row in rows}
