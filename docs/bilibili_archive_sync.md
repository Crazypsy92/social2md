# Bilibili 转录归档说明

归档按 UP 主名称整理，Markdown 文件名使用作品标题，便于直接浏览。small 版文档和 ZIP 已按要求删除；源视频、SQLite 状态数据库与运行缓存没有提交。

## 归档内容

| UP 主 | 内容 | 目录 |
|---|---|---|
| 硬件何工 | large-v3 转录 10 篇、低置信度清单 1 篇及 Markdown ZIP | [`硬件何工/`](archives/bilibili/硬件何工/) |
| 饶厂长讲传统工科求职 | 当前已有的 72 篇 Markdown 及 Markdown ZIP | [`饶厂长讲传统工科求职/`](archives/bilibili/饶厂长讲传统工科求职/) |
| 幻灵Kuri | 6 篇 large-v3 Markdown、Markdown ZIP、机器可读处理清单 | [`幻灵Kuri/`](archives/bilibili/幻灵Kuri/) |

第二个 UP 主的状态快照是 71 条 `COMPLETED`、1 条 `FAILED`、2 条 `REVIEW_REQUIRED`；扫描游标在列表第 60 条，`scan_complete=0`。归档只表示当前已生成的文档，不表示空间采集完成。标题在每位 UP 主的归档中唯一，因此文件名无需附加 BV 号或哈希；每篇文档的来源链接仍保留 BV 号。

## 运行数据与云端去重

程序运行结果写入由 `--out-dir`、`--export-dir` 指定的目录；归档样例放在 `docs/archives/`，两者用途不同。Bilibili 新生成的 Markdown 默认使用 `output/<UP主名称>/<作品标题>_<BV号>.md` 命名，方便查找并避免同名覆盖。

Bilibili 主页任务以 SQLite 状态库中的 `(platform, content_id)` 作为唯一键；`content_id` 是作品 BV 号，分 P 分开记录。`COMPLETED` 条目会检查 Markdown 有效性；启用 `--keep-source` 时也要求对应源视频存在。`FAILED` 条目若源视频仍在会复用视频重试；`REVIEW_REQUIRED` 默认跳过，显式使用 `--retry-review` 才重试。

GitHub 上的归档文档和 ZIP 不能单独让新云端环境判断哪些任务已处理。跨环境续跑需要持久化 SQLite 状态库，以及其引用的 Markdown 和源视频。其他软件的 SQLite 依赖、查询示例和处理规则见[状态库集成说明](state_db_integration.md)。


幻灵Kuri 的处理清单为 [`processed_items.json`](archives/bilibili/幻灵Kuri/processed_items.json)。其他软件按 `(platform, content_id)` 去重，仅将 `COMPLETED` 识别为已处理；清单包含 9 条筛选结果及各自状态：6 条完成、1 条处理中、2 条待处理。
