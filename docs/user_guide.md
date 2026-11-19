# Social2MD 使用指南

Social2MD 只有一套处理流水线，不区分云端版和本地版。抖音主页、已有视频目录和文档目录使用同一个命令入口、任务状态库、磁盘保护和恢复机制。

## 1. 环境准备

建议使用 Codex Cloud 的 Linux Python 环境。执行：

```bash
bash scripts/setup.sh
```

OCR 和文档转换为可选功能：

```bash
pip install -r requirements-optional.txt
```

系统需要 ffmpeg / ffprobe。初始化和测试阶段不会下载真实作品。

## 2. 唯一命令入口

```bash
python social2md.py --help
```

三种输入来源互斥，一次运行只选择一种：

| 参数 | 输入 | 处理方式 |
|---|---|---|
| `-u URL` | Douyin 主页 | F2 分页获取作品，逐项下载和转录 |
| `--input-dir PATH` | 已有视频目录 | 逐项校验、ASR/OCR、Markdown |
| `--document-dir PATH` | 文档目录 | 逐项转换为 Markdown |

## 3. Douyin 主页

在 Codex Cloud 安全环境变量中配置 `DOUYIN_COOKIE`。不要把 Cookie 写进命令、任务提示词、日志或仓库。

先处理 30 个作品：

```bash
python social2md.py -u "主页链接" -b "作者名称" --batch-size 30 --max-items 30
```

确认输出质量后，去掉 `--max-items 30` 继续扫描。默认每批获取最多 30 条作品元数据，但下载和转录始终一次处理一个作品。

## 4. Bilibili UP 主空间

用 `-b` 指定 UP 主名称，默认 Markdown 路径为 `output/<UP主名称>/<作品标题>_<BV号>.md`。文件名保留标题便于查找，并用 BV 号保证唯一。已有状态记录指向的 Markdown 若仍存在则沿用原路径，缺失时新输出使用标题格式。恢复任务时继续使用相同主页链接和状态目录；SQLite 去重键仍为平台和 BV 号。

```bash
python social2md.py -u "https://space.bilibili.com/用户ID/video" \
  -b "UP主名称" --keep-source
```

## 5. 已有视频目录

```bash
python social2md.py --input-dir "videos/inbox" -b "视频归档"
```

视频目录走与 Douyin 下载任务相同的处理规则：

1. 检查源视频能否被 ffprobe 读取。
2. 提取音频并进行 ASR，或使用 `--ocr` 做视频帧 OCR。
3. 繁转简、标点恢复和自然段整理。
4. Markdown 原子写入并验证内容。
5. 检查转录质量；低置信度标记为 `REVIEW_REQUIRED`。
6. 只有全部通过才自动删除源视频。

如需保留源视频，添加 `--keep-source`。

## 6. 文档目录

先安装可选依赖：

```bash
pip install -r requirements-optional.txt
```

运行：

```bash
python social2md.py --document-dir "documents/inbox" -b "文档归档"
```

文档按文件逐项转换，结果非空后原子写入 Markdown。源文档永远不会被删除。

## 7. 常用参数

| 参数 | 作用 | 默认 |
|---|---|---|
| `-b, --blogger` | 作者或任务目录名称 | 未分类 |
| `--batch-size` | Douyin 每批元数据数 | 30 |
| `--max-items` | 本次最多处理数量，0 为不限 | 0 |
| `--model` | Whisper 模型 | small |
| `--language` | 转录语言 | zh |
| `--ocr` | 使用视频帧 OCR 替代 ASR | 关闭 |
| `--frame-interval` | OCR / 抽帧间隔秒数 | 3 |
| `--save-frames` | 同时导出关键帧 | 关闭 |
| `--keep-source` | 成功后保留视频源文件 | 关闭 |
| `--retry-review` | 重新处理低置信度任务 | 关闭 |
| `--force` | 忽略已完成状态并重做 | 关闭 |
| `--dry-run` | 仅检查，不下载或转换 | 关闭 |
| `--pause-percent` | 磁盘暂停阈值 | 95% |
| `--resume-percent` | 磁盘恢复阈值 | 90% |
| `--min-free-gib` | 最低剩余空间 | 1 GiB |

## 8. 断点恢复和状态

状态库按来源保存，作品记录以 `platform + content_id` 为唯一键。已有旧版 Douyin 数据库会自动迁移，旧作品状态不会被丢弃。

Python 自带 `sqlite3`，读取状态库不需要额外安装数据库服务。其他程序若需复用去重规则，应只读 `works` 表并按组合键查询；状态 schema、SQLite 驱动和云端备份说明见[状态库集成说明](state_db_integration.md)。GitHub 仓库不包含被 `.gitignore` 排除的 SQLite 状态文件。

- `COMPLETED`：输出通过校验。
- `PROCESSING`：上次中断时正在处理；重新运行可继续。
- `FAILED`：失败，源文件保留；重新运行会再次尝试。
- `REVIEW_REQUIRED`：低置信度，默认跳过；使用 `--retry-review` 重试。
- `PENDING`：等待磁盘空间恢复。

## 8. 输出结构

```text
output/
├── <author_or_job>/
│   └── YYYY-MM-DD/
├── documents/
│   └── <job>/
videos/
state/
exports/
```

导出的 ZIP 只包含 Markdown，不包含视频、Cookie、模型和数据库。云端工作目录可能是临时环境，重要 ZIP 需要在任务结束前导出到持久化位置。

## 9. 安全约束

- 不把 Cookie 写入 Git、日志或命令参数。
- 不在测试中访问真实账号。
- 不删除空转录、失败或低置信度视频。
- 不删除任何源文档。
- 不手动清空状态数据库来“重置任务”；确需重跑时使用 `--force` 或 `--refresh`。
