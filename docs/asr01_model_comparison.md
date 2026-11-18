# ASR-01 模型对照实验报告

2026-11-18，Linux CPU 云环境，内存限制 32 GiB、CPU 配额 4 核。使用独立可选依赖环境，核心 PyAV 16.1.0 与 requirements.txt 未改变。源材料为已保留的 10 个本地视频，没有重新下载平台作品。

## 样本与范围

完整比较选取原第 2 篇（已知乱码）、原第 1 篇（术语样本）、原第 3 和第 4 篇（未发现乱码的对照）。这些对照仍来自同一硬件领域 UP 主，不代表通用领域数据集。通过独立目录软链接选择原视频。四篇全长切分为 66 个最多 30 秒的 16k 单声道 PCM 音频片段，Whisper 和 Paraformer 使用完全相同的 WAV。原始路径与时间范围存于 clips.json。

Qwen3-ASR-0.6B 仅评估这四篇的前 30 秒，共 120 秒。试验中其 CPU 成本较高，未扩展为四篇全长。其余 6 篇只完成已有 Markdown 的静态检查，没有冒充全长多模型测试。

## 测量结果

时间为独立子进程的总耗时，包含导入、模型加载、可能发生的下载与识别；不能将其解释为纯推理实时率。Linux ru_maxrss 换算为 MiB。重试只重新执行失败的可选引擎。

| 引擎 | 软件版本 | 片段数 | 总耗时秒 | 峰值内存 MiB |
| --- | --- | --- | --- | --- |
| whisper | 1.2.1 | 66 | 879.2 | 1172 |
| funasr | 1.4.27 | 66 | 313.7 | 2769 |
| qwen | 0.0.6 | 4 | 112.2 | 6107 |
| pycorrector | 1.1.4 | 66 | 38.2 | 1210 |

最初使用 Hugging Face funasr/paraformer-zh 进行 4×30 秒先导实验，总耗时 39.4 秒、峰值约 2472 MiB；该普通模型的实现没有消费 hotword 参数。完整实验改用 FunASR 官方 ModelScope paraformer-zh 别名，对应 iic/speech_seaco_paraformer_large_asr_nat-zh-cn-16k-common-vocab8404-pytorch，权重下载约 990 MB。SeACo 完成 66 段 CPU 识别，66 段都返回 timestamp，并记录首段带/不带热词的 A/B 结果和实际热词列表。热词接口已验证，尚无人工参考，不能宣称热词提高了准确率。

Qwen 使用 CPU float32、批次 1、最多 1024 新 token。未安装 1.7B、4B 或强制对齐模型，时间位置使用共同片段边界。首次先导 120 秒音频加载与处理约 202.6 秒、峰值约 6179 MiB；完整实验所选四篇首段的复测见上表。

## 缓存体积

下表为 Hugging Face 缓存中去重后的实际文件占用，不等同于网络传输字节数，含权重和配置。ModelScope SeACo 权重单独约 990 MB。下载保持官方 SDK 的校验和 TLS 检查，权重未提交 Git。

| 模型缓存 | MiB |
| --- | --- |
| funasr/paraformer-zh | 848.2 |
| shibing624/macbert4csc-base-chinese | 390.3 |
| Qwen/Qwen3-ASR-0.6B | 1793.4 |
| Systran/faster-whisper-small | 463.7 |

## 候选与校对

66 段均进入 REVIEW_REQUIRED，原始 Whisper 文本保持为校对基线，自动应用语义修改为 0。检测事件统计为 {'asr_disagreement': 66, 'third_asr_disagreement': 4, 'replacement_character': 1}。差异数代表模型意见不一致，不能解释为真实错误数量。

pycorrector 使用 MacBERT 字符纠错模型 shibing624/macbert4csc-base-chinese，在每个片段生成 source、target 与 errors 候选；只保存建议。该模型缺少音频证据，流畅的候选可能错误，不能直接成为终稿。专业词典是用户可维护 JSON，用于 Whisper initial_prompt、SeACo hotword 和别名候选检测。

原始 ASR 文本、模型输出、候选差异、时间范围和质量指标存于 output/asr01_full 下的独立 JSON。review_md 提供分片段待核稿。原生产 Markdown 和 SQLite 未被这些实验覆盖。旧结果未保存逐段时间戳，旧乱码问题的位置只在问题清单中给出片段匹配候选，标明仍需复听。

## 准确率与限制

没有人工核验参考文本，CER 保持 null。同音词、技术术语、漏字和漏句的真实错误数无法定量统计，不能宣称准确率提高百分比。两个 ASR 的相同结果也不能充当人工真值。四篇实验带有词典提示且做了分块，旧整篇无词典 Markdown 与新实验之间还存在条件差异，结果不宜直接用作单变量提升结论。

## 验收结论

默认 Whisper 流程兼容，可选引擎独立加载、异常及超时可记录，已有乱码可检测，多模型差异与候选可追溯。原视频、Markdown、SQLite 摘要均核对未变。全部模型均有实际 CPU 实验。自动校订准确性仍待人工参考与复听验证，因此本阶段结论为功能验证通过、准确率提升未证实。保持第二识别器为实验可选功能，先人工核验第 2 篇及差异片段，再决定是否扩展剩余 6 篇。

参考官方来源为 [FunASR](https://github.com/modelscope/FunASR)、[Qwen3-ASR](https://github.com/QwenLM/Qwen3-ASR)、[pycorrector](https://github.com/shibing624/pycorrector)。MacBERT 借助文本上下文提供字符候选，音似错误、人名和地名的正确性仍需音频、用户词典及独立 ASR 佐证。

## 乱码与自动采纳结果

四篇完整音频合计约 31.9 分钟。原生产 Markdown 的已知替换字符为 2 个；新实验重分块并使用词典提示，条件已经发生变化。以下统计仅描述实际输出，不能将减少量归因于某个单独模块或解释为准确率提升。

| 识别器 | 实测片段数 | 原始识别替换字符 |
| --- | --- | --- |
| whisper | 66 | 1 |
| funasr | 66 | 0 |
| qwen | 4 | 0 |

自动采纳语义修改为 0，校对稿保留本次 Whisper 原文。pycorrector 的候选与模型差异独立保存，未用候选内容覆盖原生产文档。测试共 36 项通过，核心与可选环境 pip check 均通过。
