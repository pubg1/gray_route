#!/usr/bin/env bash
set -euo pipefail

# 配置
APP_NAME="codex-gray-route"
PID_FILE="./logs/${APP_NAME}.pid"
LOG_FILE="./logs/${APP_NAME}.log"
ERROR_LOG_FILE="./logs/${APP_NAME}.error.log"

echo "🛑 停止 $APP_NAME 服务..."

# 检查PID文件是否存在
if [ ! -f "$PID_FILE" ]; then
    echo "❌ 未找到PID文件: $PID_FILE"
    echo "   服务可能未运行或已经停止"
    exit 1
fi

# 读取PID
PID=$(cat "$PID_FILE")

# 检查进程是否存在
if ! ps -p "$PID" > /dev/null 2>&1; then
    echo "⚠️  进程 $PID 不存在，清理PID文件"
    rm -f "$PID_FILE"
    echo "✅ 清理完成"
    exit 0
fi

echo "   PID: $PID"

# 尝试优雅停止 (SIGTERM)
echo "   发送 SIGTERM 信号..."
kill "$PID"

# 等待进程停止
for i in {1..10}; do
    if ! ps -p "$PID" > /dev/null 2>&1; then
        echo "✅ 服务已优雅停止"
        rm -f "$PID_FILE"
        exit 0
    fi
    echo "   等待进程停止... ($i/10)"
    sleep 1
done

# 如果优雅停止失败，强制停止 (SIGKILL)
echo "⚠️  优雅停止失败，强制停止进程..."
kill -9 "$PID" 2>/dev/null || true

# 再次检查
sleep 1
if ! ps -p "$PID" > /dev/null 2>&1; then
    echo "✅ 服务已强制停止"
    rm -f "$PID_FILE"
else
    echo "❌ 无法停止进程 $PID"
    echo "   请手动检查: ps -p $PID"
    exit 1
fi
