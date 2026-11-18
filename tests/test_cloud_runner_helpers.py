import tempfile
import unittest
from pathlib import Path

from cloud_runner import is_low_confidence, is_valid_markdown


class CloudRunnerHelperTests(unittest.TestCase):
    def test_valid_transcript_markdown(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "valid.md"
            path.write_text("# title\n\n## 口播转录\n\n这是一段有效转录文本。", encoding="utf-8")
            self.assertTrue(is_valid_markdown(path))

    def test_placeholder_markdown_is_invalid(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "empty.md"
            path.write_text("# title\n\n## 口播转录\n\n（未识别到内容）", encoding="utf-8")
            self.assertFalse(is_valid_markdown(path))

    def test_low_confidence_detection(self):
        self.assertTrue(is_low_confidence({"quality": {"avg_logprob": -1.2, "max_compression": 1.0}}))
        self.assertFalse(is_low_confidence({"quality": {"avg_logprob": -0.2, "max_compression": 1.0}}))


if __name__ == "__main__":
    unittest.main()
