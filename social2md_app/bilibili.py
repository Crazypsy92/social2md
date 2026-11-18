from __future__ import annotations

import http.cookiejar
import os
import re
from http.cookies import SimpleCookie
from pathlib import Path
from urllib.parse import parse_qs, urlparse


def canonical_url(url: str) -> str:
    """只接受明确的空间投稿页或视频链接，去掉分享跟踪参数。"""
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("Bilibili 链接必须使用 HTTP 或 HTTPS")
    if parsed.hostname == "space.bilibili.com":
        match = re.fullmatch(r"/(\d+)(?:/(?:upload/)?video)?/?", parsed.path)
        if match:
            return f"https://space.bilibili.com/{match[1]}/video"
    if parsed.hostname in {"www.bilibili.com", "bilibili.com"}:
        match = re.fullmatch(r"/video/(BV[0-9A-Za-z]+|av\d+)/?", parsed.path)
        if match:
            page = parse_qs(parsed.query).get("p", [""])[0]
            suffix = f"?p={int(page)}" if page.isdigit() and int(page) > 0 else ""
            return f"https://www.bilibili.com/video/{match[1]}{suffix}"
    raise ValueError("请提供 Bilibili 空间投稿页或 BV/av 视频链接")


class QuietLogger:
    """上游日志可能含签名媒体地址或请求信息，统一由调用方报告安全错误。"""

    def debug(self, message):
        pass

    def warning(self, message):
        pass

    def error(self, message):
        pass


def access_error(exc: Exception) -> str:
    message = str(exc)
    if re.search(r"(?:352|401|412|799)", message):
        return "Bilibili 拒绝请求或触发限流，请稍后重试；必要时安全配置 BILIBILI_COOKIE"
    if "CERTIFICATE_VERIFY_FAILED" in message:
        return "TLS 证书校验失败，请检查云环境的系统 CA 配置"
    if "403" in message:
        return "Bilibili 或网络代理拒绝访问（HTTP 403），请检查网络策略及登录态"
    return "Bilibili 提取或下载失败，请检查访问权限、网络及 yt-dlp 版本"


class BilibiliAdapter:
    """使用 yt-dlp 分页提取元数据，每次只下载一个分 P。"""

    def __init__(self):
        try:
            from yt_dlp import YoutubeDL
        except ImportError as exc:
            raise RuntimeError("Bilibili 采集需要安装 requirements.txt 中的 yt-dlp") from exc
        self.factory = YoutubeDL

    def _client(self, **options):
        # 系统 CA 包含云代理证书，保持 TLS 验证启用。
        client = self.factory({
            "quiet": True,
            "no_warnings": True,
            "logger": QuietLogger(),
            "compat_opts": {"no-certifi"},
            "socket_timeout": 30,
            "retries": 2,
            "extractor_retries": 1,
            "fragment_retries": 2,
            "concurrent_fragment_downloads": 1,
            "cachedir": False,
            **options,
        })
        cookie = os.environ.get("BILIBILI_COOKIE", "").strip()
        if cookie:
            parsed = SimpleCookie()
            parsed.load(cookie)
            if not parsed:
                raise RuntimeError("BILIBILI_COOKIE 格式无效，请在环境设置中重新配置")
            for name, value in parsed.items():
                client.cookiejar.set_cookie(http.cookiejar.Cookie(
                    0, name, value.value, None, False, ".bilibili.com", True, True,
                    "/", True, True, None, True, None, None, {},
                ))
        return client

    def entries(self, url: str):
        # 扁平列表保持惰性，空间分页由平台提取器负责。
        with self._client(extract_flat=True, lazy_playlist=True) as client:
            info = client.extract_info(canonical_url(url), download=False)
            yield from self._flatten(info)

    def _flatten(self, info):
        if not info:
            raise RuntimeError("Bilibili 返回空元数据")
        if info.get("_type") in {"playlist", "multi_video"}:
            for entry in info["entries"]:
                yield from self._flatten(entry)
        else:
            yield info

    def resolve(self, entry: dict):
        # 分 P / 合集继续展开元数据，媒体仍由调用方逐个下载。
        url = entry.get("webpage_url") or entry.get("url")
        if not url:
            raise RuntimeError("Bilibili 条目缺少来源链接")
        with self._client(lazy_playlist=True) as client:
            yield from self._flatten(client.extract_info(url, download=False))

    def download(self, info: dict, target: Path, guard):
        def check_space(progress):
            remaining = max(0, (progress.get("total_bytes") or 0) - progress.get("downloaded_bytes", 0))
            # 合并时需要同时保留音视频分流与成品。
            guard.assert_can_start(extra_bytes=remaining * 2)

        guard.assert_can_start()
        with self._client(
            outtmpl=str(target.with_suffix(".%(ext)s")),
            format="bestvideo+bestaudio/best",
            merge_output_format="mkv",
            progress_hooks=[check_space],
            postprocessor_hooks=[lambda _: guard.assert_can_start()],
            continuedl=True,
        ) as client:
            client.process_ie_result(dict(info), download=True)
        guard.assert_can_start()
        if not target.is_file():
            # 单流视频不会经过合并步骤。
            for extension in ("mp4", "flv", "webm"):
                candidate = target.with_suffix(f".{extension}")
                if candidate.is_file():
                    return candidate
            raise RuntimeError("下载结束但未找到媒体成品")
        return target
