# douyin2md — 抖音视频批量转文案工具

给一个抖音主页链接，自动把该号**全部作品**下载下来，提取**文案文字**，存成 Markdown。转录完成后视频默认保留在工程内 `videos/`，校验无误后用 `--clean-videos` 清理。

支持两种提取模式：

| 模式 | 适用 | 提取内容 |
|------|------|----------|
| **语音模式**（默认） | 口播/讲解类视频 | faster-whisper 本地 ASR 转录语音 |
| **OCR 模式**（`--ocr`） | 文字卡/金句/图文轮播视频 | 抽帧 + easyocr 识别画面文字 |

---

## 功能

- 📥 **批量下载**：用 [f2](https://github.com/Johnserf-Seed/f2) 抓取主页全部作品（mp4 + 原文案）
- 📝 **标题当文件名**：每个视频产出一个同名 `.md`
- 🎙️ **语音转文字**：faster-whisper 本地 CPU 转录（无需 GPU、无需联网 API）
- 🖼️ **画面转文字**（OCR 模式）：定时抽帧 → 感知哈希去重 → easyocr 识别
- 🖼️ **关键帧导出**：可把视频里的地图/战线图/图表按间隔抽成 jpg，自动去重
- 🗑️ **校验后清理**：转完默认保留视频便于对照，`--clean-videos` 一键清理；`--delete-video` 可恢复转完即删
- 🇨🇳 **简体输出**：自动 OpenCC 繁转简，并按停顿补标点、分段
- ⏭️ **断点续跑**：已存在的 md 自动跳过，`--force` 可强制重做

---

## 安装

```bash
git clone <你的仓库地址> douyin2md
cd douyin2md
bash scripts/setup.sh
```

`setup.sh` 会安装 ffmpeg（Debian/Ubuntu）、Python 依赖，并跑一遍 CLI 自检。也可手动安装：

```bash
pip install -r requirements.txt
pip install -r requirements-optional.txt   # OCR 模式 / doc2md.py 才需要
```

> 需要 ffmpeg（抽音频/抽帧），并能在命令行直接调用。

## 云端 Codex

仓库已带 `AGENTS.md` 和 `scripts/setup.sh`，可直接接入 Codex Cloud：

1. 推送仓库到 GitHub，在 Codex 中连接该仓库；
2. 环境 setup 命令填 `bash scripts/setup.sh`；
3. 环境安装和自动化测试阶段不要执行真实下载；原有脚本可用 `--skip-download` 验证本地视频。
4. 用户明确授权真实下载后，使用新增的 cloud_runner.py，不要把 Cookie 写进代码或任务提示词。


## 云端批量处理（逐个转录）

新增的云端入口为 cloud_runner.py，不改变原有 douyin2txt.py 的使用方式。

在 Codex Cloud 的安全环境变量中配置 DOUYIN_COOKIE，勿把 Cookie 写进任务提示词、命令参数、日志或 GitHub。也可以使用被 .gitignore 忽略的 douyin_cookie.yaml，但云端优先推荐 Secret 环境变量。

先执行：

~~~bash
python cloud_runner.py --help
python cloud_runner.py -u "主页链接" -b "博主名" --batch-size 30 --max-items 30
~~~

首次建议先处理 30 个作品验证端到端流程。确认结果正确后，再去掉 --max-items 30 执行完整扫描。

默认策略：

- 每批最多获取 30 个作品元数据，**不是同时缓存 30 个视频**；每次只下载、转录和校验一个视频，成功后删除。
- 每个作品单独下载、校验、转录和写入 Markdown。
- 同一时刻只运行一个视频转录任务。
- Markdown 内容有效且 Whisper 质量指标未触发复核阈值后，才删除视频。
- 空转录、异常、损坏视频和低置信度作品保留原视频。
- 以作品 ID 保存状态和分页游标，异常退出后可恢复。
- 磁盘使用率达到 95% 暂停，低于 90% 才允许恢复，并至少保留 1 GiB 空间。
- 扫描完成后如需检查新作品，使用 --refresh；已完成作品仍按作品 ID 去重。

输出目录：

- 视频缓存：videos/
- Markdown：output/
- 断点状态：state/
- Markdown 检查点 ZIP：exports/

ZIP 只包含 Markdown，不包含视频、Cookie、模型和运行数据库。云端工作目录可能是临时环境，重要 ZIP 应在任务结束前导出到用户可持久保存的位置。

## 配置 cookie

f2 下载需要登录 cookie。复制 `douyin_cookie.example.yaml` 为 `douyin_cookie.yaml`，
把 `cookie:` 字段填成你自己浏览器登录抖音后的 cookie 字符串（F12 → 网络 → 任意请求 → 请求头里的 Cookie）。

> ⚠️ `douyin_cookie.yaml` 含账号凭证，已在 `.gitignore` 中忽略，**切勿提交**。

---

## 使用方法

### 1. 语音模式（口播类视频）

```bash
python douyin2txt.py \
  -u "https://www.douyin.com/user/MS4wLjABAAAA..." \
  -b "暴躁桃姐" \
  -c douyin_cookie.yaml \
  --model small --language zh
```

默认输出到 `output/<博主名>/<运行日期>/`，视频缓存在 `videos/<博主名>/`。

### 2. OCR 模式（文字卡/金句视频）

```bash
python douyin2txt.py \
  -u "https://www.douyin.com/user/MS4wLjABAAAA..." \
  -b "文字卡博主" \
  --ocr --frame-interval 3
```

### 参数说明

| 参数 | 说明 | 默认 |
|------|------|------|
| `-u, --url` | 抖音主页链接（含 sec_uid） | 必填（除非 `--skip-download`） |
| `-b, --blogger` | 博主名，用于分目录 | `未分类` |
| `-c, --config` | f2 配置文件（含 cookie） | `douyin_cookie.yaml` |
| `--download-dir` | 视频缓存目录（转完默认保留） | `videos/<博主名>` |
| `--out-dir` | 最终 md 输出目录 | `output/<博主名>/<日期>` |
| `--model` | ASR 模型 `tiny/base/small/medium/large-v3` | `small` |
| `--language` | 转录语言 | `zh` |
| `--ocr` | 开启 OCR 画面识别模式（代替语音） | 关 |
| `--frame-interval` | OCR/关键帧抽帧间隔（秒） | `3` |
| `--save-frames` | 转录同时导出关键帧图片 | 关 |
| `--frames-only` | 不转录，只对已下载视频导出关键帧 | 关 |
| `--max-frames` | 每个视频最多导出几张关键帧 | `12` |
| `--skip-download` | 跳过下载，只处理已下好的视频 | 关 |
| `--delete-video` | 转完立即删除视频（默认保留） | 关 |
| `--clean-videos` | 校验完成后清理缓存视频 | 关 |
| `--repair-docs` | 只修复已有 md（繁转简、补标点、分段） | 关 |
| `--force` | 覆盖已存在的 md | 关 |

### 转简体与标点（自动）

转录结果会自动繁转简、补标点、按停顿分段，无需再手动跑 opencc。存量 md 可用 `--repair-docs` 就地修复。

---

## 输出格式

每个视频一个 `.md`：

```markdown
# 视频标题

## 原文案
（抖音帖子的文字描述）

## 口播转录        ← 语音模式
（语音识别的全文）

## 画面文字        ← OCR 模式
（识别出的画面文字）
```

---

## 小贴士

- **同名标题冲突**：有些号每条视频标题都一样，按标题命名会互相覆盖导致丢视频。
  把配置里 `naming` 改成 `"{aweme_id}_{desc}"`（用作品ID区分）即可拿全。OCR 示例配置已这么做。
- **主页链接**：必须是带 `sec_uid`（`MS4wLj...` 那串）的完整主页链接，纯抖音号不行。
  可用分享短链 `https://v.douyin.com/xxx` 跳转后拿到。
- **翻页等待**：f2 每翻一页会强制等待约 30 秒，作品多的号下载阶段需要耐心，不要以为它卡死。
- **ffmpeg 中文路径**：工具内部已处理（复制成临时 ASCII 名再调用 ffmpeg），无需担心 `#`/emoji/中文文件名。

## 依赖

- [f2](https://github.com/Johnserf-Seed/f2) — 抖音下载
- [faster-whisper](https://github.com/SYSTRAN/faster-whisper) — 本地 ASR
- [easyocr](https://github.com/JaidedAI/EasyOCR) — 画面文字识别
- [opencc](https://github.com/yichen0831/opencc-python) — 繁简转换
- [sherpa-onnx](https://github.com/k2-fsa/sherpa-onnx) — 中文标点恢复
- [markitdown](https://github.com/microsoft/markitdown) — `doc2md.py` 文档转换
- ffmpeg — 音视频处理

---

## 说明

本项目基于开源项目 [hi5jeff/douyinzhengliu](https://github.com/hi5jeff/douyinzhengliu) 修改，
原项目未附带许可证；本仓库仅做个人使用向的整理与增强，版权归原作者所有。
