# Social2MD — 统一社交内容归档流水线

Social2MD 将社交平台视频、已有视频文件和文档统一处理为 Markdown。项目采用**一套任务流水线**，不再区分“云端版”和“本地版”：不同来源共用任务状态、逐项处理、磁盘保护、质量校验、失败恢复和导出机制。

## 当前平台支持

| 来源 / 平台 | 内容类型 | 状态 |
|---|---|---|
| Douyin（抖音） | 主页作品视频 | 已接入，使用 F2 |
| Bilibili | 视频、UP 主空间 | 适配器已实现，真实端到端验收待完成 |
| Xiaohongshu（小红书） | 视频笔记 | 尚未接入 |
| Xiaohongshu（小红书） | 图文笔记 | 尚未接入，需图片采集与图片 OCR |
| 已有视频目录 | 视频文件 | 统一流水线支持 |
| 文档目录 | PDF、Word、PPT、Excel、HTML 等 | 可选 MarkItDown 转换 |

上游工具支持某个平台，不代表 Social2MD 已经接入。每个平台必须完成真实链接、登录态、分页、媒体下载和端到端测试后，才能更新为“已接入”。

## 统一处理规则

- 所有来源进入同一个任务状态库，唯一键为 `platform + content_id`。
- 媒体按队列逐项处理；Douyin 元数据默认每批 30 条，但不会并行缓存 30 个视频。
- 视频依次完成下载/读取、媒体校验、ASR 或 OCR、Markdown 原子写入和质量检查。
- 只有 Markdown 有效且未触发低置信度复核，才允许自动删除视频源文件。
- 失败、空转录、损坏媒体和低置信度任务保留源文件，可断点恢复。
- 文档转换只生成 Markdown，**绝不删除源文档**。
- 磁盘使用率达到 95% 暂停，低于 90% 才允许恢复，并至少保留 1 GiB 可用空间。

## 安装

建议在 Codex Cloud / Linux Python 环境中运行。环境初始化只安装依赖、编译代码和执行测试，不会下载真实作品。

```bash
git clone https://github.com/Crazypsy92/social2md.git
cd social2md
bash scripts/setup.sh
```

OCR 和文档转换为可选能力：

```bash
pip install -r requirements-optional.txt
```

系统需要 `ffmpeg` 和 `ffprobe`。安装脚本会在 Debian/Ubuntu 环境中安装 ffmpeg。

## 使用方式

统一入口只有一个：`social2md.py`。

### 1. 抖音主页采集

在运行环境的安全环境变量中配置 `DOUYIN_COOKIE`，不要把 Cookie 写入代码、命令参数、日志或 GitHub。

先做小批量验证：

```bash
python social2md.py -u "抖音主页链接" -b "作者名称" --batch-size 30 --max-items 30
```

确认结果后，去掉 `--max-items 30` 继续完整扫描。默认每批获取最多 30 个作品元数据，下载、转录和校验始终逐项执行。

### Bilibili 空间与视频采集

使用同一入口，支持空间自动分页与多分 P；默认不限制总数。完整空间运行和当前验收限制见 [Bilibili 运行说明](docs/bilibili_run.md)。

```bash
python social2md.py -u "https://space.bilibili.com/用户ID/video" -b "任务名称" --keep-source
```

该适配器使用 yt-dlp。当前固定每页 30 条元数据，媒体逐个下载转录。遇到站点限制时，可在安全环境变量中配置 `BILIBILI_COOKIE`。恢复使用相同命令和目录，按作品状态去重。

### 2. 处理已有视频目录

已有视频文件也进入同一套任务队列、状态库、磁盘保护和安全删除流程：

```bash
python social2md.py --input-dir "videos/inbox" -b "任务名称"
```

视频默认只在 Markdown 写入成功、内容有效且转录质量通过后删除。希望保留源视频时添加 `--keep-source`。

### 3. 文档转 Markdown

需要先安装可选依赖：

```bash
pip install -r requirements-optional.txt
python social2md.py --document-dir "documents/inbox" -b "文档归档"
```

文档转换逐项执行、记录状态并使用磁盘保护；源 PDF、Word、PPT、Excel 等文件始终保留。

### 4. 预览和恢复

```bash
# 只检查参数、输入数量和磁盘，不下载或转换
python social2md.py --input-dir "videos/inbox" --dry-run

# 重新处理低置信度任务
python social2md.py -u "抖音主页链接" -b "作者名称" --retry-review

# 强制重新生成输出
python social2md.py --input-dir "videos/inbox" --force
```

## 输出目录

| 目录 | 内容 |
|---|---|
| `output/` | Markdown 成品、关键帧和质量报告 |
| `videos/` | Douyin 下载缓存或输入视频 |
| `state/` | SQLite 任务状态、分页游标和暂停信息 |
| `exports/` | 只包含 Markdown 的检查点 ZIP |
| `models/` | 可选的标点恢复模型缓存 |

以上都是运行时数据目录，默认由 `.gitignore` 排除，不代表项目代码或固定样例。多个软件或任务共用同一工作区时，请为每个任务显式指定独立的下载、输出、状态和导出目录；状态库不要共用或并发写入。例如：

```bash
python social2md.py -u "主页链接" -b "UP主名称" \
  --download-dir "/workspace/data/UP主名称/videos" \
  --out-dir "/workspace/data/UP主名称/output" \
  --state-dir "/workspace/data/UP主名称/state" \
  --export-dir "/workspace/data/UP主名称/exports"
```

Bilibili 主页任务默认把 Markdown 写到 `output/<UP主名称>/<作品标题>_<BV号>.md`。标题便于人工查找，BV 号避免同名覆盖；SQLite 仍按 `platform + BV号` 去重。已有状态记录指向的 Markdown 若仍存在则沿用原路径，缺失时新输出使用标题格式。云端工作目录可能是临时环境，需把需要保留的输出和状态库保存到持久存储。仓库中的人工整理归档样例统一放在 [`docs/archives/`](docs/archives/README.md)，不会作为运行时输入，也不会与 `output/` 混放。

## 项目结构

```text
social2md/
├── social2md.py                 # 唯一命令行入口
├── social2md_app/
│   ├── cli.py                   # 统一调度与来源入口
│   ├── video.py                 # 视频 ASR、OCR、文本整理与 Markdown 写入
│   ├── documents.py             # 文档转换适配
│   ├── state.py                 # 跨平台任务状态与旧数据库迁移
│   └── storage.py               # 磁盘 / inode 保护
├── docs/
├── scripts/
└── tests/
```

## 测试

```bash
python -m py_compile social2md.py social2md_app/*.py
python -m unittest discover -s tests -v
python social2md.py --help
```

测试不得使用真实 Cookie、真实下载、真实账号或用户数据。

## 版权说明

本项目的历史实现基于开源项目 [hi5jeff/douyinzhengliu](https://github.com/hi5jeff/douyinzhengliu) 修改。原项目未附带许可证；使用和再分发前请自行核实原作者的授权与相关平台规则。

## 中文 ASR 对照实验

ASR-01 提供可选的 Whisper、Paraformer、Qwen 及 pycorrector 对照，保留原文并将差异标为待复核。默认处理入口继续使用现有 Whisper。独立环境与使用步骤见 [实验说明](docs/asr01_usage.md)，已执行的真实数据范围、资源测量和限制见 [模型对照报告](docs/asr01_model_comparison.md)。
