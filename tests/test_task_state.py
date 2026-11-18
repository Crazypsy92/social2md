import sqlite3
import tempfile
import unittest
from pathlib import Path

from social2md_app.state import TaskState


class TaskStateTests(unittest.TestCase):
    def test_cursor_and_work_status_persist(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "state.sqlite3"
            with TaskState(path) as state:
                self.assertEqual(state.get_cursor(), 0)
                state.set_cursor(123456)
                state.mark_work("aweme-1", "DOWNLOADED", title="demo", video_path="/tmp/demo.mp4")
            with TaskState(path) as state:
                self.assertEqual(state.get_cursor(), 123456)
                work = state.get_work("aweme-1")
                self.assertEqual(work["status"], "DOWNLOADED")
                self.assertEqual(work["title"], "demo")
                self.assertEqual(state.status_counts()["DOWNLOADED"], 1)

    def test_same_content_id_isolated_by_platform(self):
        with tempfile.TemporaryDirectory() as temp:
            with TaskState(Path(temp) / "state.sqlite3") as state:
                state.mark_work("123", "COMPLETED", title="douyin", platform="douyin")
                state.mark_work("123", "PROCESSING", title="bilibili", platform="bilibili")
                self.assertEqual(state.get_work("123", "douyin")["title"], "douyin")
                self.assertEqual(state.get_work("123", "bilibili")["title"], "bilibili")

    def test_legacy_aweme_database_is_migrated(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "legacy.sqlite3"
            connection = sqlite3.connect(path)
            connection.execute(
                """CREATE TABLE works (
                    aweme_id TEXT PRIMARY KEY, status TEXT NOT NULL, title TEXT,
                    video_path TEXT, md_path TEXT, error TEXT, updated_at INTEGER NOT NULL
                )"""
            )
            connection.execute(
                "INSERT INTO works VALUES (?, ?, ?, ?, ?, ?, ?)",
                ("old-aweme", "COMPLETED", "old title", "/tmp/a.mp4", "/tmp/a.md", None, 123),
            )
            connection.commit()
            connection.close()

            with TaskState(path) as state:
                migrated = state.get_work("old-aweme", "douyin")
                self.assertEqual(migrated["status"], "COMPLETED")
                self.assertEqual(migrated["title"], "old title")
                self.assertIsNone(state.get_work("old-aweme", "bilibili"))


if __name__ == "__main__":
    unittest.main()
