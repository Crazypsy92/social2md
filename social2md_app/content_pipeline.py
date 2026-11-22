"""Conservative, local-first processing for archived Bilibili transcripts.

This module never edits source archive files or the video-ingestion SQLite DB.
It detects review candidates, preserves byte-identical backups, and renders
separate review and Obsidian copies. It does not infer audio truth from text.
"""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import re
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

VERSION = "0.1.1"
ID_RE = re.compile(r"https?://(?:www\.)?bilibili\.com/video/([A-Za-z0-9_-]+)")
ORAL_HEADING = "## 口播转录"
REPEAT_RE = re.compile(r"(?P<phrase>[\u3400-\u9fffA-Za-z0-9]{8,32})(?:[，,。；;、\s]{0,6})(?P=phrase)")
BAD_FILENAME = str.maketrans({"/": "／", "\\": "＼", ":": "：", "*": "＊", "?": "？", '"': "＂", "<": "＜", ">": "＞", "|": "｜"})
ROLE_STYLE = {
    "claim": "color: var(--color-cyan); font-weight: 600;",
    "evidence": "color: var(--color-green); font-weight: 600;",
    "limit": "color: var(--color-orange); font-weight: 600;",
}


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def safe_title(title: str) -> str:
    return re.sub(r"\s+", " ", title).strip().translate(BAD_FILENAME).strip(" .") or "untitled"


def read_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(value, ensure_ascii=False, indent=2) + "\n"
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as stream:
        stream.write(payload)
        temp = Path(stream.name)
    temp.replace(path)


def load_terms(path: Path) -> list[dict[str, Any]]:
    data = read_json(path, [])
    if not isinstance(data, list):
        raise ValueError("术语词典必须是 JSON 数组")
    terms = []
    for item in data:
        if not isinstance(item, dict) or not isinstance(item.get("term"), str):
            raise ValueError("每个术语项都必须包含字符串 term")
        aliases = item.get("aliases", [])
        if not isinstance(aliases, list) or not all(isinstance(x, str) for x in aliases):
            raise ValueError(f"术语 {item['term']} 的 aliases 必须是字符串数组")
        terms.append({"term": item["term"], "aliases": aliases})
    return terms


