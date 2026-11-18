from __future__ import annotations

import argparse
import asyncio
import hashlib
import math
import os
import re
import subprocess
import tempfile
import zipfile
from datetime import date
from pathlib import Path
from typing import Any

from .state import TaskState
from .video import (
    HIGH_COMPRESSION,
    LOW_LOGPROB,
    cleanup_video,
    find_videos,
    process_video,
    title_of,
    write_quality_report,
    repair_docs,
)
from .documents import convert_document, find_documents
from .storage import StorageGuard, StorageLimitExceeded


def _project_path(value: str | None, default: Path) -> Path:
    if not value:
        return default
    path = Path(value).expanduser()
    return path if path.is_absolute() else Path(__file__).resolve().parents[1] / path


def _safe_name(value: str) -> str:
    cleaned = re.sub(r"[^\w.-]+", "_", value.strip(), flags=re.UNICODE)
    return cleaned.strip("._") or "blogger"


def load_cookie_and_settings(config_path: Path) -> tuple[str, dict]:
    settings: dict[str, Any] = {}
    if config_path.is_file():
        try:
            import yaml
        except ImportError as exc:
            raise RuntimeError("读取 Cookie YAML 需要 PyYAML，请先安装 requirements.txt") from exc
        try:
            raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
            settings = raw.get("douyin", raw) if isinstance(raw, dict) else {}
        except Exception as exc:
            raise RuntimeError(f"Cookie 配置文件无法解析：{config_path}") from exc

    cookie = os.environ.get("DOUYIN_COOKIE", "").strip()
    if not cookie:
        cookie = str(settings.get("cookie") or "").strip()
    if not cookie or cookie in {"在此粘贴你的cookie", "YOUR_COOKIE_HERE"}:
        raise RuntimeError(
            "缺少抖音 Cookie。请在运行环境的安全变量中配置 DOUYIN_COOKIE，"
            "或提供被 Git 忽略的 douyin_cookie.yaml。"
        )
    return cookie, settings


def probe_duration(video: Path) -> float | None:
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "error", "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1", str(video),
            ],
            capture_output=True,
            text=True,
            check=True,
            timeout=30,
        )
        duration = float(result.stdout.strip())
        return duration if duration > 0 else None
    except (OSError, subprocess.SubprocessError, ValueError):
        return None


def is_valid_video(video: Path) -> bool:
    return video.is_file() and video.stat().st_size > 1024 and probe_duration(video) is not None


def is_valid_markdown(path: Path) -> bool:
    if not path.is_file() or path.stat().st_size < 20:
        return False
    try:
        content = path.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeError):
        return False
    if "（未识别到内容）" in content:
        return False
    for marker in ("## 口播转录", "## 画面文字"):
        if marker in content:
            body = content.split(marker, 1)[1].strip()
            return bool(body and len(body) >= 2)
    return False


def is_low_confidence(record: dict | None) -> bool:
    if not record or not record.get("quality"):
        return False
    quality = record["quality"]
    return (
        float(quality.get("avg_logprob", 0.0)) < LOW_LOGPROB
        or float(quality.get("max_compression", 0.0)) > HIGH_COMPRESSION
    )


def estimate_temp_bytes(video: Path, ocr: bool, frame_interval: float) -> int:
    size = video.stat().st_size
    duration = probe_duration(video)
    if duration is None:
        return size + 256 * 1024**2
    if ocr:
        frame_count = max(1, math.ceil(duration / max(frame_interval, 0.5)))
        return size + frame_count * 1024**2
    wav_bytes = int(duration * 32000)
    return size + wav_bytes + 32 * 1024**2


def _find_video(user_path: Path, aweme_id: str, expected: Path) -> Path | None:
    if expected.is_file():
        return expected
    matches = sorted(user_path.rglob(f"{aweme_id}_*_video.mp4"))
    return matches[0] if matches else None


