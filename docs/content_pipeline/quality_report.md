# Social2MD 内容加工试验质量报告

## 当前范围与迁移说明

本试验最初从仓库归档中选取三位 UP 主各一篇样本：硬件术语、求职方法和长篇游戏剧情解读。第三篇《赛博朋克 2077》样本已整体迁移至 [Book Relay 游戏专区](https://github.com/Crazypsy92/book-relay/tree/main/games/赛博朋克2077)，其 ASR 状态与处理记录见[转录加工试验记录](https://github.com/Crazypsy92/book-relay/blob/main/games/%E8%B5%9B%E5%8D%9A%E6%9C%8B%E5%85%8B2077/%E5%8E%9F%E5%A7%8B%E6%9D%90%E6%96%99/%E5%A4%84%E7%90%86%E8%AE%B0%E5%BD%95/03_%E8%BD%AC%E5%BD%95%E5%8A%A0%E5%B7%A5%E8%AF%95%E9%AA%8C%E8%AE%B0%E5%BD%95.md)。本报告现在只统计仍留在 Social2MD 的两个样本。

只读归档 Markdown 并生成独立产物；未下载视频、未修改源 Markdown、未触碰 SQLite 采集状态库，也未重新下载或加载 ASR 模型。

试验遵循 `Crazypsy92/unified-content-notes`，读取版本为 `4fc18fcda056413a0e823c557045b95a636fc683`。没有人工听音参考文本，因此不计算 CER，也不把语义顺畅或多模型一致称为音频核验。当前两个样本均为 `REVIEW_REQUIRED`，适合作为复核稿，不应视为最终纠错定稿。

## 当前样本结果

| UP 主 / BV 号 | 原文口播字符 | 候选事件 | 有充分文字证据的改字 | 已人工核音确认 | 当前状态 |
|---|---:|---:|---:|---:|---|
| 硬件何工 / BV1tqsF65Eks | 2,308 | 7 | 1（`BUG→Buck`，词典与三种独立 ASR 片段一致） | 0 | REVIEW_REQUIRED |
| 饶厂长讲传统工科求职 / BV1gR7k6EEGq | 3,523 | 1 | 0 | 0 | REVIEW_REQUIRED |
| **当前合计** | **5,831** | **8** | **1** | **0** | **2 篇待复核** |

以上“候选事件”是扫描器和样本配置产生的复核点，数量不是错误数量。当前可统计为：确认正确校订 0、确认错误校订 0、确认遗漏 0；这是因为本轮没有人工逐句核音，不能据此推断原 ASR 无错或修改必然正确。1 处文字证据校订明确带有 `audio_verified: false`，原文备份和差异记录均保留。

### 复核重点

- **硬件何工**：`BUG→Buck` 有词典及 Whisper、FunASR、Qwen3-ASR 三份独立片段文本支持，但尚未听音；“扫走一年网络/少走一年弯路”及 `文博→纹波`、`DCDC→DC-DC` 均留作候选，没有擅自改写。当前归档样本自身未发现 U+FFFD。
- **饶厂长**：`电极控制工程师→电机控制工程师` 只凭语境提出，视频虽在本地，但本轮没有核听，因此保留“听辨存疑”标记。
- 《赛博朋克 2077》历史样本不再属于本仓库的加工队列；其 42,335 字符、13 个重复片段候选、0 处改字和未人工核音状态已单独归档在 Book Relay，不在此重复展开。

## 保真与格式检查

- 当前两份 `raw/` 备份与各自归档来源逐字节相同，SHA-256 与 `processed_items.json` 中的来源哈希一致。
- 当前源归档没有发生改动；校订稿只添加候选标记及一处有文字证据、但未核听的词形修改，没有删除原文字符。
- 两篇均保留来源链接和作者信息；机器清单以 `(platform, content_id)` 去重，文件按作者和标题命名。
- 两篇 Obsidian 笔记均通过 Unified Content Notes 所附 Callout 静态检查器。静态检查不等于 Obsidian 应用内渲染验收。
- 当前两篇均有独立校订稿、原文副本、候选 JSON、差异 JSON 和 Obsidian 笔记；正文保留完整转录，摘要明确区分讲者观点与独立事实核验。
- `py_compile` 通过；项目单元测试 41 项通过、1 项跳过（环境未安装 faster-whisper，跳过的为已安装音频解码器兼容性检查）。

## 归档差异说明

旧版 `docs/asr01_problem_analysis.md` 记载 ASR-01 第 2 篇曾有 2 个 U+FFFD，定位到旧运行目录中的 `output/bilibili_archive/BV1tqsF65Eks.md`。本次仓库内对应归档 `硬件何工/得电源者，得硬件.md` 检测到 0 个 U+FFFD。旧运行文件当前不在工作区可核对，故将其作为历史报告与当前归档版本之间的差异记录，不把“2 个乱码”计入本轮样本问题数。

## 可复用队列与调度

迁移前扫描快照检查了 91 篇归档，其中 9 篇《赛博朋克 2077》材料已迁出；当前 `progress.json` 保留 82 篇仍在 Social2MD 的扫描记录。常规计划每轮上限为 3 篇；口播字符数达到 10,000 的文章单独列队。重复运行会按来源哈希跳过已有结果，变化的源文件进入 `SOURCE_CHANGED`，锁冲突或处理失败不会删除材料。迁移后已从 `progress.json`、`next_batch.json`、`processed_items.json` 和 `samples.json` 中清除 2077 队列项，避免后续加工任务引用已迁出的文件。

云端交互 shell 可能暂停，不适合作为常驻定时器。本轮已手动完成扫描、计划和样本加工，但没有创建定时任务。若仓库设置允许 GitHub Actions 定时任务，可在确认私有仓库计划任务权限和额度后，用 `schedule` 加 `workflow_dispatch` 运行扫描/计划，设置 `concurrency` 并只给必要的 `contents` 写权限；未经人工维护的笔记摘要仍不会自动生成或发布。

## 产物索引

- [加工规则与使用说明](README.md)
- [样本与摘要配置](samples.json)
- [机器可读处理清单](processed_items.json)
- [归档扫描进度](progress.json)
- [下一批计划](next_batch.json)
- 当前样本输出位于同目录的 `raw/`、`corrected/`、`obsidian/`、`candidates/` 和 `diffs/` 子目录。
- 已迁出的游戏专题材料统一见 [Book Relay 游戏专区](https://github.com/Crazypsy92/book-relay/tree/main/games/赛博朋克2077)。

## 阶段结论

**当前保留样本的工程与格式试验：通过。内容准确性验收：尚未通过，需人工核听后再定稿。** 原文保真、来源记录、候选差异追溯、Callout 静态格式、幂等状态和推送冲突保护均纳入本轮验收；但当前 8 个候选事件尚未完成听音复核，因此不声称 ASR 准确率提升，也不建议直接把两篇标成“已纠错”。
