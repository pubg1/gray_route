@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

rem 汽车故障诊断 API - Windows 批处理测试脚本

set BASE_URL=http://localhost:8000

echo 🚀 汽车故障诊断 API 测试
echo ==================================
echo API地址: %BASE_URL%
echo.

rem 测试函数
:test_api
set description=%~1
set url=%~2
echo 🔍 测试: %description%
echo 请求: %url%

curl -s "%url%"
if %errorlevel% equ 0 (
    echo ✅ 请求成功
) else (
    echo ❌ 请求失败
)
echo.
echo ---
echo.
goto :eof

rem 1. 健康检查
call :test_api "健康检查" "%BASE_URL%/health"

rem 2. 基础查询测试
call :test_api "基础查询 - 刹车发软" "%BASE_URL%/match?q=刹车发软"

call :test_api "基础查询 - 发动机无法启动" "%BASE_URL%/match?q=发动机无法启动"

call :test_api "基础查询 - 方向盘很重" "%BASE_URL%/match?q=方向盘很重"

rem 3. 参数化查询测试
call :test_api "指定系统查询" "%BASE_URL%/match?q=刹车发软&system=制动"

call :test_api "指定返回数量" "%BASE_URL%/match?q=发动机故障&topn_return=5"

call :test_api "完整参数查询" "%BASE_URL%/match?q=发动机无法启动&system=发动机&model=宋&year=2019&topn_return=3"

rem 4. 边界测试
call :test_api "空查询 (应该失败)" "%BASE_URL%/match?q="

call :test_api "单字符查询" "%BASE_URL%/match?q=a"

call :test_api "不相关查询" "%BASE_URL%/match?q=做饭洗衣服"

echo 🎯 测试完成！
echo.
echo 💡 提示:
echo - 确保已安装 curl 工具
echo - 确保API服务正在 %BASE_URL% 上运行
echo - 如需格式化JSON输出，可以使用在线JSON格式化工具

pause
