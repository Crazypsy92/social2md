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
- 目标空间链接与磁盘 dry-run 通过。
- 真实统一入口空间运行退出码为 1。网络放行后，Bilibili WBI 接口返回站点拒绝码 -352。基础空间 API 也返回过 -799 限流响应。
- 当前没有 BILIBILI_COOKIE 配置或已有凭证绑定。需要用户安全配置登录态后重试；Cookie 不保证消除站点限制。

## 本轮实际产物

| 项目 | 结果 |
| --- | --- |
| 视频总数 | 未获取，不能推定为零 |
| 下载、有效视频、ASR、Markdown | 均为 0，真实处理未开始 |
| 空转录、低置信度 | 未执行真实识别，无法验收 |
| 源视频保护 | 没有下载到真实视频，没有执行删除 |
| 真实恢复 | 未验证，仅模拟状态恢复通过 |
| 检查点 ZIP | 未生成，无实际 Markdown 可导出 |
| 磁盘 | dry-run 时约 59.70 GiB 可用，无真实媒体增量 |

代码接入及离线测试完成，实际全部视频采集、ASR、内容抽查和 ZIP 验收仍受站点访问限制。空间采集范围为当前账号可访问的投稿与分 P，不宣称获取隐藏、已删除或无权限视频。下一步安全配置登录态并重试现有命令，恢复访问后再记录真实统计。
