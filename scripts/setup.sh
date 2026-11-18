#!/usr/bin/env bash
# 一次性环境安装脚本：可在本地或 Codex Cloud 的 setup 阶段执行
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

python3 -m py_compile douyin2txt.py video2txt.py doc2md.py cloud_runner.py cloud_state.py storage_guard.py
python3 cloud_runner.py --help >/dev/null
python3 -m unittest discover -s tests -v
python3 douyin2txt.py --help >/dev/null
python3 video2txt.py --help >/dev/null
python3 doc2md.py --help >/dev/null

echo "环境安装完成。OCR/doc2md 可选依赖：pip install -r requirements-optional.txt"