async def _download_one(
    handler: Any,
    kwargs: dict,
    item: dict,
    user_path: Path,
    video_path: Path,
    guard: StorageGuard,
) -> None:
    guard.assert_can_start()
    task = asyncio.create_task(
        handler.downloader.create_download_tasks(kwargs, [item], user_path)
    )
    while not task.done():
        try:
            await asyncio.wait_for(
                asyncio.shield(task), timeout=guard.poll_seconds
            )
        except asyncio.TimeoutError:
            if guard.should_pause():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
                if video_path.exists() and not is_valid_video(video_path):
                    video_path.unlink(missing_ok=True)
                raise StorageLimitExceeded(guard.pause_reason())
    await task


def export_markdown_checkpoint(
    source_root: Path, export_dir: Path, blogger: str
) -> Path | None:
    markdown_files = sorted(source_root.rglob("*.md")) if source_root.exists() else []
    if not markdown_files:
        return None
    export_dir.mkdir(parents=True, exist_ok=True)
    final_path = export_dir / f"{_safe_name(blogger)}_markdown_checkpoint.zip"
    temp_path = export_dir / f".{final_path.name}.tmp"
    try:
        with zipfile.ZipFile(
            temp_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6
        ) as archive:
            for path in markdown_files:
                archive.write(path, path.relative_to(source_root).as_posix())
        temp_path.replace(final_path)
        return final_path
    finally:
        temp_path.unlink(missing_ok=True)


def _make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Social2MD：统一的社交内容采集、媒体处理与 Markdown 归档流水线"
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("-u", "--url", help="抖音主页链接（当前唯一已接入的平台采集入口）")
    source.add_argument("--input-dir", type=Path, help="待处理视频目录；使用相同队列、状态和安全规则")
    source.add_argument("--document-dir", type=Path, help="待转换文档目录；源文档始终保留")

    parser.add_argument("-b", "--blogger", default="未分类", help="作者或任务名称，用于输出分目录")
    parser.add_argument("-c", "--config", default="douyin_cookie.yaml", help="Douyin Cookie YAML；DOUYIN_COOKIE 环境变量优先")
    parser.add_argument("--download-dir", help="Douyin 视频缓存目录")
    parser.add_argument("--out-dir", help="Markdown 输出目录")
    parser.add_argument("--state-dir", default="state", help="统一断点状态目录")
    parser.add_argument("--export-dir", default="exports", help="Markdown 检查点 ZIP 目录")
    parser.add_argument("--batch-size", type=int, default=30, help="平台元数据批量获取数量，默认 30；媒体始终逐项处理")
    parser.add_argument("--max-items", type=int, default=0, help="本次最多处理数量；0 表示不限制")
    parser.add_argument("--pause-percent", type=float, default=95.0, help="磁盘暂停阈值")
    parser.add_argument("--resume-percent", type=float, default=90.0, help="磁盘恢复阈值")
    parser.add_argument("--min-free-gib", type=float, default=1.0, help="最低可用空间")
    parser.add_argument("--poll-seconds", type=float, default=2.0, help="下载期间磁盘检查间隔")
    parser.add_argument("--model", default="small", choices=["tiny", "base", "small", "medium", "large-v3"])
    parser.add_argument("--language", default="zh")
    parser.add_argument("--ocr", action="store_true", help="使用视频帧 OCR 替代语音转录")
    parser.add_argument("--frame-interval", type=float, default=3.0)
    parser.add_argument("--save-frames", action="store_true", help="同时导出关键帧")
    parser.add_argument("--max-frames", type=int, default=12)
    parser.add_argument("--keep-source", action="store_true", help="视频处理成功后仍保留源视频")
    parser.add_argument("--retry-review", action="store_true", help="重新处理 REVIEW_REQUIRED 任务")
    parser.add_argument("--force", action="store_true", help="忽略已完成状态并重新生成 Markdown")
    parser.add_argument("--refresh", action="store_true", help="Douyin 从最新作品重新扫描，已完成作品仍按平台和作品 ID 去重")
    parser.add_argument("--dry-run", action="store_true", help="只检查输入、磁盘和参数，不下载或转换")
    return parser


