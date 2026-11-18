#!/usr/bin/env python3
"""
Social2MD shared video processor — 视频校验、ASR、OCR、文本规范化与 Markdown 写入
"""

import os
import re
import shutil
import subprocess
import tempfile
import uuid
from pathlib import Path

VIDEO_EXTS = {'.mp4', '.mkv', '.mov', '.webm', '.flv', '.avi', '.m4v', '.ts'}

# 工程根目录（本脚本所在目录），默认输出/临时目录都放这里
PROJECT_ROOT = Path(__file__).resolve().parents[1]

# ── OCR（抽帧 → 去重 → easyocr）─────────────────────────

_OCR_READER = None

def get_ocr_reader():
    global _OCR_READER
    if _OCR_READER is None:
        import easyocr
        print('🧠 加载 easyocr (ch_sim+en, cpu)')
        _OCR_READER = easyocr.Reader(['ch_sim', 'en'], gpu=False, verbose=False)
    return _OCR_READER


def _phash(path: Path):
    import cv2
    img = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
    if img is None:
        return None
    img = cv2.resize(img, (16, 16))
    return img > img.mean()


def ocr_video(video: Path, frame_interval: float) -> str:
    """抽帧（每 frame_interval 秒 1 帧）→ 感知哈希去重 → easyocr 识别，返回拼接文字。"""
    tmp = Path(tempfile.gettempdir())
    tmp_mp4 = tmp / f'ocr_{uuid.uuid4().hex}{video.suffix}'
    frames_dir = tmp / f'frames_{uuid.uuid4().hex}'
    frames_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(video, tmp_mp4)
    try:
        subprocess.run(
            ['ffmpeg', '-y', '-i', str(tmp_mp4),
             '-vf', f'fps=1/{frame_interval}', '-loglevel', 'error',
             str(frames_dir / 'f_%04d.png')],
            check=True,
        )
        frames = sorted(frames_dir.glob('*.png'))
        if not frames:
            return ''
        # 感知哈希去重：相邻帧差异小于阈值则跳过
        keep = []
        last_h = None
        for f in frames:
            h = _phash(f)
            if h is None:
                continue
            if last_h is None or (h != last_h).sum() > 12:
                keep.append(f)
                last_h = h
        reader = get_ocr_reader()
        parts = []
        for f in keep:
            res = reader.readtext(str(f), detail=0, paragraph=True)
            txt = ' '.join(res).strip()
            if txt:
                parts.append(txt)
        return '\n\n'.join(parts).strip()
    finally:
        tmp_mp4.unlink(missing_ok=True)
        shutil.rmtree(frames_dir, ignore_errors=True)


# ── 关键帧导出 ─────────────────────────────────────────────

def _frame_sig(path: Path):
    """缩略彩色图，用于比较相邻帧差异（彩色比灰度更能区分地图标记变化）。"""
    import cv2
    img = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if img is None:
        return None
    return cv2.resize(img, (32, 32)).astype('float32')


def extract_frames(video: Path, dest: Path, max_frames: int = 12, interval: float = 3.0) -> int:
    """按固定间隔抽帧 + 相邻帧差异去重，导出地图/战线图等关键画面为 jpg。"""
    import cv2
    import numpy as np

    dest.mkdir(parents=True, exist_ok=True)
    for old in dest.glob('*.jpg'):
        old.unlink(missing_ok=True)

    frames_dir = Path(tempfile.gettempdir()) / f'frames_{uuid.uuid4().hex}'
    frames_dir.mkdir(parents=True, exist_ok=True)
    try:
        subprocess.run(
            ['ffmpeg', '-y', '-i', str(video), '-vf', f'fps=1/{interval}',
             '-loglevel', 'error', str(frames_dir / 'f_%04d.png')],
            check=True,
        )
        frames = sorted(frames_dir.glob('*.png'))
        if not frames:
            return 0

        keep, last = [], None
        for f in frames:
            sig = _frame_sig(f)
            if sig is None:
                continue
            if last is None or float(np.abs(sig - last).mean()) > 8:
                keep.append(f)
                last = sig
        if not keep:
            keep = frames[:1]
        if len(keep) > max_frames:  # 均匀抽取，避免只截到视频前半段
            step = len(keep) / max_frames
            keep = [keep[int(i * step)] for i in range(max_frames)]

        for i, f in enumerate(keep, 1):
            img = cv2.imread(str(f))
            if img is not None:
                cv2.imwrite(str(dest / f'{i:03d}.jpg'), img, [cv2.IMWRITE_JPEG_QUALITY, 90])

        count = len(list(dest.glob('*.jpg')))
        if count:
            print(f'🖼  关键帧 {count} 张：{dest}')
        return count
    finally:
        shutil.rmtree(frames_dir, ignore_errors=True)


