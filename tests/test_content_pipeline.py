from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from social2md_app.content_pipeline import (
    apply_evidence_corrections,
    detect_candidates,
    inventory_archive,
    process_samples,
    read_json,
)


class ContentPipelineTests(unittest.TestCase):
    def test_deterministic_candidates_cover_replacement_glossary_and_repeat(self):
        text = "电源BUG。电源BUG。电源BUG。重复识别片段这里再出现重复识别片段这里再出现�"
        terms = [{"term": "Buck", "aliases": ["Bug"]}]
        first = detect_candidates(text, terms)
        second = detect_candidates(text, terms)
        self.assertEqual(first, second)
        self.assertEqual(sum(x["rule"] == "replacement_character" for x in first), 1)
        self.assertEqual(sum(x["rule"] == "glossary_alias" for x in first), 3)
        self.assertGreaterEqual(sum(x["rule"] == "repeated_phrase" for x in first), 1)
        unrelated = detect_candidates("2077里有BUG。BUG。BUG。", terms)
        self.assertFalse(any(x["rule"] == "glossary_alias" for x in unrelated))

    def test_auto_correction_requires_two_independent_models_and_glossary(self):
        terms = [{"term": "Buck", "aliases": ["Bug"]}]
        two = [
            {"model": "whisper", "text": "Buck boost"},
            {"model": "funasr", "text": "buck boost"},
        ]
        fixed, record = apply_evidence_corrections("BUG BOOST", [{"original": "BUG", "target": "Buck", "independent_asr": two}], terms)
        self.assertEqual(fixed, "Buck BOOST")
        self.assertFalse(record[0]["audio_verified"])
        with self.assertRaises(ValueError):
            apply_evidence_corrections("BUG BOOST", [{"original": "BUG", "target": "Buck", "independent_asr": two[:1]}], terms)
        with self.assertRaises(ValueError):
            apply_evidence_corrections("BUG BOOST", [{"original": "BUG", "target": "Boost", "independent_asr": two}], terms)

    def test_processing_preserves_archive_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive = root / "archive"
            sample_dir = archive / "测试 UP"
            sample_dir.mkdir(parents=True)
            source = sample_dir / "电源笔记.md"
            original = (
                "# 电源笔记\n\n## 来源\n\nhttps://www.bilibili.com/video/BV123abc\n\n"
                "作者：测试 UP\n\n## 原文案\n\n说明\n\n## 口播转录\n\n"
                "电源BUG。电源电极控制工程师。\n"
            ).encode()
            source.write_bytes(original)
            terms = root / "terms.json"
            terms.write_text(json.dumps([{"term": "Buck", "aliases": ["Bug"]}], ensure_ascii=False), encoding="utf-8")
            samples = root / "samples.json"
            samples.write_text(json.dumps({"samples": [{
                "content_id": "BV123abc", "archive_path": "测试 UP/电源笔记.md",
                "content_route": "测试", "manual_candidates": [{"text": "电极控制工程师", "suggestions": ["电机控制工程师"], "reason": "待核"}],
                "argument_rows": [["论点", "证据", "推理", "落点"]],
                "summary_paragraphs": ["讲者提到电源项目。"], "highlights": []
            }]}, ensure_ascii=False), encoding="utf-8")
            pipeline = root / "pipeline"
            inventory = inventory_archive(archive, [{"term": "Buck", "aliases": ["Bug"]}])
            (pipeline / "progress.json").parent.mkdir(parents=True)
            (pipeline / "progress.json").write_text(json.dumps(inventory), encoding="utf-8")
            first = process_samples(archive, pipeline, samples, terms)
            self.assertEqual(source.read_bytes(), original)
            item = first["items"][0]
            self.assertEqual(item["status"], "REVIEW_REQUIRED")
            self.assertEqual(item["evidence_based_unverified_corrections"], 0)
            raw = pipeline / item["raw_backup"]
            self.assertEqual(raw.read_bytes(), original)
            corrected = (pipeline / item["corrected_path"]).read_text(encoding="utf-8")
            self.assertIn("BUG〔听辨存疑：候选“Buck”", corrected)
            self.assertIn("电极控制工程师〔听辨存疑", corrected)
            before = (pipeline / item["obsidian_path"]).read_bytes()
            second = process_samples(archive, pipeline, samples, terms)
            self.assertEqual((pipeline / item["obsidian_path"]).read_bytes(), before)
            self.assertEqual(second["items"][0]["source_sha256"], item["source_sha256"])

    def test_long_document_waits_for_explicit_flag(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); archive = root / "archive"; d = archive / "Long"; d.mkdir(parents=True)
            source = d / "long.md"
            source.write_text("# Long\n\n## 来源\n\nhttps://www.bilibili.com/video/BV999\n\n作者：Long\n\n## 口播转录\n\n" + "故事。" * 4000, encoding="utf-8")
            samples = root / "samples.json"
            samples.write_text(json.dumps({"samples": [{"content_id": "BV999", "archive_path": "Long/long.md", "content_route": "叙事", "argument_rows": [], "summary_paragraphs": [], "highlights": []}]}), encoding="utf-8")
            terms = root / "terms.json"; terms.write_text("[]", encoding="utf-8")
            pipeline = root / "pipeline"
            result = process_samples(archive, pipeline, samples, terms)
            self.assertEqual(result["items"][0]["status"], "LONG_PENDING")
            result = process_samples(archive, pipeline, samples, terms, include_long=True)
            self.assertTrue(result["items"][0]["long_document"])

    def test_remote_conflict_check_fails_closed(self):
        from social2md_app.content_pipeline import check_publish_conflict
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            subprocess.run(["git", "init", "--bare", str(root / "remote.git")], check=True, capture_output=True)
            repo = root / "repo"; repo.mkdir()
            subprocess.run(["git", "init", "-b", "main"], cwd=repo, check=True, capture_output=True)
            subprocess.run(["git", "config", "user.email", "test@example.invalid"], cwd=repo, check=True)
            subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, check=True)
            (repo / "file").write_text("one")
            subprocess.run(["git", "add", "file"], cwd=repo, check=True)
            subprocess.run(["git", "commit", "-m", "one"], cwd=repo, check=True, capture_output=True)
            subprocess.run(["git", "remote", "add", "origin", str(root / "remote.git")], cwd=repo, check=True)
            subprocess.run(["git", "push", "-u", "origin", "main"], cwd=repo, check=True, capture_output=True)
            ok, _ = check_publish_conflict(repo)
            self.assertTrue(ok)
            (repo / "file").write_text("two")
            subprocess.run(["git", "commit", "-am", "two"], cwd=repo, check=True, capture_output=True)
            subprocess.run(["git", "push", "origin", "main"], cwd=repo, check=True, capture_output=True)
            # The checked-out HEAD is now newer than origin only after remote is rewound; normal remote drift is covered below.
            (repo / "other").write_text("remote")
            subprocess.run(["git", "add", "other"], cwd=repo, check=True)
            subprocess.run(["git", "commit", "-m", "remote only"], cwd=repo, check=True, capture_output=True)
            subprocess.run(["git", "push", "origin", "main"], cwd=repo, check=True, capture_output=True)
            # Reset local to the previous tracked commit without modifying files.
            subprocess.run(["git", "reset", "--hard", "HEAD~1"], cwd=repo, check=True, capture_output=True)
            ok, message = check_publish_conflict(repo)
            self.assertFalse(ok)
            self.assertIn("未执行推送", message)


if __name__ == "__main__":
    unittest.main()
