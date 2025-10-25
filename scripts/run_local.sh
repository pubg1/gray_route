#!/usr/bin/env bash
set -euo pipefail

# 配置
APP_NAME="codex-gray-route"
HOST="0.0.0.0"
PORT="8080"

# 兼容任意工作目录执行脚本
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$ROOT_DIR"

PID_FILE="$ROOT_DIR/logs/${APP_NAME}.pid"
LOG_FILE="$ROOT_DIR/logs/${APP_NAME}.log"
ERROR_LOG_FILE="$ROOT_DIR/logs/${APP_NAME}.error.log"

# 创建日志目录
mkdir -p logs

# 激活虚拟环境
VENV_ACTIVATE="$ROOT_DIR/.venv/bin/activate"
if [ ! -f "$VENV_ACTIVATE" ]; then
    echo "❌ 未找到虚拟环境: $VENV_ACTIVATE"
    echo "   请先执行以下命令完成环境初始化："
    echo "     python -m venv .venv"
    echo "     source .venv/bin/activate"
    if [ -f "$ROOT_DIR/requirements.txt" ]; then
        echo "     pip install -r requirements.txt"
    elif [ -f "$ROOT_DIR/requirements-macos.txt" ]; then
        echo "     pip install -r requirements-macos.txt"
    fi
    exit 1
fi

source "$VENV_ACTIVATE"
export PYTHONUNBUFFERED=1

# 检查是否已经在运行
if [ -f "$PID_FILE" ]; then
    PID=$(cat "$PID_FILE")
    if ps -p "$PID" > /dev/null 2>&1; then
        echo "❌ 服务已经在运行 (PID: $PID)"
        echo "   如需重启，请先运行: ./scripts/stop_local.sh"
        exit 1
    else
        echo "⚠️  发现过期的PID文件，正在清理..."
        rm -f "$PID_FILE"
    fi
fi

# 启动服务
echo "🚀 启动 $APP_NAME 服务..."
echo "   地址: http://$HOST:$PORT"
echo "   日志: $LOG_FILE"
echo "   错误日志: $ERROR_LOG_FILE"
echo "   PID文件: $PID_FILE"
if command -v git >/dev/null 2>&1 && git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    CURRENT_COMMIT=$(git rev-parse --short HEAD 2>/dev/null || echo "unknown")
    echo "   当前提交: $CURRENT_COMMIT"
    if ! git diff --quiet --ignore-submodules HEAD 2>/dev/null; then
        echo "   ⚠️ 检测到工作区存在未提交的更改，将以本地修改版本启动服务。"
    fi
fi

# 后台启动服务
nohup uvicorn app.main:app \
    --host "$HOST" \
    --port "$PORT" \
    --log-level info \
    > "$LOG_FILE" 2> "$ERROR_LOG_FILE" &

# 保存PID
echo $! > "$PID_FILE"
PID=$(cat "$PID_FILE")

# 等待服务启动
sleep 2

# 检查服务是否成功启动
if ps -p "$PID" > /dev/null 2>&1; then
    echo "✅ 服务启动成功!"
    echo "   PID: $PID"
    echo "   状态检查: curl http://$HOST:$PORT/health"
    echo "   查看日志: tail -f $LOG_FILE"
    echo "   停止服务: ./scripts/stop_local.sh"
else
    echo "❌ 服务启动失败"
    echo "   请检查错误日志: cat $ERROR_LOG_FILE"
    rm -f "$PID_FILE"
    exit 1
fi
