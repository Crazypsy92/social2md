#!/usr/bin/env bash
# 统一流水线环境初始化：安装核心依赖、编译并运行无网络单元测试。
set -euo pipefail
cd "$(dirname "$0")/.."

install_ffmpeg() {
  command -v ffmpeg >/dev/null 2>&1 && return
  if command -v apt-get >/dev/null 2>&1; then
    if [ "$(id -u)" -eq 0 ]; then
      apt-get update && apt-get install -y ffmpeg
    else
      sudo apt-get update && sudo apt-get install -y ffmpeg
    fi
  else
    echo "未检测到 ffmpeg，请先手动安装后再运行" >&2
    exit 1
  fi
}

install_ffmpeg
python3 -m pip install --upgrade pip
python3 -m pip install -r requirements.txt
python3 -m py_compile social2md.py social2md_app/*.py
python3 social2md.py --help >/dev/null
python3 -m unittest discover -s tests -v

echo "核心环境初始化完成。OCR / 文档转换可选依赖：pip install -r requirements-optional.txt"
