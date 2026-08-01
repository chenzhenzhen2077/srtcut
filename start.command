#!/bin/bash

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$PROJECT_DIR"

printf '\nSRT Cutter - 本地启动器\n\n'

if ! command -v python3 >/dev/null 2>&1; then
  echo "未找到 Python 3。请先安装 Python 3.10 或更高版本："
  echo "https://www.python.org/downloads/macos/"
  read -r -p "按回车退出..." _
  exit 1
fi

if ! python3 - <<'PY'
import sys
raise SystemExit(0 if sys.version_info >= (3, 10) else 1)
PY
then
  echo "当前 Python 版本过低，请安装 Python 3.10 或更高版本。"
  read -r -p "按回车退出..." _
  exit 1
fi

VENV_DIR="$PROJECT_DIR/.venv"
PYTHON="$VENV_DIR/bin/python"

if [ ! -x "$PYTHON" ]; then
  echo "首次运行：创建 Python 环境..."
  python3 -m venv "$VENV_DIR"
fi

if ! "$PYTHON" -c "import flask, faster_whisper" >/dev/null 2>&1; then
  echo "首次运行：安装项目依赖，可能需要几分钟..."
  "$PYTHON" -m pip install --upgrade pip
  "$PYTHON" -m pip install -e '.[speech]'
fi

if [ -f "$PROJECT_DIR/.env" ]; then
  set -a
  # shellcheck disable=SC1091
  . "$PROJECT_DIR/.env"
  set +a
fi

mkdir -p "$PROJECT_DIR/work" "$PROJECT_DIR/bin"

if curl --silent --fail --max-time 2 http://127.0.0.1:8964/health >/dev/null 2>&1; then
  echo "SRT Cutter 已经在运行，正在打开页面..."
  open "http://127.0.0.1:8964/"
  exit 0
fi

echo "正在启动本地服务..."
"$PYTHON" app.py >"$PROJECT_DIR/work/server.log" 2>&1 &
SERVER_PID=$!
trap 'kill "$SERVER_PID" 2>/dev/null || true' EXIT

for _ in {1..30}; do
  if curl --silent --fail --max-time 2 http://127.0.0.1:8964/health >/dev/null 2>&1; then
    echo "服务已启动，正在打开页面..."
    open "http://127.0.0.1:8964/"
    echo ""
    echo "关闭这个终端窗口即可停止服务。日志：work/server.log"
    wait "$SERVER_PID"
    exit 0
  fi
  sleep 1
done

echo "服务启动失败，最近的日志如下："
tail -40 "$PROJECT_DIR/work/server.log" || true
read -r -p "按回车退出..." _
exit 1
