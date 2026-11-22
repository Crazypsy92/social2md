# Social2MD 归档内容加工试验

本试验把 GitHub 工作区内已有的 Bilibili Markdown 归档作为只读输入，生成独立的 ASR 校订阅读版、差异记录、Obsidian 笔记和处理清单。原归档文件、视频以及 Social2MD 采集 SQLite 均不写入。

## 规范来源与加工边界

本试验遵循 `Crazypsy92/unified-content-notes` 的 `SKILL.md`、动作/结构/文体路由、来源边界、观点分析、ASR transcript-cleanup、质量检查和 Obsidian 观点分析 Callout 规范（读取版本：`4fc18fcda056413a0e823c557045b95a636fc683`）。试验只实现可确定的扫描、校订标记、摘要模板渲染和 Obsidian 静态检查；不会把技能说明本身当作可核听音频的模型。

词语修改规则：只有用户术语词典中的明确别名，加上至少两个独立 ASR 输出一致支持，且配置中逐条记下模型/片段/原始输出，才允许生成文字证据支持的词形改动。这个状态仍写 `audio_verified: false`。音频未人工核听时，人物名、数字、专有名词、不同 ASR 意见、疑似漏句和重复片段均保留并标为“听辨存疑”。词典候选、上下文通顺度、游戏/视频标题都不等于音频真值。

## 本轮三篇样本

| UP 主 | 作品 | 路由 | 特别处理 |
|---|---|---|---|
| 硬件何工 | 得电源者，得硬件 | 观点论证 + 工程技术经验 | 复用 ASR-01 对照与词典；仅 `BUG→Buck` 有三种独立 ASR 与词典共同支持，记录为未核听的文本证据校订 |
| 饶厂长讲传统工科求职 | 没有实习没有竞赛，三个月照样进大厂 | 观点论证 + 方法经验 | “电极控制工程师→电机控制工程师”仅列候选，不自动替换 |
| 幻灵Kuri | 赛博朋克 2077 终极解读 03 | 超长观点论证 + 游戏剧情叙述 | 42,335 字符，单独处理；重复片段只标记，不擅自删句 |

`raw/` 是源 Markdown 的字节级副本；其 SHA-256 同时记录在 `processed_items.json`。`corrected/` 是独立校订阅读版；`obsidian/` 是 Callout 笔记；`candidates/`、`diffs/` 保留候选、证据和改动记录。全部输出名称以作者目录和文章标题组织，BV 号只放在机器清单及来源链接中。

## 目录与状态

- `samples.json`：三个试验样本的路由、人工整理摘要、候选和可用证据配置。摘要字段是本轮整理者撰写，程序不会调用在线文字模型。
- `progress.json`：91 篇归档的确定性扫描快照，含源 SHA-256、长度、候选类型和状态；只扫描、不改写文本。
- `next_batch.json`：稳定排序的下一批计划，普通文档最多 3 篇，超长（口播转录 ≥10,000 字符）单列。
- `processed_items.json`：下游软件可读取的 3 个试验作品状态。去重键是 `(platform, content_id)`。`REVIEW_REQUIRED` 表示产物已生成但候选待人工核验；不等于处理成功、纠错正确或音频已听。
- `raw/`、`corrected/`、`obsidian/`、`candidates/`、`diffs/`：本轮输出，各自独立保存。

输入文章有变化时，SHA-256 会阻止静默复用旧产物，状态记为 `SOURCE_CHANGED`。重复运行同一 SHA 且文件齐全时跳过；已存在但不同的输出拒绝覆盖。锁文件在系统临时目录，避免两个加工进程同时写相同清单。扫描/加工失败会记录状态和原因，不删除任何输入或输出。

## 手动运行

在仓库根目录：

```bash
python scripts/process_content.py scan
python scripts/process_content.py plan --max-ordinary 3
python scripts/process_content.py process-samples --max-ordinary 3
python scripts/process_content.py process-samples --max-ordinary 3 --include-long
```

最后一步会跳过前两篇已有的同哈希结果，单独处理超长样本。无待处理内容时 `plan` 正常退出。`scan` 读取当前 Git checkout 的归档文件；不直接请求 GitHub API，也不需要平台 Cookie、下载视频或加载 ASR 模型。

只有 `docs/content_pipeline/` 下存在加工结果、当前分支为 `main` 且 `HEAD` 与 `origin/main` 完全一致时，发布命令才会暂存、提交并推送；其他目录有改动或远端前进时会拒绝：

```bash
python scripts/process_content.py publish --message "Publish reviewed content notes"
```

推送失败会保留本地提交和产物，需先人工同步并检查冲突，再重试。程序不创建分支或 PR。

## 定时任务可行性

本轮已完成一次全量候选扫描和三篇手动样本渲染；尚未配置定时任务。云端交互环境可能暂停，不能把 `nohup` 当作可靠的常驻调度器。若 GitHub Actions 在仓库设置中可用于定时运行，推荐将纯文本 `scan`/`plan` 放在 `schedule` 与 `workflow_dispatch` 入口，设置 `concurrency` 防并发，固定 checkout `main`，写权限仅限 `contents`，发布前仍执行本程序的远端一致性检查。私有仓库的 Actions 计划任务是否启用、额度与权限需在 GitHub 设置中确认后再配置。

当前程序能自动扫描并计划下一批，但不会自动创作新材料的摘要：每篇 Obsidian 笔记需要经过审阅的 `samples.json` 摘要字段。定时器可以扫描、生成计划并渲染已审阅配置；未经审阅的新内容留在队列中，不会被模型无约束改写。这个限制在本试验中是有意的来源保护。
