import unittest
from social2md_app.asr_audit import compare_segment, detect_issues


class AuditTests(unittest.TestCase):
    def test_disagreement_never_changes_original(self):
        r = compare_segment("电原", "电源", 0, 3)
        self.assertEqual(r["final_text"], "电原")
        self.assertEqual(r["status"], "REVIEW_REQUIRED")

    def test_third_model_conflict_requires_review(self):
        result = compare_segment("电源", "电源", 0, 2, third_text="电原")
        self.assertEqual(result["status"], "REVIEW_REQUIRED")
        self.assertEqual(result["final_text"], "电源")

    def test_missing_secondary_preserves_default(self):
        self.assertEqual(compare_segment("原文", None, 1, 4)["final_text"], "原文")

    def test_replacement_and_terms_are_candidates(self):
        r = detect_issues("电原�", [{"term": "电源", "aliases": ["电原"]}])
        self.assertEqual(
            {x["type"] for x in r}, {"term_candidate", "replacement_character"}
        )

    def test_punctuation_only_difference(self):
        self.assertEqual(
            compare_segment("电源，测试。", "电源测试", 0, 3)["status"], "AGREEMENT"
        )


class AuditIsolationTests(unittest.TestCase):
    def test_optional_failure_preserves_primary_and_source(self):
        import json
        import tempfile
        from pathlib import Path
        from types import SimpleNamespace
        from unittest.mock import patch
        from social2md_app.asr_audit import run_audit

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            source.mkdir()
            video = source / "test.mkv"
            video.write_bytes(b"original media")
            output = root / "audit"
            args = SimpleNamespace(
                input_dir=source,
                audit_output=str(output),
                audit_terms=None,
                audit_limit=1,
                audit_seconds=1,
                audit_full=False,
                audit_cache=str(root / "cache"),
                audit_python="unavailable-python",
                audit_timeout=10,
            )

            def invoke(command, **kwargs):
                if command[0] == "ffmpeg":
                    Path(command[-1]).write_bytes(b"pcm")
                elif command[0] == "unavailable-python":
                    raise FileNotFoundError("optional environment missing")
                else:
                    Path(command[-1]).write_text(
                        json.dumps(
                            {
                                "records": [
                                    {"clip": 1, "text": "原始文本", "quality": {}}
                                ]
                            }
                        )
                    )
                return SimpleNamespace(returncode=0)

            with patch(
                "social2md_app.asr_audit.subprocess.check_output",
                return_value='{"format":{"duration":1}}',
            ), patch("social2md_app.asr_audit.subprocess.run", side_effect=invoke):
                self.assertEqual(run_audit(args), 0)
            result = json.loads((output / "comparison.json").read_text())
            self.assertEqual(result["comparisons"][0]["final_text"], "原始文本")
            self.assertEqual(result["comparisons"][0]["status"], "REVIEW_REQUIRED")
            self.assertEqual(video.read_bytes(), b"original media")
            with self.assertRaises(FileExistsError):
                run_audit(args)


if __name__ == "__main__":
    unittest.main()