# ── ASR ─────────────────────────────────────────────────

def find_videos(root: Path) -> list[Path]:
    return sorted(p for p in root.rglob('*') if p.is_file() and p.suffix.lower() in VIDEO_EXTS)


def extract_audio(video: Path) -> Path:
    """复制成临时 ASCII 名后抽 16k 单声道 wav，规避 ffmpeg 中文/#/emoji 文件名问题。返回 wav 路径。"""
    tmp = Path(tempfile.gettempdir())
    tmp_mp4 = tmp / f'dy_{uuid.uuid4().hex}{video.suffix}'
    wav = tmp / f'dy_{uuid.uuid4().hex}.wav'
    shutil.copy2(video, tmp_mp4)
    try:
        subprocess.run(
            ['ffmpeg', '-y', '-i', str(tmp_mp4), '-vn',
             '-acodec', 'pcm_s16le', '-ar', '16000', '-ac', '1',
             '-loglevel', 'error', str(wav)],
            check=True,
        )
    finally:
        tmp_mp4.unlink(missing_ok=True)
    return wav


_MODEL = None

def get_model(size: str):
    global _MODEL
    if _MODEL is None:
        from faster_whisper import WhisperModel
        print(f'🧠 加载 faster-whisper 模型：{size} (cpu/int8)')
        _MODEL = WhisperModel(size, device='cpu', compute_type='int8', cpu_threads=8)
    return _MODEL


# ── 文本整理：繁转简 + 标点 + 按停顿分段 ───────────────────

_CC = None
_PUNCT = None
PUNCT_MODEL = (PROJECT_ROOT / 'models' /
               'sherpa-onnx-punct-ct-transformer-zh-en-vocab272727-2024-04-12' /
               'model.onnx')
PARA_GAP = float(os.environ.get('DY_PARA_GAP', '1.0'))     # 停顿超过该秒数则换段
PARA_CHARS = int(os.environ.get('DY_PARA_CHARS', '110'))   # 单段最长字数


def to_simplified(text: str) -> str:
    """繁体转简体（OpenCC t2s）。"""
    global _CC
    if _CC is None:
        from opencc import OpenCC
        _CC = OpenCC('t2s')
    return _CC.convert(text)


def get_punct_model():
    """加载标点恢复模型；不可用时返回 None，退回按停顿补句号。"""
    global _PUNCT
    if _PUNCT is None:
        try:
            import sherpa_onnx
            if not PUNCT_MODEL.exists():
                print(f'⚠  未找到标点模型：{PUNCT_MODEL}，将只按停顿补句号')
                _PUNCT = False
            else:
                print('🧠 加载中文标点模型（sherpa-onnx ct-transformer）')
                cfg = sherpa_onnx.OfflinePunctuationConfig(
                    model=sherpa_onnx.OfflinePunctuationModelConfig(
                        ct_transformer=str(PUNCT_MODEL), num_threads=2,
                        debug=False, provider='cpu'))
                _PUNCT = sherpa_onnx.OfflinePunctuation(cfg)
        except Exception as e:
            print(f'⚠  标点模型加载失败：{e}，将只按停顿补句号')
            _PUNCT = False
    return _PUNCT or None


def ensure_sentence_end(text: str) -> str:
    text = text.strip()
    if text and text[-1] not in '。！？!?…':
        # 结尾是逗号/分号/冒号时直接替换为句号，避免出现「，。」这样的叠标点
        if text[-1] in '，；：,;:':
            text = text[:-1]
        text += '。'
    return text


def _pick_punct(run: str) -> str:
    for p in '？！':
        if p in run:
            return p
    for p in '。；：':
        if p in run:
            return p
    return '，'


def normalize_punct(text: str) -> str:
    """统一半角标点为全角，并合并重复标点（whisper 有时输出英文标点）。"""
    text = re.sub(r'(?<!\d)\.(?!\d)', '。', text)
    for a, c in {',': '，', '?': '？', '!': '！', ':': '：', ';': '；'}.items():
        text = text.replace(a, c)
    text = re.sub(r'\s+([，。！？；：])', r'\1', text)
    text = re.sub(r'[，。！？；：]{2,}', lambda m: _pick_punct(m.group(0)), text)
    return text


def format_transcript(segments: list[tuple[float, float, str]]) -> str:
    """逐段补标点，并按语音停顿/长度分成自然段。"""
    punct = get_punct_model()
    paras, cur, cur_len, prev_end = [], [], 0, None
    for start, end, raw in segments:
        text = normalize_punct(to_simplified(raw).strip())
        if not text:
            continue
        if punct and not re.search(r'[，。！？；：]', text):
            try:
                text = punct.add_punctuation(text)
            except Exception:
                pass
        text = ensure_sentence_end(text)

        gap = start - prev_end if prev_end is not None else None
        if cur and (cur_len >= PARA_CHARS or (gap is not None and gap >= PARA_GAP)):
            paras.append(''.join(cur))
            cur, cur_len = [], 0
        cur.append(text)
        cur_len += len(text)
        prev_end = end
    if cur:
        paras.append(''.join(cur))
    return '\n\n'.join(paras)


