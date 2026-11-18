# Social2MD 平台支持与接入边界

## 项目定位

Social2MD 将社交平台的视频、图文笔记、原始描述和识别文本归档为 Markdown。项目名不绑定某一个平台；平台差异由独立采集适配器处理。

## 当前支持矩阵

| 平台 | 内容类型 | 当前状态 | 备注 |
|---|---|---|---|
| Douyin（抖音） | 主页视频、单条视频 | 已接入 | 当前使用 F2 Douyin API；本地和云端处理链已存在 |
| Bilibili | 单条视频、UP 主空间视频 | 尚未集成 | yt-dlp 上游包含视频和空间列表提取器；仍需集成登录态、分页、元数据、下载与验收 |
| Xiaohongshu（小红书） | 视频笔记 | 尚未集成 | yt-dlp 上游列出 XiaoHongShu 提取器；需对真实分享链接、Cookie 和下载结果进行验证 |
| Xiaohongshu（小红书） | 图文笔记 | 尚未集成 | 需要单独解析笔记正文与图片列表、下载图片，并新增图片 OCR；当前视频帧 OCR 不能替代图片 OCR |

上游参考：
- [yt-dlp 支持站点列表](https://github.com/yt-dlp/yt-dlp/blob/master/supportedsites.md)
- [yt-dlp Bilibili 提取器](https://github.com/yt-dlp/yt-dlp/blob/master/yt_dlp/extractor/bilibili.py)
- [F2 项目](https://github.com/Johnserf-Seed/f2)

上游支持不等于本项目支持。网站可能调整接口、登录要求和反爬策略；每个平台都必须通过真实链接和端到端测试后，才能在支持矩阵中标记为已接入。

## 建议的统一处理架构

1. **Platform adapter**：识别 URL、解析账号/作品列表、分页、提取元数据、下载视频或图片。
2. **Normalized content**：统一保存 platform、content_id、source_url、title、description、author、published_at、media_files 等字段。
3. **Media processors**：
   - 视频音轨 → ASR；
   - 视频画面 → 抽帧 OCR；
   - 图文笔记图片 → 图片 OCR（待实现）；
   - 原始标题、正文、话题和作者信息保留为来源元数据。
4. **Markdown writer**：按平台、作者和内容 ID 生成独立 Markdown，保留原始链接和媒体引用。
5. **State and storage guard**：使用 platform + content_id 作为唯一键；继续复用断点续跑、逐个处理、磁盘阈值暂停和成功后清理媒体的机制。

## 当前代码边界

- douyin2txt.py 和 cloud_runner.py 仍是 Douyin 专用入口，保留其平台名称是为了准确表达实际实现，不能仅通过改文件名就宣称支持其他平台。
- video2txt.py、ASR/OCR 处理、文本规范化和 Markdown 输出可作为其他视频平台的公共处理基础。
- 小红书图文笔记需要图片媒体处理，不应伪装成视频 OCR。
- Bilibili 字幕若可获取，应优先保留原字幕；无可用字幕时再运行本地 ASR，并记录文本来源。