def parse_document(path: Path, archive_root: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    text = raw.decode("utf-8")
    title = next((line[2:].strip() for line in text.splitlines() if line.startswith("# ")), path.stem)
    source = ID_RE.search(text)
    if not source:
        raise ValueError("找不到 Bilibili BV 作品链接")
    oral_start = text.find(ORAL_HEADING)
    if oral_start < 0:
        raise ValueError("找不到口播转录区")
    body_start = oral_start + len(ORAL_HEADING)
    while body_start < len(text) and text[body_start] in "\r\n":
        body_start += 1
    next_heading = re.search(r"\n## \S", text[body_start:])
    body_end = body_start + next_heading.start() if next_heading else len(text)
    rel = path.resolve().relative_to(archive_root.resolve()).as_posix()
    return {
        "platform": "bilibili", "content_id": source.group(1), "title": title,
        "creator": path.parent.name, "source_url": f"https://www.bilibili.com/video/{source.group(1)}",
        "archive_path": rel, "raw_bytes": raw, "raw_text": text,
        "source_sha256": sha256(raw), "oral_start": body_start, "oral_end": body_end,
        "oral_text": text[body_start:body_end], "character_count": len(text[body_start:body_end]),
    }


def _candidate(rule: str, start: int, end: int, original: str, suggestions: list[str], reason: str) -> dict[str, Any]:
    return {
        "candidate_id": f"{rule}:{start}:{hashlib.sha256(original.encode('utf-8')).hexdigest()[:10]}",
        "rule": rule, "start": start, "end": end, "original": original,
        "suggestions": suggestions, "reason": reason, "status": "REVIEW_REQUIRED",
        "audio_verified": False,
    }


def detect_candidates(oral_text: str, terms: list[dict[str, Any]]) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    for match in re.finditer("�", oral_text):
        found.append(_candidate("replacement_character", match.start(), match.end(), match.group(), [], "U+FFFD 表示来源文本已含替换字符，不能从文本还原原词。"))
    for item in terms:
        for alias in item["aliases"]:
            pattern = re.compile(r"(?<![A-Za-z0-9])" + re.escape(alias) + r"(?![A-Za-z0-9])", re.IGNORECASE)
            for match in pattern.finditer(oral_text):
                # Buck/Bug is highly polysemous. Only surface it as a Buck candidate
                # when nearby power-electronics context makes the glossary relevant.
                if item["term"].casefold() == "buck" and alias.casefold() == "bug":
                    context = oral_text[max(0, match.start() - 80):min(len(oral_text), match.end() + 80)]
                    if not re.search(r"电源|DC\s*-?\s*DC|DCDC|BOOST|LDO|降压|开关电源", context, re.IGNORECASE):
                        continue
                found.append(_candidate("glossary_alias", match.start(), match.end(), match.group(), [item["term"]], "用户术语词典提供候选；未核听音频，不自动替换。"))
    for match in REPEAT_RE.finditer(oral_text):
        phrase = match.group("phrase")
        found.append(_candidate("repeated_phrase", match.start(), match.end(), match.group(), [], f"发现相邻重复片段“{phrase}”；可能是强调或识别重复，不能自动删除。"))
    # Suspicious all-caps/URL-like residue at the very end is a weak signal only.
    nonempty = [(m.start(), m.group()) for m in re.finditer(r"[^\n]+", oral_text) if m.group().strip()]
    if nonempty:
        start, tail = nonempty[-1]
        if re.fullmatch(r"[A-Z0-9 .:/_-]{16,}", tail.strip()) and ("//" in tail or ".COM" in tail):
            left = start + len(tail) - len(tail.lstrip())
            found.append(_candidate("possible_residual", left, start + len(tail.rstrip()), tail.strip(), [], "口播末尾出现疑似无关残留；可能是来源附加信息，需对照音频，不自动删除。"))
    # Stable de-duplication and ordering.
    unique = {item["candidate_id"]: item for item in found}
    return sorted(unique.values(), key=lambda item: (item["start"], item["rule"], item["candidate_id"]))


def inventory_archive(archive_root: Path, terms: list[dict[str, Any]], prior: dict[str, Any] | None = None) -> dict[str, Any]:
    prior_items = {x["key"]: x for x in (prior or {}).get("items", [])}
    items = []
    for path in sorted(archive_root.rglob("*.md"), key=lambda p: p.as_posix().casefold()):
        if path.name.startswith("_") or path.name in {"README.md"}:
            continue
        try:
            doc = parse_document(path, archive_root)
            hits = detect_candidates(doc["oral_text"], terms)
            key = f"bilibili:{doc['content_id']}"
            old = prior_items.get(key, {})
            status = "CANDIDATES_FOUND" if hits else "QUEUED"
            if old.get("source_sha256") == doc["source_sha256"] and old.get("status") in {"COMPLETED", "REVIEW_REQUIRED"}:
                status = old["status"]
            elif old.get("source_sha256") and old.get("source_sha256") != doc["source_sha256"]:
                status = "SOURCE_CHANGED"
            items.append({
                "key": key, "platform": "bilibili", "content_id": doc["content_id"],
                "creator": doc["creator"], "title": doc["title"], "archive_path": doc["archive_path"],
                "source_sha256": doc["source_sha256"], "character_count": doc["character_count"],
                "long_document": doc["character_count"] >= 10000, "candidate_count": len(hits),
                "candidate_rules": sorted({x["rule"] for x in hits}), "status": status,
            })
        except Exception as exc:
            items.append({"key": f"path:{path.relative_to(archive_root).as_posix()}", "archive_path": path.relative_to(archive_root).as_posix(), "status": "FAILED", "error": f"{type(exc).__name__}: {exc}"})
    return {"schema_version": 1, "pipeline_version": VERSION, "updated_at": utc_now(), "archive_root": archive_root.as_posix(), "scanned_count": len(items), "items": items}


def annotate_text(oral_text: str, candidates: list[dict[str, Any]]) -> str:
    edits: list[tuple[int, int, str]] = []
    for item in candidates:
        suggestions = item["suggestions"]
        if suggestions:
            marker = f"〔听辨存疑：候选“{' / '.join(suggestions)}”，未核听音频〕"
        elif item["rule"] == "replacement_character":
            marker = "〔听辨存疑：原文含替换字符，无法据文本还原〕"
        elif item["rule"] == "possible_residual":
            marker = "〔听辨存疑：疑似残留，未核听音频〕"
        else:
            marker = "〔听辨存疑：疑似重复，可能为口头强调，未删改〕"
        edits.append((item["end"], item["end"], marker))
    return apply_edits(oral_text, edits)


def apply_edits(text: str, edits: list[tuple[int, int, str]]) -> str:
    """Apply non-overlapping replacements and insertions against original offsets."""
    ordered = sorted(edits, key=lambda item: (item[0], item[1]))
    out: list[str] = []
    cursor = 0
    for start, end, replacement in ordered:
        if start < cursor or end < start or end > len(text):
            raise ValueError("重叠或越界的校订操作")
        out.extend((text[cursor:start], replacement))
        cursor = end
    out.append(text[cursor:])
    return "".join(out)


def apply_evidence_corrections(oral_text: str, corrections: list[dict[str, Any]], terms: list[dict[str, Any]]) -> tuple[str, list[dict[str, Any]]]:
    """Apply only configured corrections backed by two independent ASR outputs and glossary."""
    edits = []
    records = []
    for correction in corrections:
        source = correction["original"]
        target = correction["target"]
        matching_term = next((item for item in terms if item["term"].casefold() == target.casefold()), None)
        if matching_term is None or source.casefold() not in {alias.casefold() for alias in matching_term["aliases"]}:
            raise ValueError(f"自动候选目标不在技术词典中：{target}")
        evidence = correction.get("independent_asr", [])
        models = {item.get("model") for item in evidence}
        if len(models) < 2 or any(not item.get("text") or not re.search(r"(?<![A-Za-z0-9])" + re.escape(target) + r"(?![A-Za-z0-9])", item["text"], re.IGNORECASE) for item in evidence):
            raise ValueError(f"自动校订 {source} → {target} 缺少两个独立识别器的一致证据")
        offsets = [m.start() for m in re.finditer(re.escape(source), oral_text, re.IGNORECASE)]
        occurrence = int(correction.get("occurrence", 1))
        if occurrence < 1 or len(offsets) < occurrence:
            raise ValueError(f"待校订文本不存在或出现次数不足：{source}")
        start = offsets[occurrence - 1]
        edits.append((start, start + len(source), target))
        records.append({
            "original": oral_text[start:start + len(source)], "target": target,
            "start": start, "end": start + len(source),
            "evidence_type": "independent_asr_consensus_plus_user_glossary",
            "independent_asr": evidence, "audio_verified": False,
            "reason": correction.get("reason", ""),
        })
    return apply_edits(oral_text, edits), records


def apply_highlights(text: str, highlights: list[dict[str, str]]) -> str:
    result = text
    for highlight in highlights:
        snippet, role = highlight["text"], highlight["role"]
        if role not in ROLE_STYLE or snippet not in result:
            raise ValueError(f"高亮片段缺失或角色无效：{snippet[:50]}")
        result = result.replace(snippet, f'<span style="{ROLE_STYLE[role]}">{snippet}</span>', 1)
    return result


def render_corrected(doc: dict[str, Any], oral_review: str) -> str:
    text = doc["raw_text"]
    text = text[:doc["oral_start"]] + oral_review + text[doc["oral_end"]:]
    text = text.replace(ORAL_HEADING, "## 口播转录 · 校订阅读版", 1)
    insertion = "\n\n> 校订边界：基于 ASR 文本与可用词典 / 交叉识别材料；本轮未由人工核听音频。候选只作待核标记，未静默替换。\n"
    header_end = text.find("\n", text.find("## 口播转录 · 校订阅读版"))
    return text[:header_end] + insertion + text[header_end:]


def render_note(doc: dict[str, Any], oral_review: str, sample: dict[str, Any], raw_backup: str) -> str:
    title = doc["title"]
    rows = sample["argument_rows"]
    lines = [f"## {title}", "", f"> [!info] 来源 · Bilibili · UP 主：{doc['creator']}", f"> {doc['source_url']}", "", "> [!abstract] 观点速览", ">", "> | 核心论点 | 具体案例 / 原文依据 | 论据如何支撑观点 | 最终落点 |", "> | --- | --- | --- | --- |"]
    for row in rows:
        lines.append("> | " + " | ".join(cell.replace("|", "\\|").replace("\n", " ") for cell in row) + " |")
    lines.extend(["", "> [!summary] 浓缩正文", ">"])
    for para in sample["summary_paragraphs"]:
        lines.append("> 　　" + para)
        lines.append(">")
    note = sample.get("evidence_note", "")
    lines.extend(["", "> [!note] 校订与证据边界", ">", f"> 本稿基于归档 ASR 文本；人工核听：否。原始 Markdown 已逐字另存于 `{raw_backup}`。{note}仅把满足两种独立识别器与词典条件的词形候选写入校订稿；其余候选只作待核标记，不把文本证据冒充音频核验。", "", "> [!quote]- 口播转录 · 断句校订版", ">", "> 来源归档：ASR 原始段落保留；校订稿中的改字与待核标记均可在差异记录中追溯，原始备份见上方路径。", ">"])
    highlighted_oral = apply_highlights(oral_review, sample.get("highlights", []))
    for para in re.split(r"\n\s*\n", highlighted_oral.strip()):
        if not para.strip():
            continue
        for line in para.splitlines():
            lines.append("> 　　" + line)
        lines.append(">")
    return "\n".join(lines).rstrip() + "\n"


def write_text_immutable(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = text.encode("utf-8")
    if path.exists():
        if path.read_bytes() != payload:
            raise FileExistsError(f"拒绝覆盖已有且内容不同的输出：{path}")
        return
    path.write_bytes(payload)


def process_samples(archive_root: Path, pipeline_root: Path, sample_config: Path, terms_path: Path, max_ordinary: int = 3, include_long: bool = False) -> dict[str, Any]:
    pipeline_root.mkdir(parents=True, exist_ok=True)
    lock_id = sha256(str(pipeline_root.resolve()).encode("utf-8"))[:16]
    lock_path = Path(tempfile.gettempdir()) / f"social2md-content-{lock_id}.lock"
    with lock_path.open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError("内容加工任务已在运行；本轮退出且未覆盖文件。") from exc
        config = read_json(sample_config)
        manifest_path = pipeline_root / "processed_items.json"
        old_manifest = read_json(manifest_path, {"schema_version": 1, "items": []})
        old = {x["content_id"]: x for x in old_manifest.get("items", [])}
        terms = load_terms(terms_path)
        processed: list[dict[str, Any]] = []
        ordinary_count = 0
        for sample in config["samples"]:
            source = (archive_root / sample["archive_path"]).resolve()
            source.relative_to(archive_root.resolve())
            doc = parse_document(source, archive_root)
            if doc["content_id"] != sample["content_id"]:
                raise ValueError(f"样本配置 BV 号与来源不一致：{sample['content_id']}")
            source_hash = doc["source_sha256"]
            prior = old.get(doc["content_id"], {})
            if prior.get("source_sha256") and prior["source_sha256"] != source_hash:
                processed.append({**prior, "status": "SOURCE_CHANGED", "error": "归档源哈希变化，拒绝覆盖既有加工结果。"})
                continue
            if prior.get("source_sha256") == source_hash and prior.get("status") in {"COMPLETED", "REVIEW_REQUIRED"} and all((pipeline_root / prior.get(k, "__missing__")).is_file() for k in ("raw_backup", "corrected_path", "obsidian_path", "diff_path", "candidates_path")):
                processed.append(prior)
                continue
            is_long = doc["character_count"] >= 10000
            if is_long and not include_long:
                processed.append({"platform": "bilibili", "content_id": doc["content_id"], "title": doc["title"], "status": "LONG_PENDING", "source_sha256": source_hash, "archive_path": doc["archive_path"], "error": "超长材料需单独运行 --include-long。"})
                continue
            if not is_long:
                if ordinary_count >= max_ordinary:
                    processed.append({"platform": "bilibili", "content_id": doc["content_id"], "title": doc["title"], "status": "QUEUED", "source_sha256": source_hash, "archive_path": doc["archive_path"]})
                    continue
                ordinary_count += 1
            corrected_oral, applied = apply_evidence_corrections(doc["oral_text"], sample.get("evidence_corrections", []), terms)
            candidates = detect_candidates(corrected_oral, terms)
            manual = sample.get("manual_candidates", [])
            for hint in manual:
                needle = hint["text"]
                starts = [m.start() for m in re.finditer(re.escape(needle), corrected_oral)]
                if not starts:
                    raise ValueError(f"手工待核短语不存在于原文：{needle}")
                for start in starts if hint.get("all_occurrences") else starts[:1]:
                    candidates.append(_candidate("manual_review", start, start + len(needle), needle, hint.get("suggestions", []), hint["reason"]))
            candidates.sort(key=lambda x: (x["start"], x["rule"], x["candidate_id"]))
            oral_review = annotate_text(corrected_oral, candidates)
            slug = safe_title(doc["title"])
            raw_rel = Path("raw") / doc["creator"] / f"{slug}.md"
            corrected_rel = Path("corrected") / doc["creator"] / f"{slug} · 校订稿.md"
            note_rel = Path("obsidian") / doc["creator"] / f"{slug}.md"
            diff_rel = Path("diffs") / doc["creator"] / f"{slug}.diff.json"
            candidates_rel = Path("candidates") / doc["creator"] / f"{slug}.json"
            raw_path = pipeline_root / raw_rel
            corrected_path = pipeline_root / corrected_rel
            note_path = pipeline_root / note_rel
            diff_path = pipeline_root / diff_rel
            candidates_path = pipeline_root / candidates_rel
            raw_path.parent.mkdir(parents=True, exist_ok=True)
            if raw_path.exists() and raw_path.read_bytes() != doc["raw_bytes"]:
                raise FileExistsError(f"拒绝覆盖原文备份：{raw_path}")
            raw_path.write_bytes(doc["raw_bytes"])
            corrected = render_corrected(doc, oral_review)
            note = render_note(doc, oral_review, sample, raw_rel.as_posix())
            diff = {
                "schema_version": 1, "source_sha256": source_hash,
                "corrected_sha256": sha256(corrected.encode("utf-8")),
                "audio_verified": False, "applied_text_replacements": applied,
                "applied_text_deletions": [], "inserted_review_markers": [
                    {"candidate_id": x["candidate_id"], "original": x["original"], "suggestions": x["suggestions"], "rule": x["rule"], "status": "REVIEW_REQUIRED"} for x in candidates
                ],
                "original_character_count": len(doc["raw_text"]),
                "review_character_count": len(corrected),
            }
            write_text_immutable(corrected_path, corrected)
            write_text_immutable(note_path, note)
            atomic_json(diff_path, diff)
            atomic_json(candidates_path, {"source_sha256": source_hash, "audio_verified": False, "candidates": candidates})
            unresolved = len(candidates)
            record = {
                "platform": "bilibili", "content_id": doc["content_id"], "creator": doc["creator"],
                "title": doc["title"], "source_url": doc["source_url"], "archive_path": doc["archive_path"],
                "source_sha256": source_hash, "character_count": doc["character_count"],
                "content_route": sample["content_route"], "long_document": is_long,
                "status": "REVIEW_REQUIRED" if unresolved else "COMPLETED",
                "candidate_count": unresolved, "verified_corrections": 0,
                "evidence_based_unverified_corrections": len(applied),
                "incorrect_corrections": 0, "omissions": 0,
                "raw_backup": raw_rel.as_posix(), "corrected_path": corrected_rel.as_posix(),
                "obsidian_path": note_rel.as_posix(), "diff_path": diff_rel.as_posix(),
                "candidates_path": candidates_rel.as_posix(), "pipeline_version": VERSION,
                "audio_verified": False,
            }
            processed.append(record)
        new_manifest = {"schema_version": 1, "pipeline_version": VERSION, "updated_at": utc_now(), "deduplication_key": ["platform", "content_id"], "items": processed}
        atomic_json(manifest_path, new_manifest)
        progress_path = pipeline_root / "progress.json"
        progress = read_json(progress_path, {"schema_version": 1, "items": []})
        progress_by_id = {x.get("content_id"): x for x in progress.get("items", [])}
        for item in processed:
            current = progress_by_id.get(item.get("content_id"))
            if current is not None:
                current["status"] = item["status"]
                current["candidate_count"] = item.get("candidate_count", 0)
                current["processed_outputs"] = [item[k] for k in ("corrected_path", "obsidian_path", "diff_path", "candidates_path") if item.get(k)]
        progress["updated_at"] = utc_now()
        atomic_json(progress_path, progress)
        return new_manifest


def scan_command(args: argparse.Namespace) -> int:
    archive = Path(args.archive_root).resolve()
    pipeline = Path(args.pipeline_root).resolve()
    terms = load_terms(Path(args.terms))
    lock_id = sha256(str(pipeline.resolve()).encode("utf-8"))[:16]
    lock_path = Path(tempfile.gettempdir()) / f"social2md-content-{lock_id}.lock"
    pipeline.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print("内容加工任务已在运行；本轮退出。", file=sys.stderr)
            return 2
        report = inventory_archive(archive, terms, read_json(pipeline / "progress.json", {}))
        atomic_json(pipeline / "progress.json", report)
    counts: dict[str, int] = {}
    for item in report["items"]:
        counts[item["status"]] = counts.get(item["status"], 0) + 1
    print(f"扫描 {report['scanned_count']} 篇归档；状态：{counts}。仅生成候选清单，未改写来源。")
    return 0


def process_command(args: argparse.Namespace) -> int:
    try:
        result = process_samples(Path(args.archive_root).resolve(), Path(args.pipeline_root).resolve(), Path(args.samples), Path(args.terms), args.max_ordinary, args.include_long)
    except Exception as exc:
        if "已在运行" not in str(exc):
            pipeline = Path(args.pipeline_root).resolve()
            manifest_path = pipeline / "processed_items.json"
            manifest = read_json(manifest_path, {"schema_version": 1, "pipeline_version": VERSION, "items": []})
            manifest["last_failure"] = {
                "status": "FAILED", "updated_at": utc_now(),
                "sample_ids": [x.get("content_id") for x in read_json(Path(args.samples), {}).get("samples", [])],
                "reason": f"{type(exc).__name__}: {exc}",
            }
            atomic_json(manifest_path, manifest)
        print(f"内容加工失败：{type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    counts: dict[str, int] = {}
    for item in result["items"]:
        counts[item["status"]] = counts.get(item["status"], 0) + 1
    print(f"处理清单已更新；状态：{counts}。所有输入归档保持不变。")
    return 0


def plan_command(args: argparse.Namespace) -> int:
    pipeline = Path(args.pipeline_root).resolve()
    pipeline.mkdir(parents=True, exist_ok=True)
    lock_id = sha256(str(pipeline).encode("utf-8"))[:16]
    lock_path = Path(tempfile.gettempdir()) / f"social2md-content-{lock_id}.lock"
    with lock_path.open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print("内容加工任务已在运行；计划未更新。", file=sys.stderr)
            return 2
        progress_path = pipeline / "progress.json"
        progress = read_json(progress_path)
        if progress is None:
            print("缺少 progress.json；请先运行 scan。", file=sys.stderr)
            return 2
        manifest = read_json(pipeline / "processed_items.json", {"items": []})
        processed = {x.get("content_id"): x for x in manifest.get("items", [])}
        ordinary, long_queue, skipped = [], [], []
        for item in progress["items"]:
            cid = item.get("content_id")
            if not cid or item.get("status") == "FAILED":
                skipped.append({"content_id": cid, "status": item.get("status"), "reason": item.get("error", "扫描失败")})
                continue
            old = processed.get(cid)
            if old:
                if old.get("source_sha256") != item.get("source_sha256"):
                    skipped.append({"content_id": cid, "status": "SOURCE_CHANGED", "reason": "源 SHA-256 与处理清单不一致"})
                    continue
                if old.get("status") in {"COMPLETED", "REVIEW_REQUIRED", "PROCESSING"}:
                    skipped.append({"content_id": cid, "status": old["status"], "reason": "已有相同源哈希的结果或处理中记录"})
                    continue
            if item.get("status") == "SOURCE_CHANGED":
                skipped.append({"content_id": cid, "status": "SOURCE_CHANGED", "reason": "扫描发现源文件变化"})
                continue
            row = {k: item.get(k) for k in ("platform", "content_id", "creator", "title", "archive_path", "source_sha256", "character_count", "candidate_count")}
            row["status"] = "LONG_PENDING" if item.get("long_document") else "QUEUED"
            if item.get("long_document"):
                long_queue.append(row)
            elif len(ordinary) < args.max_ordinary:
                ordinary.append(row)
        plan = {
            "schema_version": 1, "pipeline_version": VERSION, "updated_at": utc_now(),
            "ordinary_limit": args.max_ordinary, "ordinary_batch": ordinary,
            "long_documents_separate": long_queue, "skipped": skipped,
        }
        atomic_json(pipeline / "next_batch.json", plan)
    print(f"下一批普通文档：{len(ordinary)} 篇；超长文档单独排队：{len(long_queue)} 篇；跳过/已处理：{len(skipped)}。")
    if not ordinary and not long_queue:
        print("没有待处理内容；正常退出。")
    return 0


def check_publish_conflict(repo: Path, branch: str = "main") -> tuple[bool, str]:
    """Fail closed unless local HEAD exactly matches the fetched remote branch."""
    fetch = subprocess.run(["git", "fetch", "origin", branch], cwd=repo, capture_output=True, text=True)
    if fetch.returncode:
        return False, fetch.stderr.strip() or "git fetch 失败"
    local = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True)
    remote = subprocess.run(["git", "rev-parse", f"origin/{branch}"], cwd=repo, capture_output=True, text=True)
    if local.returncode or remote.returncode:
        return False, "无法解析本地或远端分支头"
    if local.stdout.strip() != remote.stdout.strip():
        return False, f"推送冲突保护：HEAD 与 origin/{branch} 不一致；先人工同步并重新审查，未执行推送。"
    return True, "本地 main 与 origin/main 一致。"


def publish_command(args: argparse.Namespace) -> int:
    repo = Path(args.repo).resolve()
    pipeline = repo / "docs/content_pipeline"
    lock_id = sha256(str(pipeline.resolve()).encode("utf-8"))[:16]
    lock_path = Path(tempfile.gettempdir()) / f"social2md-content-{lock_id}.lock"
    with lock_path.open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print("内容加工任务正在写入；拒绝推送。", file=sys.stderr)
            return 2
        return _publish_locked(args, repo)


def _publish_locked(args: argparse.Namespace, repo: Path) -> int:
    if args.branch != "main":
        print("本项目仅允许向 main 推送；未作修改。", file=sys.stderr)
        return 2
    branch = subprocess.run(["git", "branch", "--show-current"], cwd=repo, capture_output=True, text=True)
    if branch.returncode or branch.stdout.strip() != "main":
        print("当前分支不是 main；未暂存或推送。", file=sys.stderr)
        return 2
    status = subprocess.run(["git", "-c", "core.quotePath=false", "status", "--porcelain", "--untracked-files=all"], cwd=repo, capture_output=True, text=True)
    if status.returncode:
        print(status.stderr.strip(), file=sys.stderr)
        return 2
    changed = []
    for line in status.stdout.splitlines():
        name = line[3:].split(" -> ")[-1]
        changed.append(name)
    outside = [name for name in changed if not name.startswith("docs/content_pipeline/")]
    if outside:
        print(f"工作区含加工目录以外的更改，拒绝自动暂存：{outside}", file=sys.stderr)
        return 2
    ok, message = check_publish_conflict(repo, "main")
    if not ok:
        print(message, file=sys.stderr)
        return 3
    if not changed:
        print("没有待推送的加工结果。")
        return 0
    add = subprocess.run(["git", "add", "--", "docs/content_pipeline"], cwd=repo, capture_output=True, text=True)
    if add.returncode:
        print(add.stderr.strip(), file=sys.stderr)
        return 2
    diff = subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=repo)
    if diff.returncode == 0:
        print("加工目录没有新的变更。")
        return 0
    commit = subprocess.run(["git", "commit", "-m", args.message], cwd=repo, capture_output=True, text=True)
    if commit.returncode:
        print(commit.stderr.strip(), file=sys.stderr)
        return 2
    push = subprocess.run(["git", "push", "origin", "main"], cwd=repo, capture_output=True, text=True)
    if push.returncode:
        print("推送失败；本地提交与加工结果均保留，可在解决远端冲突后重试。\n" + push.stderr.strip(), file=sys.stderr)
        return 4
    print(push.stdout.strip() or "加工结果已推送到 origin/main。")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Social2MD 归档文本的保守校订与 Obsidian 笔记试验")
    subs = parser.add_subparsers(dest="command", required=True)
    scan = subs.add_parser("scan", help="确定性扫描归档并更新候选进度清单")
    scan.add_argument("--archive-root", default="docs/archives/bilibili")
    scan.add_argument("--pipeline-root", default="docs/content_pipeline")
    scan.add_argument("--terms", default="docs/asr_terms.example.json")
    scan.set_defaults(func=scan_command)
    plan = subs.add_parser("plan", help="按来源哈希、状态和长度生成幂等的下一批清单")
    plan.add_argument("--pipeline-root", default="docs/content_pipeline")
    plan.add_argument("--max-ordinary", type=int, default=3)
    plan.set_defaults(func=plan_command)
    process = subs.add_parser("process-samples", help="运行受限样本加工；超长样本需显式 --include-long")
    process.add_argument("--archive-root", default="docs/archives/bilibili")
    process.add_argument("--pipeline-root", default="docs/content_pipeline")
    process.add_argument("--samples", default="docs/content_pipeline/samples.json")
    process.add_argument("--terms", default="docs/asr_terms.example.json")
    process.add_argument("--max-ordinary", type=int, default=3)
    process.add_argument("--include-long", action="store_true")
    process.set_defaults(func=process_command)
    publish = subs.add_parser("publish", help="只在 main 与远端同步且工作区仅有加工结果时推送")
    publish.add_argument("--repo", default=".")
    publish.add_argument("--branch", default="main")
    publish.add_argument("--message", default="Publish archived content processing results")
    publish.set_defaults(func=publish_command)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
