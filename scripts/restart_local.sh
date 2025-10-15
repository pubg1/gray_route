#!/usr/bin/env bash
set -euo pipefail

# 配置
APP_NAME="codex-gray-route"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "🔄 重启 $APP_NAME 服务..."

# 停止服务
echo "1️⃣ 停止当前服务..."
if [ -f "$SCRIPT_DIR/stop_local.sh" ]; then
    bash "$SCRIPT_DIR/stop_local.sh" || true
else
    echo "❌ 未找到停止脚本: $SCRIPT_DIR/stop_local.sh"
    exit 1
fi

echo

# 等待一下确保完全停止
sleep 2

# 启动服务
echo "2️⃣ 启动新服务..."
if [ -f "$SCRIPT_DIR/run_local.sh" ]; then
    bash "$SCRIPT_DIR/run_local.sh"
else
    echo "❌ 未找到启动脚本: $SCRIPT_DIR/run_local.sh"
    exit 1
fi

echo
echo "🎉 重启完成!"
