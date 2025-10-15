#!/bin/bash
# 汽车故障诊断 API - cURL 测试脚本

BASE_URL="http://localhost:8000"

echo "🚀 汽车故障诊断 API 测试"
echo "=================================="
echo "API地址: $BASE_URL"
echo

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 测试函数
test_api() {
    local description="$1"
    local url="$2"
    local expected_status="${3:-200}"
    
    echo -e "${BLUE}🔍 测试: $description${NC}"
    echo "请求: $url"
    
    # 发送请求并获取状态码
    response=$(curl -s -w "\n%{http_code}" "$url")
    status_code=$(echo "$response" | tail -n1)
    body=$(echo "$response" | head -n -1)
    
    if [ "$status_code" -eq "$expected_status" ]; then
        echo -e "${GREEN}✅ 成功 (HTTP $status_code)${NC}"
        
        # 如果是JSON响应，格式化输出
        if echo "$body" | jq . > /dev/null 2>&1; then
            echo "响应 (格式化):"
            echo "$body" | jq .
        else
            echo "响应: $body"
        fi
    else
        echo -e "${RED}❌ 失败 (HTTP $status_code, 期望: $expected_status)${NC}"
        echo "响应: $body"
    fi
    
    echo
    echo "---"
    echo
}

# 1. 健康检查
test_api "健康检查" "$BASE_URL/health"

# 2. 基础查询测试
test_api "基础查询 - 刹车发软" "$BASE_URL/match?q=刹车发软"

test_api "基础查询 - 发动机无法启动" "$BASE_URL/match?q=发动机无法启动"

test_api "基础查询 - 方向盘很重" "$BASE_URL/match?q=方向盘很重"

# 3. 参数化查询测试
test_api "指定系统查询" "$BASE_URL/match?q=刹车发软&system=制动"

test_api "指定返回数量" "$BASE_URL/match?q=发动机故障&topn_return=5"

test_api "完整参数查询" "$BASE_URL/match?q=发动机无法启动&system=发动机&model=宋&year=2019&topn_return=3"

# 4. 边界测试
test_api "空查询 (应该失败)" "$BASE_URL/match?q=" 422

test_api "单字符查询" "$BASE_URL/match?q=a"

test_api "不相关查询" "$BASE_URL/match?q=做饭洗衣服"

# 5. URL编码测试
test_api "中文查询 (URL编码)" "$BASE_URL/match?q=%E5%88%B9%E8%BD%A6%E5%8F%91%E8%BD%AF"

echo -e "${YELLOW}🎯 测试完成！${NC}"
echo
echo "💡 提示:"
echo "- 如果看到 'command not found: jq'，请安装 jq 工具来格式化JSON输出"
echo "- 在Windows上可以使用 Git Bash 或 WSL 运行此脚本"
echo "- 确保API服务正在 $BASE_URL 上运行"
