# AGENTS.md

本仓库项目名为 **Social2MD**，定位为多平台社交视频与图文内容归档工具，目标是把内容、原始描述、媒体和识别文本统一整理为 Markdown。

**当前真实实现范围：** 已接入 Douyin 主页作品下载与云端批处理；Bilibili、小红书尚未接入。视频 ASR、视频帧 OCR、文本清洗和 Markdown 输出属于可复用处理能力。不要把当前 Douyin 专用下载代码描述成通用平台支持。

平台接入应遵循：平台适配器负责 URL/账号解析、内容列表分页、元数据和媒体下载；公共处理层负责视频 ASR、视频帧 OCR、图片 OCR、文本规范化和 Markdown 输出；状态记录必须使用 platform + content_id，避免不同平台 ID 冲突。

## 环境

- Python 3.10+（云端建议 3.11/3.12），Linux
- 系统依赖：`ffmpeg`、`ffprobe`
- 安装：

```bash
bash scripts/setup.sh
```

只装依赖不跑脚本时：

```bash
pip install -r requirements.txt
# OCR / doc2md 需要时再装：
pip install -r requirements-optional.txt
```

## 入口

| 文件 | 用途 |
|------|------|
| `douyin2txt.py` | 当前 Douyin 适配器与 CLI：下载抖音主页视频 → 转录/OCR → Markdown |
| `video2txt.py` | 本地目录视频 → 逐个转 `.txt` |
| `doc2md.py` | 本地文档 → Markdown（依赖 markitdown） |
| `cloud_runner.py` | 当前 Douyin 云端运行器：小批量获取作品、逐个下载转录、磁盘保护与断点恢复 |
| `cloud_state.py` | 云端作品状态和分页游标持久化 |
| `storage_guard.py` | 多目录文件系统、空间和 inode 保护 |

常用命令：

```bash
python douyin2txt.py --help
python video2txt.py --help
python doc2md.py --help
python cloud_runner.py --help
python -m unittest discover -s tests -v

# 只处理已下载视频，不联网下载
python douyin2txt.py -b 测试 --skip-download

# 只修复已有 md 的繁简/标点/分段（幂等）
python douyin2txt.py -b 博主名 --repair-docs
```

## 验证

修改代码后至少执行：

```bash
python -m py_compile douyin2txt.py video2txt.py doc2md.py cloud_runner.py cloud_state.py storage_guard.py
python -m unittest discover -s tests -v
python douyin2txt.py --help >/dev/null
```

自动化测试和环境初始化阶段禁止真实下载。当前 cloud_runner.py 仅支持 Douyin；只有用户明确授权后才可执行真实下载。不得在测试中使用真实 Cookie。新增平台必须先实现独立适配器并完成端到端验收，不得直接复用 Douyin API。

## 目录约定

- `output/<博主名>/<运行日期>/`：Markdown 成品，按博主和批次分目录
- `videos/<博主名>/`：视频缓存；云端入口仅在转录校验成功且质量合格后删除
- `state/`：云端作品状态、分页游标和暂停信息
- `exports/`：只包含 Markdown 的检查点 ZIP
- `models/sherpa-onnx-punct-ct-transformer-zh-en-vocab272727-2024-04-12/`：可选标点模型，
  缺失时自动退化为按停顿补句号
- 以上目录及 `*.db`、`logs/` 均不入库

## 约束

- 不要提交 `douyin_cookie.yaml`、`*.db`、`*.sqlite3*`、`output/`、`videos/`、`models/`、`logs/`、`state/`、`exports/` 等数据或凭证
- 不要新增重型依赖；OCR/markitdown 保持可选，缺失时应能正常运行核心流程
- 保持现有 CLI 参数兼容：`-u/-b/-c`、`--skip-download`、`--repair-docs`、`--clean-videos`
- 转录输出必须保持：繁转简、补中文标点、按停顿分段
- 代码注释使用中文
