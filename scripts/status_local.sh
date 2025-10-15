#!/usr/bin/env bash
set -euo pipefail

# 配置
APP_NAME="codex-gray-route"
HOST="0.0.0.0"
PORT="8080"
PID_FILE="./logs/${APP_NAME}.pid"
LOG_FILE="./logs/${APP_NAME}.log"
ERROR_LOG_FILE="./logs/${APP_NAME}.error.log"

echo "📊 $APP_NAME 服务状态"
echo "=================================="

# 检查PID文件
if [ ! -f "$PID_FILE" ]; then
    echo "🔴 状态: 未运行 (无PID文件)"
    echo "   启动服务: ./scripts/run_local.sh"
    exit 1
fi

# 读取PID
PID=$(cat "$PID_FILE")
echo "📝 PID文件: $PID_FILE"
echo "🆔 进程ID: $PID"

# 检查进程状态
if ps -p "$PID" > /dev/null 2>&1; then
    echo "🟢 进程状态: 运行中"
    
    # 获取进程信息
    if command -v ps > /dev/null 2>&1; then
        echo "⏱️  运行时间: $(ps -o etime= -p "$PID" 2>/dev/null | tr -d ' ' || echo '未知')"
        echo "💾 内存使用: $(ps -o rss= -p "$PID" 2>/dev/null | awk '{printf "%.1f MB", $1/1024}' || echo '未知')"
        echo "🖥️  CPU使用: $(ps -o %cpu= -p "$PID" 2>/dev/null | tr -d ' ' || echo '未知')%"
    fi
else
    echo "🔴 进程状态: 未运行 (PID $PID 不存在)"
    echo "   清理PID文件: rm -f $PID_FILE"
    echo "   启动服务: ./scripts/run_local.sh"
    exit 1
fi

# 检查网络端口
echo
echo "🌐 网络状态:"
echo "   地址: http://$HOST:$PORT"

if command -v netstat > /dev/null 2>&1; then
    if netstat -tuln 2>/dev/null | grep -q ":$PORT "; then
        echo "   端口状态: ✅ $PORT 端口已监听"
    else
        echo "   端口状态: ❌ $PORT 端口未监听"
    fi
elif command -v ss > /dev/null 2>&1; then
    if ss -tuln 2>/dev/null | grep -q ":$PORT "; then
        echo "   端口状态: ✅ $PORT 端口已监听"
    else
        echo "   端口状态: ❌ $PORT 端口未监听"
    fi
else
    echo "   端口状态: ❓ 无法检查 (缺少 netstat 或 ss 命令)"
fi

# 健康检查
echo
echo "🏥 健康检查:"
if command -v curl > /dev/null 2>&1; then
    if curl -s --connect-timeout 5 "http://localhost:$PORT/health" > /dev/null 2>&1; then
        echo "   API状态: ✅ 健康"
        
        # 获取响应内容
        HEALTH_RESPONSE=$(curl -s --connect-timeout 5 "http://localhost:$PORT/health" 2>/dev/null || echo "")
        if [ -n "$HEALTH_RESPONSE" ]; then
            echo "   响应: $HEALTH_RESPONSE"
        fi
    else
        echo "   API状态: ❌ 不健康或无响应"
    fi
else
    echo "   API状态: ❓ 无法检查 (缺少 curl 命令)"
fi

# 日志文件状态
echo
echo "📋 日志文件:"
if [ -f "$LOG_FILE" ]; then
    LOG_SIZE=$(du -h "$LOG_FILE" 2>/dev/null | cut -f1 || echo "未知")
    LOG_LINES=$(wc -l < "$LOG_FILE" 2>/dev/null || echo "未知")
    echo "   访问日志: ✅ $LOG_FILE ($LOG_SIZE, $LOG_LINES 行)"
    echo "   最新日志: tail -f $LOG_FILE"
else
    echo "   访问日志: ❌ $LOG_FILE 不存在"
fi

if [ -f "$ERROR_LOG_FILE" ]; then
    ERROR_SIZE=$(du -h "$ERROR_LOG_FILE" 2>/dev/null | cut -f1 || echo "未知")
    ERROR_LINES=$(wc -l < "$ERROR_LOG_FILE" 2>/dev/null || echo "未知")
    echo "   错误日志: ✅ $ERROR_LOG_FILE ($ERROR_SIZE, $ERROR_LINES 行)"
    
    # 检查是否有最近的错误
    if [ -s "$ERROR_LOG_FILE" ]; then
        RECENT_ERRORS=$(tail -n 5 "$ERROR_LOG_FILE" 2>/dev/null | wc -l)
        if [ "$RECENT_ERRORS" -gt 0 ]; then
            echo "   ⚠️  发现错误日志，最近5行:"
            tail -n 5 "$ERROR_LOG_FILE" | sed 's/^/      /'
        fi
    fi
else
    echo "   错误日志: ❌ $ERROR_LOG_FILE 不存在"
fi

# 操作提示
echo
echo "🛠️  操作命令:"
echo "   查看日志: tail -f $LOG_FILE"
echo "   停止服务: ./scripts/stop_local.sh"
echo "   重启服务: ./scripts/restart_local.sh"
echo "   测试API: curl http://localhost:$PORT/health"
