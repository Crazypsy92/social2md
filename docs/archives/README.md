# 归档样例清单

这里保存人工整理的转录归档，按平台和 UP 主名称分目录，Markdown 文件直接使用作品标题。它们是历史结果，不是 Social2MD 的运行输入或实时任务状态。程序新运行时的数据仍写入仓库根目录的 `output/`、`exports/`、`state/` 和 `videos/`，这些目录由 `.gitignore` 排除。

## Bilibili

| UP 主 | 归档内容 | 处理范围 |
|---|---|---|
| [硬件何工](bilibili/硬件何工/) | 10 篇 large-v3 转录、1 篇低置信度清单、转录 ZIP | small 版按用户要求移除 |
| [饶厂长讲传统工科求职](bilibili/饶厂长讲传统工科求职/) | 当前已有的 72 篇 Markdown 和转录 ZIP | 归档时状态为 71 完成、1 失败、2 待复核；扫描尚未结束 |
| 幻灵Kuri | 已迁移至 [Book Relay 游戏专区](https://github.com/Crazypsy92/book-relay/tree/main/games/赛博朋克2077) | 9 篇原始转录、6 份整合分析文档及转录处理记录，长期归档位置已调整 |

Markdown 文件名使用作品标题；作品 BV 号保留在文档来源链接中。标题在各自归档中唯一，所以文件名不附加难辨认的 ID 或哈希。ZIP 只含 Markdown。

源视频、SQLite 状态库、模型和运行缓存均不在归档中。云端断点恢复需要单独持久化状态库及其引用的源视频和输出；跨软件读取方式见[状态库集成说明](../state_db_integration.md)。
