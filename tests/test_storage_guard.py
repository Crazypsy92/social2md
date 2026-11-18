import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from storage_guard import StorageGuard, StorageLimitExceeded


class StorageGuardTests(unittest.TestCase):
    def make_guard(self, used_percent, free_bytes=500, inode_percent=10):
        usage = SimpleNamespace(total=1000, used=int(used_percent * 10), free=free_bytes)
        statvfs = SimpleNamespace(f_files=1000, f_ffree=1000 - int(inode_percent * 10))
        return StorageGuard(
            [Path(tempfile.gettempdir())],
            pause_percent=95,
            resume_percent=90,
            min_free_bytes=100,
            disk_usage_fn=lambda _path: usage,
            statvfs_fn=lambda _path: statvfs,
        )

    def test_94_9_percent_does_not_pause(self):
        self.assertFalse(self.make_guard(94.9).should_pause())

    def test_95_percent_pauses(self):
        self.assertTrue(self.make_guard(95).should_pause())

    def test_resume_requires_below_90_percent(self):
        self.assertFalse(self.make_guard(90).can_resume())
        self.assertTrue(self.make_guard(89.9).can_resume())

    def test_inode_threshold_also_pauses(self):
        self.assertTrue(self.make_guard(50, inode_percent=95).should_pause())

    def test_minimum_free_space_pauses(self):
        self.assertTrue(self.make_guard(50, free_bytes=99).should_pause())

    def test_preflight_extra_space(self):
        guard = self.make_guard(50, free_bytes=500)
        with self.assertRaises(StorageLimitExceeded):
            guard.assert_can_start(extra_bytes=450)


if __name__ == "__main__":
    unittest.main()