async def run_cloud(args: argparse.Namespace) -> int:
    project_root = Path(__file__).resolve().parents[1]
    download_dir = _project_path(args.download_dir, project_root / "videos" / args.blogger)
    output_base = project_root / "output" / args.blogger
    out_dir = _project_path(args.out_dir, output_base / date.today().isoformat())
    state_dir = _project_path(args.state_dir, project_root / "state")
    export_dir = _project_path(args.export_dir, project_root / "exports")
    model_cache = Path(os.environ.get("HF_HOME", Path.home() / ".cache" / "huggingface"))
    temp_dir = Path(tempfile.gettempdir())

    download_dir.mkdir(parents=True, exist_ok=True)
    out_dir.mkdir(parents=True, exist_ok=True)
    state_dir.mkdir(parents=True, exist_ok=True)

    guard = StorageGuard(
        [project_root, download_dir, out_dir, state_dir, export_dir, temp_dir, model_cache],
        pause_percent=args.pause_percent,
        resume_percent=args.resume_percent,
        min_free_bytes=int(args.min_free_gib * 1024**3),
        poll_seconds=args.poll_seconds,
    )

    state_key = hashlib.sha256(args.url.encode("utf-8")).hexdigest()[:20]
    with TaskState(state_dir / f"{state_key}.sqlite3") as state:
        was_paused = state.get_meta("paused", "0") == "1"
        if args.refresh:
            state.set_cursor(0)
            state.set_meta("exhausted", "0")
            state.set_meta("paused", "0")
            was_paused = False

        if state.get_meta("exhausted", "0") == "1" and not args.refresh:
            print("该主页已完成扫描。如需检查新作品，请添加 --refresh。")
            return 0

        if args.dry_run:
            print("DRY RUN：不会读取 Cookie，也不会访问抖音。")
            print(StorageGuard.format_snapshot(guard.snapshot()))
            print(f"每批作品数：{args.batch_size}；暂停阈值：{args.pause_percent:.1f}%；恢复阈值：{args.resume_percent:.1f}%")
            return 0

        try:
            guard.assert_can_start(was_paused=was_paused)
        except StorageLimitExceeded as exc:
            state.set_meta("paused", "1")
            print(f"PAUSED_STORAGE: {exc}")
            print(StorageGuard.format_snapshot(guard.snapshot()))
            return 75
        state.set_meta("paused", "0")

        try:
            cookie, settings = load_cookie_and_settings(
                _project_path(args.config, project_root / "douyin_cookie.yaml")
            )
            from f2.apps.douyin.db import AsyncUserDB
            from f2.apps.douyin.handler import DouyinHandler
            from f2.apps.douyin.utils import SecUserIdFetcher, format_file_name
        except Exception as exc:
            print(f"环境或 Cookie 初始化失败：{exc}")
            return 2

        kwargs = {
            "headers": {
                "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
                "Referer": "https://www.douyin.com/",
            },
            "proxies": {"http://": None, "https://": None},
            "cookie": cookie,
            "url": args.url,
            "path": str(download_dir),
            "mode": "post",
            "naming": "{aweme_id}_{desc}",
            "desc": True,
            "cover": False,
            "music": False,
            "folderize": False,
            "interval": "all",
            "timeout": int(settings.get("timeout", 10)),
            "max_retries": int(settings.get("max_retries", 3)),
            "max_connections": 2,
            "max_tasks": 1,
            "page_counts": args.batch_size,
            "max_counts": args.batch_size,
        }

        try:
            sec_user_id = await SecUserIdFetcher.get_sec_user_id(
                args.url, proxies=kwargs["proxies"]
            )
            handler = DouyinHandler(kwargs)
            async with AsyncUserDB("douyin_users.db") as user_db:
                user_path = await handler.get_or_add_user_data(
                    kwargs=kwargs, sec_user_id=sec_user_id, db=user_db
                )
            if user_path is None:
                raise RuntimeError("F2 未能创建用户目录，可能是账号不可用或被识别为异常用户")
            user_path = Path(user_path)
            state.set_meta("sec_user_id", sec_user_id)
        except Exception as exc:
            print(f"F2 初始化失败：{exc}")
            return 2

        cursor = state.get_cursor(0)
        processed_this_run = 0
        quality_records: list[dict] = []
        exhausted = False

        try:
            while not exhausted:
                batch_start_cursor = cursor
                batch_progress = 0
                stop_for_limit = False

                async for page in handler.fetch_user_post_videos(
                    sec_user_id, 0, cursor, args.batch_size, args.batch_size
                ):
                    items = page._to_list()
                    page_cursor = getattr(page, "max_cursor", None)
                    has_more = bool(getattr(page, "has_more", False))

                    for item in items:
                        if args.max_items and processed_this_run >= args.max_items:
                            stop_for_limit = True
                            break

                        aweme_id = str(item.get("aweme_id") or "")
                        if not aweme_id:
                            continue

                        record = state.get_work(aweme_id)
                        status = record.get("status") if record else None

                        if status == "COMPLETED" and not args.force:
                            saved_md = Path(record["md_path"]) if record.get("md_path") else None
                            saved_video = Path(record["video_path"]) if record.get("video_path") else None
                            if saved_md and is_valid_markdown(saved_md):
                                if saved_video and saved_video.exists() and not args.keep_source:
                                    cleanup_video(saved_video, title_of(saved_video))
                                processed_this_run += 1
                                batch_progress += 1
                                continue
                            state.mark_work(aweme_id, "FAILED", error="已完成记录的 Markdown 不存在或校验失败")

                        if status == "SKIPPED" or (status == "REVIEW_REQUIRED" and not args.retry_review and not args.force):
                            processed_this_run += 1
                            batch_progress += 1
                            continue

                        if not item.get("video_play_addr"):
                            state.mark_work(
                                aweme_id,
                                "SKIPPED",
                                title=str(item.get("desc") or aweme_id),
                                error="该作品没有可下载的视频流",
                            )
                            processed_this_run += 1
                            batch_progress += 1
                            continue

                        base_name = format_file_name(kwargs["naming"], item)
                        expected_video = user_path / f"{base_name}_video.mp4"
                        video_path = _find_video(user_path, aweme_id, expected_video)

                        if video_path is not None and not is_valid_video(video_path):
                            video_path.unlink(missing_ok=True)
                            video_path = None

                        if video_path is None:
                            try:
                                await _download_one(
                                    handler, kwargs, item, user_path, expected_video, guard
                                )
                            except StorageLimitExceeded as exc:
                                state.mark_work(
                                    aweme_id, "PENDING_DOWNLOAD", title=base_name,
                                    video_path=str(expected_video), error=str(exc)
                                )
                                state.set_meta("paused", "1")
                                print(f"PAUSED_STORAGE: {exc}")
                                return 75
                            except Exception as exc:
                                if expected_video.exists() and not is_valid_video(expected_video):
                                    expected_video.unlink(missing_ok=True)
                                state.mark_work(
                                    aweme_id, "FAILED", title=base_name,
                                    video_path=str(expected_video), error=f"下载失败：{exc}"
                                )
                                processed_this_run += 1
                                batch_progress += 1
                                continue
                            video_path = _find_video(user_path, aweme_id, expected_video)

                        if video_path is None or not is_valid_video(video_path):
                            state.mark_work(
                                aweme_id, "FAILED", title=base_name,
                                video_path=str(expected_video),
                                error="下载后未找到有效视频文件或 ffprobe 校验失败",
                            )
                            processed_this_run += 1
                            batch_progress += 1
                            continue

                        state.mark_work(
                            aweme_id, "DOWNLOADED",
                            title=title_of(video_path), video_path=str(video_path)
                        )

                        try:
                            guard.assert_can_start(
                                extra_bytes=estimate_temp_bytes(
                                    video_path, args.ocr, args.frame_interval
                                )
                            )
                        except StorageLimitExceeded as exc:
                            state.set_meta("paused", "1")
                            print(f"PAUSED_STORAGE: 已下载视频保留，等待空间恢复：{exc}")
                            return 75

                        title = title_of(video_path)
                        md_path = out_dir / f"{title}.md"
                        if md_path.exists() and is_valid_markdown(md_path) and not args.force and not (status == "REVIEW_REQUIRED" and args.retry_review):
                            state.mark_work(
                                aweme_id, "REVIEW_REQUIRED", title=title,
                                video_path=str(video_path), md_path=str(md_path),
                                error="发现已有有效 Markdown；为避免误删原视频，保留视频供人工核验",
                            )
                            processed_this_run += 1
                            batch_progress += 1
                            continue

                        state.mark_work(
                            aweme_id, "PROCESSING", title=title,
                            video_path=str(video_path), md_path=str(md_path)
                        )
                        result, quality_record = process_video(
                            video_path,
                            out_dir,
                            set(),
                            args.model,
                            args.language,
                            delete_video=False,
                            force=md_path.exists(),
                            ocr=args.ocr,
                            frame_interval=args.frame_interval,
                            save_frames=args.save_frames,
                            max_frames=args.max_frames,
                            require_transcript=True,
                        )

                        if result != "ok" or not is_valid_markdown(md_path):
                            state.mark_work(
                                aweme_id, "FAILED", title=title,
                                video_path=str(video_path), md_path=str(md_path),
                                error="转录失败或 Markdown 校验未通过；原视频已保留",
                            )
                            processed_this_run += 1
                            batch_progress += 1
                            continue

                        if quality_record:
                            quality_records.append(quality_record)

                        if is_low_confidence(quality_record):
                            state.mark_work(
                                aweme_id, "REVIEW_REQUIRED", title=title,
                                video_path=str(video_path), md_path=str(md_path),
                                error="转录质量指标低于阈值；保留原视频供人工复核",
                            )
                            print(f"REVIEW_REQUIRED: {title}")
                        else:
                            state.mark_work(
                                aweme_id, "COMPLETED", title=title,
                                video_path=str(video_path), md_path=str(md_path)
                            )
                            if not args.keep_source:
                                cleanup_video(video_path, title)

                        processed_this_run += 1
                        batch_progress += 1

                        if guard.should_pause():
                            state.set_meta("paused", "1")
                            print(f"PAUSED_STORAGE: {guard.pause_reason()}")
                            return 75

                    if stop_for_limit:
                        break

                    if has_more:
                        if page_cursor is None or str(page_cursor) == str(cursor):
                            raise RuntimeError("F2 返回的分页游标未前进，已停止以避免重复请求")
                        cursor = int(page_cursor)
                        state.set_cursor(cursor)
                    else:
                        exhausted = True
                        state.set_meta("exhausted", "1")
                    if exhausted:
                        break

                if quality_records:
                    write_quality_report(out_dir, quality_records)
                    quality_records.clear()

                try:
                    estimate_zip = (
                        sum(p.stat().st_size for p in output_base.rglob("*.md"))
                        if output_base.exists() else 0
                    )
                    guard.assert_can_start(extra_bytes=estimate_zip)
                    checkpoint = export_markdown_checkpoint(
                        output_base, export_dir, args.blogger
                    )
                    if checkpoint:
                        print(f"Markdown 检查点：{checkpoint}")
                except StorageLimitExceeded as exc:
                    if guard.should_pause():
                        state.set_meta("paused", "1")
                        print(f"PAUSED_STORAGE: ZIP 导出前空间不足：{exc}")
                        return 75
                    print(f"跳过本批 ZIP 导出：{exc}")

                if stop_for_limit or exhausted:
                    break
                if cursor == batch_start_cursor or batch_progress == 0:
                    raise RuntimeError("本批没有取得可恢复的分页进度，已停止以避免死循环")

            state.set_meta("paused", "0")
            print("任务处理结束。")
            print(f"本次扫描作品数：{processed_this_run}")
            print(f"状态统计：{state.status_counts()}")
            print(StorageGuard.format_snapshot(guard.snapshot()))
            return 0
        except StorageLimitExceeded as exc:
            state.set_meta("paused", "1")
            print(f"PAUSED_STORAGE: {exc}")
            print(StorageGuard.format_snapshot(guard.snapshot()))
            return 75
        except KeyboardInterrupt:
            state.set_meta("paused", "1")
            print("收到中断信号；分页游标和作品状态已保存。")
            return 130
        except Exception as exc:
            print(f"任务处理异常：{exc}")
            return 1


