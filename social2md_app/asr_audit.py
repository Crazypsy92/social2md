"""独立 ASR 对照实验；原媒体、Markdown 与生产状态只读。"""

from __future__ import annotations
import difflib
import hashlib
import json
import os
from pathlib import Path
import re
import resource
import subprocess
import sys
import time
import unicodedata


def normalized(text):
    return "".join(
        c.lower() for c in unicodedata.normalize("NFKC", text) if c.isalnum()
    )


def detect_issues(text, terms=()):
    issues = []
    if not text.strip():
        issues.append({"type": "empty_transcript"})
    for match in re.finditer("\ufffd", text):
        issues.append(
            {
                "type": "replacement_character",
                "offset": match.start(),
                "original": text[max(0, match.start() - 15) : match.end() + 15],
            }
        )
    for match in re.finditer(r"(.{8,80}?)\1{2,}", text):
        issues.append(
            {"type": "repetition", "offset": match.start(), "original": match.group()}
        )
    for term in terms:
        for alias in term.get("aliases", []):
            if alias in text:
                issues.append(
                    {
                        "type": "term_candidate",
                        "original": alias,
                        "candidate": term["term"],
                        "reason": "用户词典候选，尚需音频证据",
                    }
                )
    return issues


def compare_segment(
    original, secondary, start, end, suggestions=(), terms=(), third_text=None
):
    issues = detect_issues(original, terms)
    if secondary is not None and normalized(original) != normalized(secondary):
        issues.append(
            {
                "type": "asr_disagreement",
                "original": original,
                "candidate": secondary,
                "reason": "独立 ASR 结果不一致",
            }
        )
    if third_text is not None and normalized(third_text) != normalized(original):
        issues.append({"type": "third_asr_disagreement", "candidate": third_text})
    if secondary is None:
        issues.append({"type": "secondary_unavailable"})
    return {
        "start": start,
        "end": end,
        "whisper": original,
        "secondary": secondary,
        "suggestions": list(suggestions),
        "issues": issues,
        "final_text": original,
        "status": "REVIEW_REQUIRED" if issues or suggestions else "AGREEMENT",
        "automatically_applied": [],
    }


