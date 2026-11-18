# Bilibili 空间采集与本轮验收

## 当前状态

2026-11-18 已实现 Bilibili 空间及 BV/av 视频适配器，通过统一入口 social2md.py 运行。安装的 F2 0.0.1.7 未包含 Bilibili 应用模块，因此使用 yt-dlp 2026.10.26。平台适配器负责分页、元数据和下载，本地目录与 Bilibili 复用公共媒体任务函数及现有 ASR、质量阈值、SQLite、磁盘保护和 Markdown 原子写入。

本轮用户将目标改为 UP 主空间的全部视频，取消原先 30 条总数限制。实际主页、作品标题和凭证不写入此公开文档。

## 运行与恢复

在云环境中激活 `/workspace/.venvs/social2md`。配置 `HF_HOME=/workspace/.cache/huggingface` 可将模型缓存放在可写位置。安装仍使用 `bash scripts/setup.sh`。

```bash
python social2md.py -u "https://space.bilibili.com/用户ID/video" \
  -b bilibili_archive --keep-source --model small --language zh \
  --download-dir videos/bilibili_archive \
  --out-dir output/bilibili_archive \
  --state-dir state/bilibili_archive \
  --export-dir exports/bilibili_archive --dry-run
```

确认后去掉 `--dry-run`。默认 `--max-items 0` 表示不限数量。Bilibili 提取器固定每页 30 条元数据，当前不使用 `--batch-size` 修改其页大小。媒体和分 P 逐个下载、校验、转录、写入 Markdown，再处理下一个。默认调用既有 ASR，未增加字幕替代逻辑或更改模型参数。

Cookie 可通过安全环境变量 `BILIBILI_COOKIE` 注入，作用域限于 Bilibili 域名。无需配置 DOUYIN_COOKIE。不得把 Cookie 放入命令参数、聊天、报告或 Git。

恢复时重复相同命令并保留状态目录。扫描位置、作品状态、来源信息和质量指标写入 SQLite。为避免新增投稿导致分页偏移漏项，恢复会重新枚举列表，按 platform=bilibili 和分 P 标识去重。已完成且 Markdown 有效的作品跳过；待复核作品默认跳过；已下载且未完成的视频复用源文件。默认不清空数据库，不使用 force、refresh 或 retry-review。

同一来源使用文件锁防止多个任务同时写入。磁盘使用率达 95%、inode 达阈值或可用空间不足 1 GiB 时暂停，低于 90% 才恢复。下载期间及合并前后检查磁盘。媒体处理失败会保存源视频并停止后续下载，供诊断后恢复。`--keep-source` 保留成功和待复核视频。

## 验证证据

- 28 项无网络测试全部通过，包括跨多页惰性列表展开及逐项处理、分 P 独立标识、重跑去重、处理失败后从已有视频重试、磁盘暂停、来源元数据输出及 ZIP 内容校验。
- 编译和统一入口帮助检查通过。
- 使用真实 yt-dlp 下载本地 HTTP 服务上的生成视频，验证下载钩子、单流扩展名处理与 FFprobe 校验通过。该检查只验证下载组件。
- 目标空间 dry-run 通过。公开空间 API 曾返回 -799，登录态下 WBI 接口及登录 API 均工作，投稿清单共 10 条。首个 CDN 下载遇到整文件请求 403/567，使用标准 Range 分块下载成功。首个 ASR 因 PyAV 19 接口不兼容失败，安装 PyAV 16.1.0 并验证后从 SQLite 状态及本地视频恢复，无需重新下载。任务最终退出码为 0，扫描完成标志为 1，状态为 COMPLETED 10。
- 公开下载凭证配置在仓库外的权限 0600 本机文件，登录确认通过。凭证没有进入报告或 Git。更换云任务后该文件是否保留未经验证。
- 使用 yt-dlp 从本地 HTTP 服务下载生成媒体、FFprobe 检查、自动恢复模拟、ZIP 检查均通过。

## 本轮实际产物

| 项目 | 结果 |
| --- | --- |
| 可见空间投稿 | 10 条 |
| 下载视频 / FFprobe 有效 | 10 / 10 |
| ASR 成功 / 最终空转录 | 10 / 0 |
| Markdown 输出 | 10 |
| 自动阈值待复核 | 0 |
| 最终失败作品 | 0，初次下载和首个 ASR 的问题均恢复 |
| 源视频保留 | 10 / 10 |
| 断点恢复 | 实际验证，首个作品从已下载媒体恢复处理 |
| 检查点 ZIP | 通过，10 个 Markdown，与输出目录一致，无其他文件 |
| 磁盘 | dry-run 约 59.70 GiB 可用，完成约 58.46 GiB，可用空间充足 |

对前两篇 Markdown 抽查后，第 2 篇发现 2 个替换乱码字符、疑似同音词误识别和技术术语错误。当前质量阈值没有发现这些问题。其余作品已检查标题、文案、来源链接、文本非空、繁简与格式，但未逐秒对听全部音频，不能承诺逐字准确。建议人工校对第 2 篇并抽听其他作品。

空间采集范围为当前账号可见的投稿和分 P，不包含隐藏、已删除或无权限视频。本轮 10 条任务已完成。后续检查可保留 state/bilibili_archive 并使用相同运行命令。


## 运行时配置与兼容性

除 `BILIBILI_COOKIE` 外，可通过 `BILIBILI_COOKIE_FILE` 指定凭证文件。环境变量中的 Cookie 优先；文件必须由用户妥善控制权限，建议目录 0700、文件 0600，并放在 Git 仓库外。应用只读取文件，凭证不写入启动脚本正文和公开报告。本机文件配置与平台安全变量配置分别管理，新任务需确认所用凭证来源是否存在。

Bilibili CDN 对普通整文件请求可能返回 HTTP 403 或 567，下载使用 yt-dlp 的标准 Range 分块选项，每块 10 MiB。TLS 验证保持开启。

实测 faster-whisper 1.2.1 调用 PyAV 19.0.2 时，音频解码会报 `metadata_errors` 参数错误。核心依赖已限制 PyAV 为 16.x，并在 16.1.0 上验证解码。ASR 模型、推理参数和质量阈值保持原实现。
