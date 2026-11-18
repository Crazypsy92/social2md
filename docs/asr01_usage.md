# ASR-01 实验与审计使用说明

默认视频处理仍使用 faster-whisper。新增 ASR 对照通过统一入口的 `--asr-audit` 启用，所有模型按子进程运行，每个引擎结束后释放模型。原视频只读，实验输出目录必须为新目录，不能覆盖已有 Markdown 或实验目录。生产 SQLite 不参与实验写入。

## 可选依赖

建议新建独立虚拟环境，核心环境保留 PyAV 16.x 和原 requirements.txt。安装示例适用于当前云环境。

```bash
python3 -m venv /workspace/.venvs/asr01
/workspace/.venvs/asr01/bin/python -m pip install torch torchaudio --index-url https://download.pytorch.org/whl/cpu
/workspace/.venvs/asr01/bin/python -m pip install -r requirements-asr-audit.txt
```

核心环境的命令仍使用 `/workspace/.venvs/social2md/bin/python`。依赖和模型均延迟加载，默认流水线不导入 FunASR、Qwen 或 pycorrector。可选模型失败时记录 UNAVAILABLE；超时记录 TIMEOUT，已经生成的 Whisper 证据继续保留。

模型由官方 Hugging Face 仓库下载，缓存目录通过 `--audit-cache` 设置。权重不提交 Git。Qwen 使用 0.6B，CPU float32、批次 1；额外的强制对齐模型未加载，时间范围来自共同音频片段。Paraformer 请求 pred_timestamp，实际是否返回词级时间戳需要检查模型结果，不能只据请求参数判定支持。

## 运行

先选定 4 篇视频，可在独立输入目录建立源视频软链接。已知问题视频和术语视频优先，其他两篇作为对照。输入按文件名排序，默认取前 4 个。

```bash
/workspace/.venvs/social2md/bin/python social2md.py \
  --input-dir state/asr01/selected --asr-audit \
  --audit-output output/asr01_new_run \
  --audit-python /workspace/.venvs/asr01/bin/python \
  --audit-cache /workspace/.cache/asr01 \
  --audit-terms docs/asr_terms.example.json \
  --audit-limit 4 --audit-seconds 30 --audit-full
```

省略 audit-full 可先做每篇前 30 秒的运行验证。开启后将选中视频全长切为 30 秒单声道 16k PCM，所有 ASR 对同一批 WAV 进行识别。Qwen 作为资源评估候选，仅处理每篇首段，完整音频比较由 Whisper 和 Paraformer 执行。冷启动下载和热缓存耗时需分别看待。

词典是用户维护的 JSON 数组，每项包含 term 和 aliases，示例见 asr_terms.example.json。term 用于 Whisper initial_prompt 和 Paraformer hotword；aliases 只产生候选提示。词典不会触发无证据的文本替换。

## 查看结果

- source_hashes.json 保留源文件摘要，clips.json 记录共同音频及时间范围。
- whisper.json、funasr.json、qwen.json 保存原始识别、模型版本、参数、运行时间和峰值内存。
- pycorrector.json 保存辅助纠错候选。MacBERT 结果属于文本模型建议，需要音频或独立 ASR 支持。
- comparison.json 保存片段原文、第二和第三模型文本、差异、候选修改与 REVIEW_REQUIRED 状态。
- review_md 保存按片段标记待核的可读实验稿，语义原文保持可追溯。
- 独立日志用于诊断下载、模型或依赖错误。输出均保存在实验目录。

原始 Whisper 内容作为最终文本基线。当前实现采用保守策略，不自动应用任何语义纠错；不同模型存在内容差异、乱码、异常重复、词典可疑别名或低置信度时进入待复核。模型一致只能证明识别一致，不能用作人工参考文本来计算 CER。原生产 Markdown 保持可追溯，实验结果不会写回生产作品状态。

## 当前限制

旧 Markdown 没有保存逐段时间戳，原有 quality 只保存聚合指标及一个最差片段摘要。因此旧问题位置可能只能标为待定位，新实验通过分块时间范围和原始分段数据补充证据。

未提供人工核验参考文本时，CER 保持空值。同音词、术语和漏句的真实错误数量也需要人工参考或复听确认。模型之间的差异数量不能解释为错误数量或准确率提升。

## 热词模型的区别

Hugging Face 的 funasr/paraformer-zh 是普通 Paraformer，最初短片段实验验证了 CPU 识别，但该实现未消费 hotword 参数。当前实验适配器使用 FunASR 官方 ModelScope 别名 paraformer-zh，对应 iic 发布的 SeACo Paraformer 热词模型。模型 ID 和 hub 的差别必须记录，不能将普通模型接受未知参数视作热词能力已验证。模型权重约 990 MB，使用官方 SDK 的 MODELSCOPE_DOWNLOAD_PARALLELS=4 并行下载，并保持校验机制。