def _state_paths(args: argparse.Namespace, project_root: Path) -> tuple[Path, Path]:
    state_dir = _project_path(args.state_dir, project_root / "state")
    export_dir = _project_path(args.export_dir, project_root / "exports")
    state_dir.mkdir(parents=True, exist_ok=True)
    export_dir.mkdir(parents=True, exist_ok=True)
    return state_dir, export_dir


def run_video_directory(args: argparse.Namespace) -> int:
    project_root = Path(__file__).resolve().parents[1]
    source_dir = args.input_dir.expanduser().resolve()
    if not source_dir.is_dir():
        print(f"输入视频目录不存在：{source_dir}")
        return 2

    label = _safe_name(args.blogger if args.blogger != "未分类" else source_dir.name)
    output_base = project_root / "output" / label
    out_dir = _project_path(args.out_dir, output_base / date.today().isoformat())
    state_dir, export_dir = _state_paths(args, project_root)
    model_cache = Path(os.environ.get("HF_HOME", Path.home() / ".cache" / "huggingface"))
    temp_dir = Path(tempfile.gettempdir())
    out_dir.mkdir(parents=True, exist_ok=True)

    guard = StorageGuard(
        [project_root, source_dir, out_dir, state_dir, export_dir, temp_dir, model_cache],
        pause_percent=args.pause_percent,
        resume_percent=args.resume_percent,
        min_free_bytes=int(args.min_free_gib * 1024**3),
        poll_seconds=args.poll_seconds,
    )
    state_key = hashlib.sha256(str(source_dir).encode("utf-8")).hexdigest()[:20]
    videos = find_videos(source_dir)
    if args.dry_run:
        print("DRY RUN：不会转录、删除源文件或下载模型。")
        print(f"发现视频：{len(videos)}")
        print(StorageGuard.format_snapshot(guard.snapshot()))
        return 0

    processed = 0
    quality_records: list[dict] = []
    with TaskState(state_dir / f"files_{state_key}.sqlite3") as state:
        was_paused = state.get_meta("paused", "0") == "1"
        try:
            guard.assert_can_start(was_paused=was_paused)
        except StorageLimitExceeded as exc:
            state.set_meta("paused", "1")
            print(f"PAUSED_STORAGE: {exc}")
            return 75
        state.set_meta("paused", "0")

        for video in videos:
            if args.max_items and processed >= args.max_items:
                break
            content_id = hashlib.sha256(str(video.resolve()).encode("utf-8")).hexdigest()
            record = state.get_work(content_id, platform="file")
            status = record.get("status") if record else None
            saved_md = Path(record["md_path"]) if record and record.get("md_path") else None

            if status == "COMPLETED" and saved_md and is_valid_markdown(saved_md) and not args.force:
                if not args.keep_source:
                    video.unlink(missing_ok=True)
                processed += 1
                continue
            if status == "REVIEW_REQUIRED" and not args.retry_review:
                processed += 1
                continue

            if not is_valid_video(video):
                state.mark_work(
                    content_id, "FAILED", title=title_of(video), video_path=str(video),
                    error="源视频无效或 ffprobe 无法读取时长", platform="file",
                )
                processed += 1
                continue

            try:
                guard.assert_can_start(
                    extra_bytes=estimate_temp_bytes(video, args.ocr, args.frame_interval)
                )
            except StorageLimitExceeded as exc:
                state.mark_work(
                    content_id, "PENDING", title=title_of(video), video_path=str(video),
                    error=str(exc), platform="file",
                )
                state.set_meta("paused", "1")
                print(f"PAUSED_STORAGE: {exc}")
                return 75

            title = title_of(video)
            relative_parent = video.relative_to(source_dir).parent
            item_out_dir = out_dir / relative_parent
            md_path = item_out_dir / f"{title}_{content_id[:8]}.md"
            item_out_dir.mkdir(parents=True, exist_ok=True)

            if (
                md_path.exists() and is_valid_markdown(md_path) and not args.force
                and not (status == "REVIEW_REQUIRED" and args.retry_review)
            ):
                state.mark_work(
                    content_id, "REVIEW_REQUIRED", title=title, video_path=str(video),
                    md_path=str(md_path),
                    error="发现已有有效 Markdown；为避免覆盖或误删源视频，保留源视频供人工核验",
                    platform="file",
                )
                processed += 1
                continue
            state.mark_work(
                content_id, "PROCESSING", title=title, video_path=str(video),
                md_path=str(md_path), platform="file",
            )
            result, quality_record = process_video(
                video, item_out_dir, set(), args.model, args.language,
                delete_video=False, force=True, ocr=args.ocr,
                frame_interval=args.frame_interval, save_frames=args.save_frames,
                max_frames=args.max_frames, require_transcript=True,
                output_path=md_path,
            )
            if result != "ok" or not is_valid_markdown(md_path):
                state.mark_work(
                    content_id, "FAILED", title=title, video_path=str(video),
                    md_path=str(md_path), error="媒体处理失败或 Markdown 校验未通过；源视频已保留",
                    platform="file",
                )
            elif is_low_confidence(quality_record):
                state.mark_work(
                    content_id, "REVIEW_REQUIRED", title=title, video_path=str(video),
                    md_path=str(md_path), error="转录质量触发复核阈值；源视频已保留",
                    platform="file",
                )
                if quality_record:
                    quality_records.append(quality_record)
            else:
                state.mark_work(
                    content_id, "COMPLETED", title=title, video_path=str(video),
                    md_path=str(md_path), platform="file",
                )
                if quality_record:
                    quality_records.append(quality_record)
                if not args.keep_source:
                    video.unlink(missing_ok=True)

            processed += 1
            if guard.should_pause():
                state.set_meta("paused", "1")
                print(f"PAUSED_STORAGE: {guard.pause_reason()}")
                return 75

        if quality_records:
            write_quality_report(out_dir, quality_records)
        try:
            guard.assert_can_start()
            checkpoint = export_markdown_checkpoint(output_base, export_dir, label)
            if checkpoint:
                print(f"Markdown 检查点：{checkpoint}")
        except StorageLimitExceeded as exc:
            print(f"跳过 ZIP 导出：{exc}")
        state.set_meta("paused", "0")
        print(f"视频任务处理数：{processed}")
        print(f"状态统计：{state.status_counts('file')}")
        print(StorageGuard.format_snapshot(guard.snapshot()))
    return 0


