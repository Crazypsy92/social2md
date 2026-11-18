# 平台支持与接入边界

## 项目定位

Social2MD 将社交平台视频、图文笔记、原始描述和识别文本归档为 Markdown。所有平台使用同一任务状态和媒体处理流水线，平台差异由独立采集适配器承担。

## 当前支持矩阵

| 平台 / 来源 | 内容类型 | 当前状态 | 说明 |
|---|---|---|---|
| Douyin（抖音） | 主页视频 | 已接入 | 使用 F2；分页、逐项下载、状态恢复 |
| Bilibili | 单条视频、UP 主空间 | 适配器已实现，端到端待验收 | yt-dlp 自动分页与分 P；复用 ASR、质量和状态规则 |
| Xiaohongshu（小红书） | 视频笔记 | 尚未集成 | 需验证分享链接、Cookie 和媒体下载 |
| Xiaohongshu（小红书） | 图文笔记 | 尚未集成 | 需解析正文与图片列表，并增加图片 OCR |
| 文件目录 | 已有视频 | 已接入 | 直接进入统一视频处理队列 |
| 文件目录 | PDF / Office 等文档 | 可选 | 通过 MarkItDown 转换，源文件保留 |

上游参考：
- [yt-dlp 支持站点列表](https://github.com/yt-dlp/yt-dlp/blob/master/supportedsites.md)
- [yt-dlp Bilibili 提取器](https://github.com/yt-dlp/yt-dlp/blob/master/yt_dlp/extractor/bilibili.py)
- [F2 项目](https://github.com/Johnserf-Seed/f2)

上游支持不等于本项目支持。每个平台必须通过实际链接和端到端测试后，才能标记为已接入。

## 统一适配约定

1. 平台适配器负责 URL / 账号解析、内容列表分页、元数据提取和媒体下载。
2. 标准任务标识包含 `platform`、`content_id`、`source_url`、`title`、`description`、`author` 和媒体文件信息。
3. 视频处理器负责 ASR、视频帧 OCR、繁简转换、标点恢复和段落整理。
4. 图片处理器负责图文笔记图片 OCR；不能用视频帧 OCR 冒充图片 OCR。
5. Markdown 输出必须保留原始链接和来源元数据。
6. 状态唯一键为 `platform + content_id`，防止跨平台作品 ID 冲突。
7. 下载和处理始终逐项执行，统一使用磁盘保护和安全删除规则。

## Bilibili 处理建议

本轮按用户要求验证既有 ASR，全部媒体使用 faster-whisper。字幕优先作为后续能力，尚未实现，不将字幕提取结果计作 ASR。

## 当前代码边界

- Douyin 已完成接入。Bilibili 适配器已实现，真实空间访问被站点拒绝（-352），尚未完成端到端验收。
- 文件目录输入是通用处理入口，不代表已经接入新的社交平台。
- 小红书图文需要独立图片采集和 OCR。
- 不能只修改 README 就把平台标记为已支持。