def transcribe(wav: Path, model_size: str, language: str) -> tuple[list[tuple[float, float, str]], dict]:
    """返回 ([(start, end, text), ...], 质量指标)。时间戳用于判断停顿，指标用于筛可疑转录。"""
    model = get_model(model_size)
    segs, _ = model.transcribe(
        str(wav), language=language,
        beam_size=int(os.environ.get('DY_BEAM', '5')),
        vad_filter=True,
        initial_prompt='以下是普通话口播，请输出简体中文，并带上逗号、句号等标点符号。',
    )

    segments = []
    total_dur = weighted = 0.0
    quality = {'avg_logprob': 0.0, 'min_logprob': 0.0,
               'max_compression': 0.0, 'max_no_speech': 0.0, 'worst': None}
    for s in segs:
        if not s.text.strip():
            continue
        segments.append((s.start, s.end, s.text))
        dur = max(s.end - s.start, 0.05)
        weighted += s.avg_logprob * dur
        total_dur += dur
        quality['max_compression'] = max(quality['max_compression'], s.compression_ratio)
        quality['max_no_speech'] = max(quality['max_no_speech'], s.no_speech_prob)
        if quality['worst'] is None or s.avg_logprob < quality['min_logprob']:
            quality['min_logprob'] = s.avg_logprob
            quality['worst'] = (s.start, s.text.strip()[:40])
    if total_dur:
        quality['avg_logprob'] = weighted / total_dur
    return segments, quality


# ── 每个视频：转录 → 写 md → 删视频 ──────────────────────

def read_desc(video: Path) -> str:
    """f2 会为每个视频存一个同名 *_desc.txt 文案。视频名形如 <标题>_video.mp4，文案为 <标题>_desc.txt。"""
    stem = video.stem
    if stem.endswith('_video'):
        base = stem[:-len('_video')]
    else:
        base = stem
    desc_file = video.with_name(base + '_desc.txt')
    if desc_file.exists():
        try:
            return desc_file.read_text(encoding='utf-8').strip()
        except Exception:
            return ''
    return ''


def title_of(video: Path) -> str:
    stem = video.stem
    return stem[:-len('_video')] if stem.endswith('_video') else stem


def cleanup_video(video: Path, title: str) -> None:
    """删除视频及 f2 的同名附属文件（desc/封面等）。"""
    video.unlink(missing_ok=True)
    for sib in video.parent.glob(glob_escape(title) + '*'):
        if sib.suffix.lower() in {'.txt', '.jpg', '.png', '.mp3', '.webp'}:
            sib.unlink(missing_ok=True)
    print(f'🗑  已删视频：{video.name}')


def process_video(video: Path, out_dir: Path, existing: set, model_size: str, language: str,
                  delete_video: bool, force: bool,
                  ocr: bool = False, frame_interval: float = 3.0,
                  save_frames: bool = False, max_frames: int = 12,
                  require_transcript: bool = False,
                  output_path: Path | None = None) -> tuple[str, dict | None]:
    """返回 (状态, 质量记录)：状态为 ok / skip / fail；质量记录仅在成功语音转录时存在。"""
    title = title_of(video)
    md_path = output_path or (out_dir / (title + '.md'))

    if not force and title in existing:
        print(f'⏭  跳过（已存在）：{title}.md')
        cleanup_video(video, title)  # 重复下载的视频不再保留
        return 'skip', None

    wav = None
    quality = None
    try:
        desc = read_desc(video)
        if ocr:
            text = to_simplified(ocr_video(video, frame_interval))
            section = '## 画面文字\n'
        else:
            wav = extract_audio(video)
            segments, quality = transcribe(wav, model_size, language)
            text = format_transcript(segments)
            section = '## 口播转录\n'

        parts = [f'# {title}\n']
        if desc:
            parts.append('## 原文案\n\n' + desc + '\n')
        if require_transcript and not text.strip():
            raise RuntimeError('未识别到有效文字，保留原视频等待复核')

        parts.append(section + '\n' + (text if text else '（未识别到内容）') + '\n')
        md_path.parent.mkdir(parents=True, exist_ok=True)
        content = '\n'.join(parts)
        temp_md = None
        try:
            with tempfile.NamedTemporaryFile(
                mode='w',
                encoding='utf-8',
                dir=md_path.parent,
                prefix=f'.{md_path.name}.',
                suffix='.tmp',
                delete=False,
            ) as handle:
                temp_md = Path(handle.name)
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_md, md_path)
        finally:
            if temp_md is not None:
                temp_md.unlink(missing_ok=True)

        existing.add(title)
        print(f'✅ {md_path.name}  ({len(text)} 字)')

        if save_frames:
            extract_frames(video, md_path.parent / 'images' / title, max_frames, frame_interval)

        if delete_video:
            cleanup_video(video, title)
        return 'ok', ({'title': title, 'quality': quality} if quality else None)

    except Exception as e:
        print(f'❌ 失败：{video.name} — {e}')
        return 'fail', None
    finally:
        if wav is not None:
            wav.unlink(missing_ok=True)


