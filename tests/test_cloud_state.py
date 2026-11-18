import tempfile
import unittest
from pathlib import Path

from cloud_state import CloudState


class CloudStateTests(unittest.TestCase):
    def test_cursor_and_work_status_persist(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "state.sqlite3"
            with CloudState(path) as state:
                self.assertEqual(state.get_cursor(), 0)
                state.set_cursor(123456)
                state.mark_work("aweme-1", "DOWNLOADED", title="demo", video_path="/tmp/demo.mp4")
            with CloudState(path) as state:
                self.assertEqual(state.get_cursor(), 123456)
                work = state.get_work("aweme-1")
                self.assertEqual(work["status"], "DOWNLOADED")
                self.assertEqual(work["title"], "demo")
                self.assertEqual(state.status_counts()["DOWNLOADED"], 1)


if __name__ == "__main__":
    unittest.main()
