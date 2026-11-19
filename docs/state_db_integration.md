# 任务状态库集成说明

本文说明其他程序如何只读 Social2MD 状态库，识别已处理的作品。状态库是 SQLite 文件，不是独立运行的数据库服务。

## 依赖与文件位置

- Social2MD 使用 Python 自带的 `sqlite3` 模块，无需安装 SQLite 服务或额外 Python 包。
- Python 集成程序也可直接使用标准库 `sqlite3`。Node.js/TypeScript 程序需安装 SQLite 驱动（例如 `better-sqlite3` 或 `sqlite3`）；Java 程序可用 SQLite JDBC 驱动。若要在终端运行 `sqlite3` 命令，需另行安装 SQLite 命令行工具。
- 状态目录默认为仓库的 `state/`；`--state-dir` 可指定其他目录。`.gitignore` 会排除状态文件，所以从 GitHub 新克隆仓库不会自动带上用户的状态库。
- Bilibili 任务的文件名为 `bilibili_<来源键>.sqlite3`。来源键是规范化后的主页或视频 URL 的 SHA-256 前 20 个十六进制字符。主页 URL 规范化规则见 `social2md_app/bilibili.py` 的 `canonical_url()`。

## 当前读取接口

主要作品表结构如下：

| 列 | 含义 |
|---|---|
| `platform` | 来源平台，例如 `bilibili` |
| `content_id` | 平台作品标识；Bilibili 使用 BV 号，文本类型 |
| `status` | 当前处理状态 |
| `title` | 作品标题 |
| `video_path` | 源视频路径，可能为空或已失效 |
| `md_path` | Markdown 路径，可能为空或已失效 |
| `error` | 最近一次失败或复核原因 |
| `updated_at` | Unix 时间戳，单位为秒 |

唯一键是 `(platform, content_id)`，不要只用 BV 号，也不要把作品 ID 转成整数。当前状态值包括 `PENDING_DOWNLOAD`、`DOWNLOADED`、`PROCESSING`、`PENDING`、`COMPLETED`、`REVIEW_REQUIRED` 和 `FAILED`；消费者应允许遇到未知状态，以便兼容将来新增的状态。

- `PENDING_DOWNLOAD`：已发现作品，等待下载。
- `DOWNLOADED`：源视频已保存，等待媒体处理。
- `PROCESSING`：正在校验或转录。
- `PENDING`：受磁盘保护暂停，等待恢复。
- `COMPLETED`：处理完成；使用方仍需检查记录的 Markdown 是否存在且有效。
- `REVIEW_REQUIRED`：需要人工复核，默认不自动重跑。
- `FAILED`：处理失败；若记录的视频仍存在，可从已有视频重试。

Python 只读查询示例：

```python
from pathlib import Path
import sqlite3

db_path = Path("state/bilibili_<来源键>.sqlite3")
uri = db_path.resolve().as_uri() + "?mode=ro"
with sqlite3.connect(uri, uri=True) as con:
    con.row_factory = sqlite3.Row
    rows = con.execute(
        """
        SELECT content_id, status, title, video_path, md_path, error, updated_at
        FROM works
        WHERE platform = ?
        """,
        ("bilibili",),
    ).fetchall()

for row in rows:
    print(row["content_id"], row["status"], row["title"], row["md_path"])
```

请用只读连接，不要由外部程序直接插入、修改或删除状态。要展示可复用的结果，至少应确认状态为 `COMPLETED`、`md_path` 非空且文件仍存在。Social2MD 运行时还会校验 Markdown 内容；启用 `--keep-source` 时也检查 `video_path` 指向的视频是否存在。`REVIEW_REQUIRED` 默认不自动重跑；`FAILED` 作品仅在源视频仍可用时才能直接复用媒体。

`metadata` 表保存分页游标、暂停标记、作品来源 JSON 和质量指标等运行内部信息。跨软件去重请以 `works` 的组合键和状态为准；不要把 `metadata` 中未在本文列出的键当成稳定接口。

## 并发与云端持久化

状态库使用 SQLite WAL 模式。其他程序可以在 Social2MD 运行时只读查询，但不要并发写同一个数据库，也不要用普通文件复制方式在任务运行中备份单独的 `.sqlite3` 文件。可靠迁移应先停止写入，再复制数据库；或使用 SQLite 的 backup API，并同时持久化记录引用的 Markdown 和源视频。

跨云环境续跑还需保留相同任务的状态库、源视频和 Markdown，并确保路径可访问。仅有 GitHub 上的程序代码、归档文档或检查点 ZIP，不包含状态库，也不能让新环境自动识别已处理作品。

本说明描述当前 schema；外部消费者应只读、容忍新增状态，并随所使用的 Social2MD 版本检查 schema 变更。Social2MD 会负责状态迁移，外部程序不要自行修改表结构。
