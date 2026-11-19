from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
import tempfile
from pathlib import Path

from .bilibili import BilibiliAdapter, access_error, canonical_url
from .state import TaskState
from .storage import StorageGuard, StorageLimitExceeded


def item_metadata(info: dict) -> dict:
    source_url = canonical_url(info["webpage_url"])
    # 分 P 的 ID 各不相同，避免一个 BV 下不同视频互相覆盖。
    content_id = str(info["id"])
    if not re.fullmatch(r"[A-Za-z0-9_-]+", content_id):
        raise ValueError("Bilibili 返回了无效的作品标识")
    return {
        "content_id": content_id,
        "source_url": source_url,
        "title": str(info.get("title") or content_id),
        "description": str(info.get("description") or ""),
        "author": str(info.get("uploader") or ""),
    }


def run_bilibili(args) -> int:
    from .cli import _project_path, _safe_name

    try:
        source_url = canonical_url(args.url)
    except ValueError as exc:
        print(exc)
        return 2
    project_root = Path(__file__).resolve().parents[1]
    source_key = hashlib.sha256(source_url.encode()).hexdigest()[:20]
    label = _safe_name(args.blogger if args.blogger != "未分类" else f"bilibili_{source_key}")
    download_dir = _project_path(args.download_dir, project_root / "videos" / label)
    out_dir = _project_path(args.out_dir, project_root / "output" / label)
    state_dir = _project_path(args.state_dir, project_root / "state")
    export_dir = _project_path(args.export_dir, project_root / "exports" / label)
    for directory in (download_dir, out_dir, state_dir, export_dir):
        directory.mkdir(parents=True, exist_ok=True)
    guard = StorageGuard(
        [project_root, download_dir, out_dir, state_dir, export_dir,
         Path(tempfile.gettempdir()), Path(os.environ.get("HF_HOME", Path.home() / ".cache/huggingface"))],
        pause_percent=args.pause_percent, resume_percent=args.resume_percent,
        min_free_bytes=int(args.min_free_gib * 1024**3), poll_seconds=args.poll_seconds,
    )
    if args.dry_run:
        guard.assert_can_start()
        print("DRY RUN：Bilibili 链接与磁盘检查通过；未联网、未读取 Cookie、未下载。")
        print(StorageGuard.format_snapshot(guard.snapshot()))
        return 0

    # 同一来源禁止两个任务同时改写状态和媒体。
    with (state_dir / f"bilibili_{source_key}.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print("该 Bilibili 来源已有任务运行，请等待现有任务结束。")
            return 2
        with TaskState(state_dir / f"bilibili_{source_key}.sqlite3") as state:
            try:
                guard.assert_can_start(was_paused=state.get_meta("paused", "0") == "1")
                state.set_meta("paused", "0")
                return _run_items(args, state, guard, download_dir, out_dir, export_dir, label, source_url)
            except StorageLimitExceeded as exc:
                state.set_meta("paused", "1")
                print(f"PAUSED_STORAGE: {exc}")
                return 75
            except KeyboardInterrupt:
                print("已中断；媒体、作品状态及扫描位置已保留。")
                return 130
            except Exception as exc:
                message = access_error(exc)
                state.set_meta("last_error", message)
                print(message)
                return 1


def _run_items(args, state, guard, download_dir, out_dir, export_dir, label, source_url):
    from .cli import _safe_name, export_markdown_checkpoint, is_valid_markdown, process_media_task

    adapter = BilibiliAdapter()
    processed = 0
    seen = set()
    state.set_meta("scan_complete", "0")
    try:
        # 恢复时重新分页扫描并按作品状态去重，避免空间新增视频导致偏移游标漏项。
        for index, entry in enumerate(adapter.entries(source_url), 1):
            guard.assert_can_start()
            for info in adapter.resolve(entry):
                metadata = item_metadata(info)
                content_id = metadata["content_id"]
                if content_id in seen:
                    continue
                seen.add(content_id)
                if args.max_items and processed >= args.max_items:
                    return 0
                state.set_cursor(index)
                state.set_meta("last_content_id", content_id)
                record = state.get_work(content_id, platform="bilibili")
                if record and not args.force:
                    source_retained = record.get("video_path") and Path(record["video_path"]).is_file()
                    if (record["status"] == "COMPLETED" and record.get("md_path")
                            and is_valid_markdown(Path(record["md_path"]))
                            and (not args.keep_source or source_retained)):
                        processed += 1
                        continue
                    if record["status"] == "REVIEW_REQUIRED" and not args.retry_review:
                        processed += 1
                        continue

                target = download_dir / f"{content_id}_video.mkv"
                recorded_md_path = Path(record["md_path"]) if record and record.get("md_path") else None
                if recorded_md_path and recorded_md_path.is_file():
                    md_path = recorded_md_path
                else:
                    title_stem = _safe_name(metadata["title"]).encode("utf-8")[:180]
                    title_stem = title_stem.decode("utf-8", errors="ignore").rstrip("._-") or content_id
                    md_path = out_dir / f"{title_stem}_{content_id}.md"
                saved_video = Path(record["video_path"]) if record and record.get("video_path") else None
                if saved_video is None or not saved_video.is_file():
                    state.mark_work(content_id, "PENDING_DOWNLOAD", title=metadata["title"], video_path=str(target), platform="bilibili")
                    try:
                        saved_video = adapter.download(info, target, guard)
                    except StorageLimitExceeded:
                        raise
                    except Exception as exc:
                        if guard.should_pause():
                            raise StorageLimitExceeded(guard.pause_reason()) from exc
                        state.mark_work(content_id, "FAILED", error=access_error(exc), platform="bilibili")
                        raise
                    state.mark_work(content_id, "DOWNLOADED", video_path=str(saved_video), platform="bilibili")

                state.set_meta(f"source:{content_id}", json.dumps(metadata, ensure_ascii=False))
                quality = process_media_task(args, state, guard, saved_video, md_path, content_id, "bilibili", metadata)
                if quality:
                    # 单作品持久化，避免中断后遗失已处理视频的质量指标。
                    state.set_meta(f"quality:{content_id}", json.dumps(quality, ensure_ascii=False))
                processed += 1
                if state.get_work(content_id, platform="bilibili")["status"] == "FAILED":
                    print("媒体处理失败，源视频已保留；停止继续下载以便诊断。")
                    return 1
                guard.assert_can_start()
            state.set_meta("last_entry", index)
        state.set_meta("scan_complete", "1")
        state.set_meta("last_error", "")
        return 0
    finally:
        print(f"本次扫描视频数：{processed}；状态统计：{state.status_counts('bilibili')}")
        size = sum(path.stat().st_size for path in out_dir.rglob("*.md"))
        guard.assert_can_start(extra_bytes=size)
        checkpoint = export_markdown_checkpoint(out_dir, export_dir, label)
        if checkpoint:
            print(f"Markdown 检查点：{checkpoint}")