def run_document_directory(args: argparse.Namespace) -> int:
    project_root = Path(__file__).resolve().parents[1]
    source_dir = args.document_dir.expanduser().resolve()
    if not source_dir.is_dir():
        print(f"输入文档目录不存在：{source_dir}")
        return 2

    label = _safe_name(args.blogger if args.blogger != "未分类" else source_dir.name)
    output_base = project_root / "output" / "documents" / label
    out_dir = _project_path(args.out_dir, output_base / date.today().isoformat())
    state_dir, export_dir = _state_paths(args, project_root)
    temp_dir = Path(tempfile.gettempdir())
    out_dir.mkdir(parents=True, exist_ok=True)
    guard = StorageGuard(
        [project_root, source_dir, out_dir, state_dir, export_dir, temp_dir],
        pause_percent=args.pause_percent,
        resume_percent=args.resume_percent,
        min_free_bytes=int(args.min_free_gib * 1024**3),
        poll_seconds=args.poll_seconds,
    )
    state_key = hashlib.sha256(str(source_dir).encode("utf-8")).hexdigest()[:20]
    documents = find_documents(source_dir)
    try:
        import markitdown  # noqa: F401
    except ImportError:
        print("文档转换需要可选依赖，请先安装 requirements-optional.txt。")
        return 2
    if args.dry_run:
        print("DRY RUN：不会转换或修改源文档。")
        print(f"发现文档：{len(documents)}")
        print(StorageGuard.format_snapshot(guard.snapshot()))
        return 0

    processed = 0
    with TaskState(state_dir / f"documents_{state_key}.sqlite3") as state:
        was_paused = state.get_meta("paused", "0") == "1"
        try:
            guard.assert_can_start(was_paused=was_paused)
        except StorageLimitExceeded as exc:
            state.set_meta("paused", "1")
            print(f"PAUSED_STORAGE: {exc}")
            return 75
        state.set_meta("paused", "0")

        for source in documents:
            if args.max_items and processed >= args.max_items:
                break
            content_id = hashlib.sha256(str(source.resolve()).encode("utf-8")).hexdigest()
            relative = source.relative_to(source_dir)
            destination = out_dir / relative.with_suffix(".md")
            record = state.get_work(content_id, platform="document")
            if (
                record and record.get("status") == "COMPLETED"
                and destination.is_file() and destination.stat().st_size > 0
                and not args.force
            ):
                processed += 1
                continue

            try:
                guard.assert_can_start(extra_bytes=source.stat().st_size * 2)
            except StorageLimitExceeded as exc:
                state.mark_work(
                    content_id, "PENDING", title=source.name, md_path=str(destination),
                    error=str(exc), platform="document",
                )
                state.set_meta("paused", "1")
                print(f"PAUSED_STORAGE: {exc}")
                return 75

            state.mark_work(
                content_id, "PROCESSING", title=source.name, md_path=str(destination),
                platform="document",
            )
            try:
                success = convert_document(source, destination)
            except Exception as exc:
                success = False
                error = str(exc)
            else:
                error = "文档转换失败或输出为空"
            if success:
                state.mark_work(
                    content_id, "COMPLETED", title=source.name,
                    md_path=str(destination), platform="document",
                )
            else:
                state.mark_work(
                    content_id, "FAILED", title=source.name, md_path=str(destination),
                    error=error, platform="document",
                )
            processed += 1
            if guard.should_pause():
                state.set_meta("paused", "1")
                print(f"PAUSED_STORAGE: {guard.pause_reason()}")
                return 75

        try:
            guard.assert_can_start()
            checkpoint = export_markdown_checkpoint(output_base, export_dir, label)
            if checkpoint:
                print(f"Markdown 检查点：{checkpoint}")
        except StorageLimitExceeded as exc:
            print(f"跳过 ZIP 导出：{exc}")
        state.set_meta("paused", "0")
        print(f"文档任务处理数：{processed}")
        print(f"状态统计：{state.status_counts('document')}")
    return 0


def main() -> int:
    parser = _make_parser()
    args = parser.parse_args()
    if args.batch_size < 1 or args.batch_size > 50:
        parser.error("--batch-size 必须在 1 到 50 之间")
    if args.max_items < 0:
        parser.error("--max-items 不能为负数")
    if args.frame_interval <= 0:
        parser.error("--frame-interval 必须大于 0")
    if args.min_free_gib < 0 or args.poll_seconds <= 0:
        parser.error("磁盘保护参数无效")
    if args.refresh and not args.url:
        parser.error("--refresh 仅适用于 Douyin 主页采集")
    try:
        if args.url:
            return asyncio.run(run_cloud(args))
        if args.input_dir:
            return run_video_directory(args)
        return run_document_directory(args)
    except KeyboardInterrupt:
        print("收到中断信号；任务状态已保存。")
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
