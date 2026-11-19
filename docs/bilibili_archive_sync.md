# Bilibili 转录文档归档说明

本次整理后的交付只保留 large-v3 版和第二个 UP 主当前已有的 Markdown 文档与检查点 ZIP。small 版已从仓库和本地文档输出中删除。源视频、SQLite 状态数据库及运行缓存没有提交。

## 归档内容

归档快照统一放在 [`docs/archives/bilibili/`](archives/README.md)：

| UP 主空间 | 内容 | 位置 |
|---|---|---|
| `3707065532942758` | large-v3 转录 10 篇、低置信度清单 1 篇、仅含上述 Markdown 的 ZIP | [`large-v3/`](archives/bilibili/3707065532942758/large-v3/) |
| `1696279173` | 当前 72 篇 Markdown、仅含 Markdown 的 ZIP | [`1696279173/`](archives/bilibili/1696279173/) |

第二个空间的任务状态快照为 71 条 `COMPLETED`、1 条 `FAILED`、2 条 `REVIEW_REQUIRED`；扫描游标位于列表第 60 条，`scan_complete=0`。归档只代表当前已生成的文档，不表示空间采集完成。

## 运行结果与云端去重

程序运行结果写入由 `--out-dir`、`--export-dir` 指定的目录；这些目录属于运行数据，不应与人工归档样例混放。仓库内精选归档放在 `docs/archives/`，并附有清单说明其来源和范围。

Bilibili 主页任务以 SQLite 状态库中的 `platform + content_id` 作为唯一键，`content_id` 是 BV 号，分 P 会各自记录。云端恢复同一主页任务时，`COMPLETED` 条目会检查 Markdown 有效性；启用 `--keep-source` 时也要求对应源视频仍存在。`FAILED` 条目若源视频仍在会复用视频重试；`REVIEW_REQUIRED` 默认跳过，显式使用 `--retry-review` 才重试。

因此，GitHub 上的 Markdown 和 ZIP **不能单独让新的云端环境判断任务是否处理过**。跨环境断点续跑还需要保存并恢复任务 SQLite 状态库，以及该状态引用的源视频和输出文件；恢复时需确保配置路径可用。当前归档没有状态库和源视频，只供查看或下载。云端每次处理完成后，应把更新的 SQLite 状态库保存到持久存储，供后续任务读取。

使用 `--input-dir` 时，状态 ID 根据源视频绝对路径的 SHA-256 生成；迁移后路径变化会产生不同 ID。Bilibili 主页模式使用 BV 号，更适合跨路径识别。多个软件/任务请使用独立的输出和状态目录，不要同时写同一个 SQLite 数据库。
