# AGENTS.md

本仓库是抖音视频批量转文字工具 **douyin2md**。给一个抖音主页链接，下载全部作品，
用本地 ASR（faster-whisper）或 OCR（easyocr）提取文字，输出 Markdown。

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
| `douyin2txt.py` | 主脚本：下载抖音主页视频 → 转录/OCR → Markdown |
| `video2txt.py` | 本地目录视频 → 逐个转 `.txt` |
| `doc2md.py` | 本地文档 → Markdown（依赖 markitdown） |
| `cloud_runner.py` | 云端小批量下载、逐个转录、磁盘保护与断点恢复 |
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

自动化测试和环境初始化阶段禁止真实下载。只有用户明确授权后，才可使用 cloud_runner.py 执行真实下载；不得在测试中使用真实 Cookie。

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