def glob_escape(s: str) -> str:
    # 转义 glob 特殊字符，避免标题里的 [ ] 等误伤
    for ch in '[]?*':
        s = s.replace(ch, '[' + ch + ']')
    return s


# ── 修复已有 md（繁转简 + 标点 + 分段）────────────────────

def split_sentences(text: str) -> list[str]:
    return [p.strip() for p in re.split(r'(?<=[。！？!?])', text) if p.strip()]


def group_paragraphs(sentences: list[str]) -> str:
    paras, cur, cur_len = [], [], 0
    for sent in sentences:
        cur.append(sent)
        cur_len += len(sent)
        if cur_len >= PARA_CHARS:
            paras.append(''.join(cur))
            cur, cur_len = [], 0
    if cur:
        paras.append(''.join(cur))
    return '\n\n'.join(paras)


def repair_docs(root: Path) -> tuple[int, int]:
    """就地修复已有 md 的「口播转录」：繁转简、补标点、分段。返回 (已修改, 跳过)。"""
    if not root.exists():
        print(f'❌ 目录不存在：{root}')
        return 0, 0
    punct = get_punct_model()
    modified = skipped = 0
    for md in sorted(root.rglob('*.md')):
        raw = md.read_text(encoding='utf-8')
        marker = '## 口播转录\n'
        if marker not in raw:
            skipped += 1
            continue
        head, body = raw.split(marker, 1)
        body = normalize_punct(to_simplified(body.strip()))
        if not body or body == '（未识别到内容）':
            skipped += 1
            continue

        sentences = []
        for chunk in re.split(r'\n+', body):
            chunk = chunk.strip()
            if not chunk:
                continue
            # 原文没标点才过标点模型，避免给已有标点的文本乱加
            if punct and not re.search(r'[，。！？；：]', chunk):
                try:
                    chunk = punct.add_punctuation(chunk)
                except Exception:
                    pass
            sentences.extend(split_sentences(ensure_sentence_end(chunk)))

        new_body = group_paragraphs(sentences)
        md.write_text(head + marker + '\n' + new_body + '\n', encoding='utf-8')
        modified += 1

    print(f'✅ 修复完成：修改 {modified} 个，跳过 {skipped} 个（{root}）')
    return modified, skipped


# ── 可疑转录筛查 ─────────────────────────────────────────

LOW_LOGPROB = float(os.environ.get('DY_LOW_LOGPROB', '-0.8'))
HIGH_COMPRESSION = float(os.environ.get('DY_HIGH_COMPRESSION', '2.4'))


def write_quality_report(out_dir: Path, records: list[dict]) -> None:
    """根据 Whisper 置信度生成本批低置信度清单。"""
    suspects = [r for r in records
                if r['quality']['avg_logprob'] < LOW_LOGPROB
                or r['quality']['max_compression'] > HIGH_COMPRESSION]
    suspects.sort(key=lambda r: r['quality']['avg_logprob'])

    lines = [
        '# 低置信度转录清单',
        '',
        f'> 本批语音转录 {len(records)} 篇，低置信 {len(suspects)} 篇。',
        f'> 判定标准：平均 avg_logprob < {LOW_LOGPROB} 或 compression_ratio > {HIGH_COMPRESSION}。',
        '> 分数越低越可能有错字，建议用 medium 重跑或人工核对。',
        '',
    ]
    if suspects:
        lines += ['| 标题 | avg_logprob | 压缩比 | 最差片段 |', '| --- | --- | --- | --- |']
        for r in suspects:
            q = r['quality']
            worst = q.get('worst')
            w = f'{worst[0]:.1f}s {worst[1]}' if worst else ''
            lines.append(f"| {r['title']} | {q['avg_logprob']:.2f} | {q['max_compression']:.2f} | {w} |")
    else:
        lines.append('本批没有触发低置信阈值。')
    p = out_dir / '_低置信度清单.md'
    p.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print(f'📋 低置信度清单：{p.name}（{len(suspects)}/{len(records)}）')


