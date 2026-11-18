# AGENTS.md

## Git 分支与提交规则

本项目采用单分支工作流，长期只保留 `main`：

1. Codex 默认直接在 `main` 分支工作，不创建 `codex/*`、`feature/*`、`fix/*` 等临时分支。
2. 不为常规修改创建 Pull Request；完成修改后先运行相关测试，再直接提交并推送到 `main`。
3. 每次提交只包含一个逻辑完整的修改主题，提交信息应清晰说明改动。
4. 修改前先检查工作区和远端状态；不得覆盖或丢弃用户尚未提交的改动。
5. 需要回退时优先使用 Git 历史定位并恢复，不通过创建长期分支保存备份。
6. 只有用户明确要求并行开发、隔离实验或发布维护时，才临时创建分支；任务结束后合并并删除临时分支。

## 项目定位

Social2MD 是统一的社交内容归档流水线。所有来源共用同一套任务状态、逐项处理、磁盘保护、质量校验、失败恢复和 Markdown 导出规则。不要重新拆分“云端版 / 本地版”，也不要创建第二套绕过安全规则的处理入口。

当前已接入 Douyin 主页作品采集。Bilibili 和小红书尚未接入。已有视频目录和文档目录可作为统一流水线的输入来源。

## 唯一入口

```bash
python social2md.py --help
```

来源参数三选一：
- `-u/--url`：Douyin 主页采集。
- `--input-dir`：已有视频目录，复用同一媒体处理队列。
- `--document-dir`：文档目录，使用同一状态与磁盘保护机制；源文档永不删除。

不要恢复旧的 `douyin2txt.py`、`cloud_runner.py`、`video2txt.py`、`doc2md.py` 独立入口。

## 模块职责

| 路径 | 职责 |
|---|---|
| `social2md.py` | 唯一 CLI 启动入口 |
| `social2md_app/cli.py` | 统一调度、Douyin 采集、视频目录与文档目录处理 |
| `social2md_app/video.py` | 视频校验、ASR、视频帧 OCR、文本规范化、Markdown 写入 |
| `social2md_app/documents.py` | 可选 MarkItDown 文档转换 |
| `social2md_app/state.py` | 统一 SQLite 状态库 |
| `social2md_app/storage.py` | 磁盘与 inode 保护 |

## 统一任务规则

1. 状态唯一键必须为 `platform + content_id`，不能只使用作品 ID。
2. 媒体逐项处理；Douyin 默认每批获取 30 条元数据，但媒体下载和转录并发保持为 1。
3. 先校验媒体，再处理；Markdown 必须原子写入并通过有效性检查。
4. 视频只有在输出有效、转录非空且质量未触发复核时才能自动删除。
5. 失败、异常、空转录、低置信度任务必须保留源视频。
6. 文档转换永远不删除源文档。
7. `REVIEW_REQUIRED` 默认不自动重试；用户显式传入 `--retry-review` 才重新处理。
8. 磁盘暂停阈值 95%，恢复阈值 90%，最低可用空间 1 GiB。
9. 断点状态和旧 Douyin 数据库必须保留；升级状态 schema 时实现迁移，不得直接删除用户状态。
10. 测试与安装阶段禁止真实下载、真实 Cookie 和真实账号访问。

## 兼容性与依赖

- Python 3.10+；云端建议 Python 3.11。
- 系统依赖：ffmpeg、ffprobe。
- 核心依赖见 `requirements.txt`。
- OCR 和 MarkItDown 为可选依赖，见 `requirements-optional.txt`。
- Cookie 通过 Codex Cloud 安全环境变量 `DOUYIN_COOKIE` 注入，不得打印或提交。

## 验证命令

```bash
python -m py_compile social2md.py social2md_app/*.py
python -m unittest discover -s tests -v
python social2md.py --help
python social2md.py --input-dir /tmp/social2md-empty --dry-run
```

不要在自动化测试中调用真实平台下载或转录模型。新平台必须通过独立适配器接入，并提供模拟测试与端到端验收证据。

## 文件与文档规范

- 目录、文件名、Python 标识符使用英文 snake_case。
- 文档正文使用中文。
- 文档统一放在 `docs/`。
- 测试命名为 `tests/test_<module_or_behavior>.py`。
- 不提交 Cookie、数据库、媒体、模型、运行日志和输出目录。
