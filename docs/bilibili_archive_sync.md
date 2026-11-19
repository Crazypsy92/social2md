# Bilibili 转录文档交付说明

本次交付仅包含可阅读的 Markdown 转录文档、只含 Markdown 的检查点 ZIP，以及本说明。源视频、SQLite 状态数据库和运行缓存不包含在交付中。

## 文档清单

| UP 主空间 | Markdown 文件 | 检查点 ZIP |
|---|---:|---|
| `3707065532942758` | Whisper small 版 10 篇；large-v3 版 10 篇及 1 份低置信度清单 | 两个 ZIP，分别含 10 和 11 个 Markdown 文件 |
| `1696279173` | 72 篇 | 1 个 ZIP，含 72 个 Markdown 文件 |

检查点 ZIP 已通过完整性检查，内容均为 Markdown。第二个空间的本地任务状态快照为 71 条 `COMPLETED`、1 条 `FAILED`、2 条 `REVIEW_REQUIRED`；扫描游标位于列表第 60 条，`scan_complete=0`。所以这些文件代表当前已处理结果，不表示该空间已采集完成。

## 云端如何判断作品是否处理过

Bilibili 主页任务以 `platform + content_id` 作为 SQLite 状态库中的唯一键，`content_id` 是 BV 号，分 P 会各自记录。云端恢复同一个主页任务时，状态为 `COMPLETED` 的条目只有在对应 Markdown 有效、且配置了保留源视频时视频仍存在，才会跳过；`FAILED` 条目若源视频仍在会复用视频重试；`REVIEW_REQUIRED` 默认跳过，显式使用 `--retry-review` 才重试。

因此，仅把 Markdown 和 ZIP 放进 GitHub，**不足以**让新的云端环境可靠判断已处理条目。要跨环境续跑，需要另外安全保留并恢复同一任务的 SQLite 状态库，以及它引用的 Markdown 和源视频；各路径也要能在新环境正确对应。当前这次文档交付没有同步状态库和源视频，所以它适合查看和下载结果，不能单独用于云端断点续跑。新云端处理完成后，需将更新后的状态库持久保存，后续运行才能读取最新进度。

若使用 `--input-dir` 处理本地视频，状态 ID 根据视频绝对路径的 SHA-256 生成；迁移后路径变化会产生不同 ID。Bilibili 主页模式使用 BV 号作为作品 ID，更适合跨环境续跑。多个环境不要同时写入同一个 SQLite 状态库。