def worker(request_path, output_path):
    request = json.loads(Path(request_path).read_text())
    engine = request["engine"]
    started = time.monotonic()
    if engine != "whisper":
        import torch

        torch.set_num_threads(4)
    cache = Path(request["cache"])
    cache.mkdir(parents=True, exist_ok=True)
    os.environ["HF_HOME"] = str(cache / "huggingface")
    os.environ["MODELSCOPE_CACHE"] = str(cache / "modelscope")
    os.environ["PYCORRECTOR_DATA_DIR"] = str(cache / "pycorrector")
    os.environ.setdefault("MODELSCOPE_DOWNLOAD_PARALLELS", "4")
    records = []
    if engine == "whisper":
        from .video import transcribe

        for clip in request["clips"]:
            prompt = (
                "参考术语：" + "、".join(t["term"] for t in request["terms"])
                if request["terms"]
                else None
            )
            details = []
            segments, quality = transcribe(
                Path(clip["path"]),
                "small",
                "zh",
                initial_prompt=prompt,
                segment_details=details,
            )
            records.append(
                {
                    "clip": clip["index"],
                    "text": "".join(s[2] for s in segments),
                    "segments": segments,
                    "segment_details": details,
                    "quality": quality,
                }
            )
    elif engine == "funasr":
        from funasr import AutoModel

        model = AutoModel(
            model="paraformer-zh", hub="ms", device="cpu", disable_update=True
        )
        for clip in request["clips"]:
            baseline = None
            if not records:
                baseline = model.generate(
                    input=clip["path"], hotword="", batch_size_s=30, pred_timestamp=True
                )
            result = model.generate(
                input=clip["path"],
                hotword=" ".join(t["term"] for t in request["terms"]),
                batch_size_s=30,
                pred_timestamp=True,
            )
            records.append(
                {
                    "clip": clip["index"],
                    "text": result[0].get("text", ""),
                    "raw": result,
                    "without_hotwords_first_clip": baseline,
                }
            )
    elif engine == "qwen":
        import torch
        from qwen_asr import Qwen3ASRModel

        model = Qwen3ASRModel.from_pretrained(
            "Qwen/Qwen3-ASR-0.6B",
            dtype=torch.float32,
            device_map="cpu",
            max_inference_batch_size=1,
            max_new_tokens=1024,
        )
        for clip in request["clips"]:
            if clip.get("offset_seconds", 0) != 0:
                continue
            result = model.transcribe(audio=clip["path"], language="Chinese")
            records.append({"clip": clip["index"], "text": result[0].text})
    elif engine == "pycorrector":
        from pycorrector import MacBertCorrector

        model = MacBertCorrector("shibing624/macbert4csc-base-chinese")
        for clip in request["clips"]:
            # 仅返回候选，不采纳模型改写。
            records.append(
                {
                    "clip": clip["index"],
                    "candidates": model.correct_batch([clip["text"]]),
                }
            )
    else:
        raise ValueError("未知实验引擎")
    from importlib.metadata import version

    package = {
        "whisper": "faster-whisper",
        "funasr": "funasr",
        "qwen": "qwen-asr",
        "pycorrector": "pycorrector",
    }[engine]
    result = {
        "engine": engine,
        "version": version(package),
        "seconds": time.monotonic() - started,
        "peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        "parameters": {
            "device": "cpu",
            "terms": request["terms"],
            "language": "zh",
            "cpu_threads": 8 if engine == "whisper" else 4,
            "model": {
                "whisper": "small",
                "funasr": "iic/speech_seaco_paraformer_large_asr_nat-zh-cn-16k-common-vocab8404-pytorch",
                "qwen": "Qwen/Qwen3-ASR-0.6B",
                "pycorrector": "shibing624/macbert4csc-base-chinese",
            }[engine],
        },
        "records": records,
    }
    Path(output_path).write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def run_audit(args):
    source = args.input_dir.resolve()
    output = Path(args.audit_output).resolve()
    if output == source or source in output.parents:
        raise ValueError("实验输出必须位于源视频目录以外")
    output.mkdir(parents=True, exist_ok=False)
    terms = json.loads(Path(args.audit_terms).read_text()) if args.audit_terms else []
    videos = sorted(
        p for p in source.iterdir() if p.suffix.lower() in {".mp4", ".mkv", ".webm"}
    )
    if not videos:
        raise ValueError("实验目录中没有视频")
    manifest = {
        str(p): hashlib.file_digest(p.open("rb"), "sha256").hexdigest() for p in videos
    }
    (output / "source_hashes.json").write_text(json.dumps(manifest, indent=2))
    clips = []
    # 每个片段使用同一份 PCM WAV，所有模型对照同一音频。
    for video_index, video in enumerate(videos[: args.audit_limit], 1):
        probe = subprocess.check_output(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "json",
                str(video),
            ],
            text=True,
        )
        duration = float(json.loads(probe)["format"]["duration"])
        limit = duration if args.audit_full else min(duration, args.audit_seconds)
        offset = 0.0
        while offset < limit:
            index = len(clips) + 1
            length = min(args.audit_seconds, limit - offset)
            clip = output / f"clip_{index:04d}.wav"
            subprocess.run(
                [
                    "ffmpeg",
                    "-v",
                    "error",
                    "-ss",
                    str(offset),
                    "-i",
                    str(video),
                    "-t",
                    str(length),
                    "-vn",
                    "-ar",
                    "16000",
                    "-ac",
                    "1",
                    "-c:a",
                    "pcm_s16le",
                    str(clip),
                ],
                check=True,
            )
            clips.append(
                {
                    "index": index,
                    "video_index": video_index,
                    "path": str(clip),
                    "source": str(video),
                    "offset_seconds": offset,
                    "end_seconds": offset + length,
                    "audio_sha256": hashlib.file_digest(
                        clip.open("rb"), "sha256"
                    ).hexdigest(),
                }
            )
            offset += length
    (output / "clips.json").write_text(json.dumps(clips, indent=2))
    results = {}
    for engine in ["whisper", "funasr", "qwen", "pycorrector"]:
        engine_clips = clips
        if engine == "pycorrector":
            engine_clips = [
                {"index": r["clip"], "text": r["text"]}
                for r in results.get("whisper", {}).get("records", [])
            ]
        request = {
            "engine": engine,
            "clips": engine_clips,
            "terms": terms,
            "cache": args.audit_cache,
        }
        request_path = output / f"{engine}_request.json"
        request_path.write_text(json.dumps(request, ensure_ascii=False))
        result_path = output / f"{engine}.json"
        python = sys.executable if engine == "whisper" else args.audit_python
        try:
            with (output / f"{engine}.log").open("w") as log:
                completed = subprocess.run(
                    [
                        python,
                        "-c",
                        "from social2md_app.asr_audit import worker; import sys; worker(*sys.argv[1:])",
                        str(request_path),
                        str(result_path),
                    ],
                    stdout=log,
                    stderr=log,
                    timeout=args.audit_timeout,
                )
        except OSError as exc:
            results[engine] = {
                "status": "UNAVAILABLE",
                "error_type": type(exc).__name__,
            }
            continue
        except subprocess.TimeoutExpired:
            results[engine] = {
                "status": "TIMEOUT",
                "timeout_seconds": args.audit_timeout,
            }
            continue
        results[engine] = (
            json.loads(result_path.read_text())
            if completed.returncode == 0 and result_path.exists()
            else {"status": "UNAVAILABLE", "exit_code": completed.returncode}
        )
    corrections = []
    for clip in clips:
        index = clip["index"]
        primary = next(
            (r for r in results["whisper"].get("records", []) if r["clip"] == index),
            None,
        )
        if primary is None:
            corrections.append({"clip": index, "status": "PRIMARY_UNAVAILABLE"})
            continue
        second = next(
            (r for r in results["funasr"].get("records", []) if r["clip"] == index),
            None,
        )
        suggestions = next(
            (
                r["candidates"]
                for r in results.get("pycorrector", {}).get("records", [])
                if r["clip"] == index
            ),
            [],
        )
        suggestions = [
            s
            for s in suggestions
            if s.get("errors") or s.get("target") != s.get("source")
        ]
        row = compare_segment(
            primary["text"],
            second["text"] if second else None,
            clip["offset_seconds"],
            clip["end_seconds"],
            suggestions=suggestions,
            terms=terms,
        )
        row["video_index"] = clip["video_index"]
        row["qwen"] = next(
            (
                r["text"]
                for r in results.get("qwen", {}).get("records", [])
                if r["clip"] == index
            ),
            None,
        )
        if row["qwen"] is not None and normalized(row["qwen"]) != normalized(
            primary["text"]
        ):
            row["issues"].append(
                {"type": "third_asr_disagreement", "candidate": row["qwen"]}
            )
            row["status"] = "REVIEW_REQUIRED"
        quality = primary.get("quality", {})
        from .video import LOW_LOGPROB, HIGH_COMPRESSION

        if (
            quality.get("avg_logprob", 0) < LOW_LOGPROB
            or quality.get("max_compression", 0) > HIGH_COMPRESSION
        ):
            row["issues"].append({"type": "low_confidence", "quality": quality})
            row["status"] = "REVIEW_REQUIRED"
        row["differences"] = (
            [
                {"original": primary["text"][a:b], "candidate": second["text"][c:d]}
                for kind, a, b, c, d in difflib.SequenceMatcher(
                    None, primary["text"], second["text"] if second else ""
                ).get_opcodes()
                if kind != "equal"
            ]
            if second
            else []
        )
        corrections.append({"clip": index, **row})
    result = {
        "models": results,
        "comparisons": corrections,
        "cer": None,
        "reference_status": "未提供人工核验参考文本",
    }
    (output / "comparison.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2)
    )
    review_dir = output / "review_md"
    review_dir.mkdir(exist_ok=True)
    for video_index in sorted(
        {row["video_index"] for row in corrections if "video_index" in row}
    ):
        blocks = [f"# 转录校对稿 {video_index:02d}"]
        for row in corrections:
            if row.get("video_index") != video_index:
                continue
            label = "待核" if row["status"] == "REVIEW_REQUIRED" else "模型文本一致"
            blocks.extend(
                [f"{label} {row['start']:.1f}–{row['end']:.1f} 秒", row["final_text"]]
            )
        (review_dir / f"video_{video_index:02d}.md").write_text(
            "\n\n".join(blocks), encoding="utf-8"
        )
    if any(
        hashlib.file_digest(Path(p).open("rb"), "sha256").hexdigest() != digest
        for p, digest in manifest.items()
    ):
        raise RuntimeError("源视频摘要变化")
    print(f'实验报告：{output / "comparison.json"}')
    return 0 if results["whisper"].get("records") else 1
