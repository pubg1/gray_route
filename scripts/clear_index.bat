@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

echo 🗑️  OpenSearch 索引清除工具
echo ================================

rem 检查Python是否可用
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ❌ Python 未安装或不在PATH中
    pause
    exit /b 1
)

echo ✅ Python 环境检查通过
echo.

echo 📋 清除选项:
echo   1. 交互式清除 - 提供多种清除方法选择
echo   2. 快速清除   - 直接删除所有文档数据
echo.

set /p choice="请选择清除方式 (1/2): "

if "%choice%"=="1" (
    echo 🚀 启动交互式清除工具...
    python clear_opensearch_index.py
) else if "%choice%"=="2" (
    echo ⚠️  警告: 即将快速清除所有索引数据!
    set /p confirm="确认继续吗? (y/N): "
    if /i "!confirm!"=="y" (
        echo 🚀 启动快速清除...
        python quick_clear_index.py
    ) else (
        echo 👋 操作已取消
    )
) else (
    echo ❌ 无效选择
    pause
    exit /b 1
)

if %errorlevel% equ 0 (
    echo.
    echo 🎉 清除操作完成!
) else (
    echo.
    echo ❌ 清除操作失败!
)

echo.
pause
