#!/usr/bin/env python3
"""
Video to Text Extractor — 视频转文字工具
遍历目录下所有视频，提取音频 → 转写文字 → 同名 .txt 保存 → 删除原视频
"""

import argparse
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

VIDEO_EXTS = {
    '.mp4', '.avi', '.mov', '.mkv', '.webm', '.flv', '.wmv',
    '.m4v', '.ts', '.3gp', '.mts', '.m2ts', '.ogv', '.rmvb', '.vob', '.divx'
}

# ── helpers ──────────────────────────────────────────────

def find_videos(root: Path) -> list[Path]:
    videos = []
    for f in root.rglob('*'):
        if f.is_file() and f.suffix.lower() in VIDEO_EXTS:
            videos.append(f)
    return sorted(videos)


def extract_audio(video_path: Path, audio_path: str) -> float:
    """Extract audio to mono 16kHz WAV. Returns duration in seconds."""
    # get duration first
    probe = subprocess.run(
        ['ffprobe', '-v', 'error', '-show_entries', 'format=duration',
         '-of', 'default=noprint_wrappers=1:nokey=1', str(video_path)],
        capture_output=True, text=True
    )
    try:
        duration = float(probe.stdout.strip())
    except ValueError:
        duration = 0

    cmd = [
        'ffmpeg', '-y', '-i', str(video_path),
        '-vn', '-acodec', 'pcm_s16le', '-ar', '16000', '-ac', '1',
        '-loglevel', 'error', audio_path
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg 失败: {result.stderr.strip()}")
    return duration


def transcribe(audio_path: str, model_size: str, language: str | None) -> str:
    from faster_whisper import WhisperModel

    device = 'cpu'
    compute = 'int8'  # int8 for CPU; float16 for GPU
    model = WhisperModel(model_size, device=device, compute_type=compute)

    segs, info = model.transcribe(audio_path, language=language, beam_size=5)
    lines = []
    for seg in segs:
        text = seg.text.strip()
        if text:
            lines.append(text)

    full_text = '\n'.join(lines)
    detected_lang = info.language
    return full_text, detected_lang


# ── main logic ───────────────────────────────────────────

def process_video(video_path: Path, model: str, language: str | None,
                  dry_run: bool, force: bool, keep_audio: bool) -> bool:
    """Returns True on success."""
    txt_path = video_path.with_suffix('.txt')

    if txt_path.exists() and not force:
        print(f'  ⏭ 跳过 — {txt_path.name} 已存在')
        return True

    if dry_run:
        print(f'  🔍 [预览] {video_path.name} → {txt_path.name}')
        return True

    tmp_audio = None
    try:
        # 1. extract audio
        print(f'  🎵 提取音频 ({video_path.stat().st_size / 1024 / 1024:.1f} MB) ...')
        tmp_fd, tmp_audio = tempfile.mkstemp(suffix='.wav')
        os.close(tmp_fd)
        duration = extract_audio(video_path, tmp_audio)
        print(f'     时长: {int(duration // 60)}分{int(duration % 60)}秒')

        # 2. transcribe
        print(f'  📝 转写中 (模型: {model}) ...')
        t0 = time.time()
        text, detected_lang = transcribe(tmp_audio, model, language)
        elapsed = time.time() - t0
        print(f'     语言: {detected_lang} | 耗时: {elapsed:.1f}s | 字数: {len(text)}')

        # 3. save
        txt_path.write_text(text, encoding='utf-8')
        print(f'  ✅ 已保存: {txt_path.name}')

        # 4. delete video
        video_path.unlink()
        print(f'  🗑 已删除: {video_path.name}')

        return True

    except Exception as e:
        print(f'  ❌ 失败: {e}')
        return False

    finally:
        if tmp_audio and Path(tmp_audio).exists():
            Path(tmp_audio).unlink()


def main():
    parser = argparse.ArgumentParser(
        description='视频转文字 — 提取音频转文字，同名 .txt 保存后删除原视频',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
示例:
  python video2txt.py Z:\\视频                  # 处理整个目录
  python video2txt.py Z:\\视频 --dry-run        # 预览，不实际处理
  python video2txt.py Z:\\视频 --model small    # 用 small 模型（中文更好）
  python video2txt.py Z:\\视频 --language zh    # 指定中文
  python video2txt.py Z:\\视频 --force          # 覆盖已有 .txt
        '''
    )
    parser.add_argument('directory', help='目标目录')
    parser.add_argument('--model', default='base',
                        choices=['tiny', 'base', 'small', 'medium', 'large-v3', 'turbo'],
                        help='Whisper 模型 (默认 base; 中文推荐 small 以上)')
    parser.add_argument('--language', help='语言代码 (zh/en/ja/ko/auto; 默认自动检测)')
    parser.add_argument('--dry-run', action='store_true', help='预览模式，不实际处理')
    parser.add_argument('--force', action='store_true', help='强制覆盖已有 .txt')
    args = parser.parse_args()

    root = Path(args.directory)
    if not root.is_dir():
        print(f'❌ 目录不存在: {args.directory}')
        sys.exit(1)

    videos = find_videos(root)
    if not videos:
        print('📭 未找到视频文件')
        return

    total_size = sum(v.stat().st_size for v in videos) / 1024 / 1024 / 1024
    print(f'📁 {root}')
    print(f'🎬 找到 {len(videos)} 个视频，共 {total_size:.1f} GB')
    if args.dry_run:
        print('🔍 === 预览模式：不会实际修改文件 ===')
    print('=' * 50)

    ok = fail = 0
    for i, vp in enumerate(videos, 1):
        print(f'\n[{i}/{len(videos)}] {vp.name}')
        if process_video(vp, args.model, args.language, args.dry_run, args.force, False):
            ok += 1
        else:
            fail += 1

    print('\n' + '=' * 50)
    print(f'✅ 完成！成功 {ok} 个，失败 {fail} 个')
    if args.dry_run:
        print('🔍 预览模式未实际修改，去掉 --dry-run 正式运行')


if __name__ == '__main__':
    main()