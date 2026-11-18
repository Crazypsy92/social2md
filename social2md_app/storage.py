from __future__ import annotations

import os
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable, Iterable


@dataclass(frozen=True)
class VolumeUsage:
    path: str
    total_bytes: int
    used_bytes: int
    free_bytes: int
    used_percent: float
    inode_used_percent: float | None

    def to_dict(self) -> dict:
        return asdict(self)


class StorageLimitExceeded(RuntimeError):
    """磁盘空间或 inode 达到保护阈值。"""


class StorageGuard:
    """统一任务流水线的磁盘与 inode 保护。"""

    def __init__(
        self,
        paths: Iterable[str | Path],
        pause_percent: float = 95.0,
        resume_percent: float = 90.0,
        min_free_bytes: int = 1024**3,
        poll_seconds: float = 2.0,
        disk_usage_fn: Callable | None = None,
        statvfs_fn: Callable | None = None,
    ) -> None:
        if not 0 < resume_percent < pause_percent < 100:
            raise ValueError("阈值必须满足 0 < resume_percent < pause_percent < 100")
        if min_free_bytes < 0 or poll_seconds <= 0:
            raise ValueError("最小剩余空间不能为负数，检查间隔必须大于 0")

        self.paths = [Path(p).expanduser() for p in paths]
        self.pause_percent = float(pause_percent)
        self.resume_percent = float(resume_percent)
        self.min_free_bytes = int(min_free_bytes)
        self.poll_seconds = float(poll_seconds)
        self._disk_usage = disk_usage_fn or shutil.disk_usage
        self._statvfs = statvfs_fn or os.statvfs

    @staticmethod
    def _existing_path(path: Path) -> Path:
        current = path
        while not current.exists() and current != current.parent:
            current = current.parent
        return current

    def snapshot(self) -> list[VolumeUsage]:
        volumes: list[VolumeUsage] = []
        seen_devices: set[int] = set()

        for configured_path in self.paths:
            try:
                path = self._existing_path(configured_path)
                stat_result = path.stat()
                device = stat_result.st_dev
                if device in seen_devices:
                    continue
                seen_devices.add(device)

                usage = self._disk_usage(path)
                total = int(usage.total)
                used = int(usage.used)
                free = int(usage.free)
                used_percent = (used / total * 100.0) if total else 100.0

                inode_percent = None
                try:
                    inode = self._statvfs(path)
                    if inode.f_files:
                        inode_used = max(0, inode.f_files - inode.f_ffree)
                        inode_percent = inode_used / inode.f_files * 100.0
                except (AttributeError, OSError, NotImplementedError):
                    pass

                volumes.append(
                    VolumeUsage(
                        path=str(path),
                        total_bytes=total,
                        used_bytes=used,
                        free_bytes=free,
                        used_percent=used_percent,
                        inode_used_percent=inode_percent,
                    )
                )
            except OSError:
                continue

        return volumes

    def should_pause(self, snapshot: list[VolumeUsage] | None = None) -> bool:
        volumes = snapshot if snapshot is not None else self.snapshot()
        if not volumes:
            return True
        for volume in volumes:
            if volume.used_percent >= self.pause_percent:
                return True
            if volume.free_bytes < self.min_free_bytes:
                return True
            if (
                volume.inode_used_percent is not None
                and volume.inode_used_percent >= self.pause_percent
            ):
                return True
        return False

    def can_resume(self, snapshot: list[VolumeUsage] | None = None) -> bool:
        volumes = snapshot if snapshot is not None else self.snapshot()
        if not volumes:
            return False
        for volume in volumes:
            if volume.used_percent >= self.resume_percent:
                return False
            if volume.free_bytes < self.min_free_bytes:
                return False
            if (
                volume.inode_used_percent is not None
                and volume.inode_used_percent >= self.resume_percent
            ):
                return False
        return True

    def pause_reason(self, snapshot: list[VolumeUsage] | None = None) -> str:
        volumes = snapshot if snapshot is not None else self.snapshot()
        if not volumes:
            return "无法读取任何受监控路径的磁盘信息，按安全策略暂停"
        reasons = []
        for volume in volumes:
            if volume.used_percent >= self.pause_percent:
                reasons.append(
                    f"{volume.path} 使用率 {volume.used_percent:.2f}% >= {self.pause_percent:.2f}%"
                )
            if volume.free_bytes < self.min_free_bytes:
                reasons.append(
                    f"{volume.path} 剩余空间 {volume.free_bytes} B < {self.min_free_bytes} B"
                )
            if (
                volume.inode_used_percent is not None
                and volume.inode_used_percent >= self.pause_percent
            ):
                reasons.append(
                    f"{volume.path} inode 使用率 {volume.inode_used_percent:.2f}%"
                )
        return "；".join(reasons) if reasons else "磁盘状态正常"

    def assert_can_start(
        self,
        extra_bytes: int = 0,
        was_paused: bool = False,
    ) -> list[VolumeUsage]:
        volumes = self.snapshot()
        if was_paused:
            if not self.can_resume(volumes):
                raise StorageLimitExceeded(
                    "尚未达到恢复条件：" + self.pause_reason(volumes)
                )
        elif self.should_pause(volumes):
            raise StorageLimitExceeded(self.pause_reason(volumes))

        required_free = self.min_free_bytes + max(0, int(extra_bytes))
        for volume in volumes:
            if volume.free_bytes < required_free:
                raise StorageLimitExceeded(
                    f"{volume.path} 可用空间不足：需要至少 {required_free} B，"
                    f"当前 {volume.free_bytes} B"
                )
        return volumes

    @staticmethod
    def format_snapshot(volumes: list[VolumeUsage]) -> str:
        if not volumes:
            return "无法读取磁盘信息"
        return "\n".join(
            f"{v.path}: {v.used_percent:.2f}% used, "
            f"{v.free_bytes / 1024**3:.2f} GiB free"
            + (
                f", inode {v.inode_used_percent:.2f}%"
                if v.inode_used_percent is not None
                else ""
            )
            for v in volumes
        )
