@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

echo 🚀===============================================================================🚀
echo    OpenSearch 故障现象匹配系统 - 一键部署
echo    基于 servicingcase_last.json 的智能故障诊断
echo    保留所有原有字段，按照 README.md 设计实现
echo 🚀===============================================================================🚀
echo.

rem 检查Python是否可用
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ❌ Python 未安装或不在PATH中
    echo 请先安装Python 3.8+并添加到环境变量
    pause
    exit /b 1
)

echo ✅ Python 环境检查通过
echo.

echo 📋 选择部署方式:
echo    1. 一键自动部署（推荐）
echo    2. 手动步骤部署
echo    3. 仅启动已配置的系统
echo.

set /p choice="请选择 (1/2/3): "

if "%choice%"=="1" (
    echo 🚀 启动一键自动部署...
    python one_click_setup.py
) else if "%choice%"=="2" (
    echo 📋 手动步骤部署...
    echo.
    echo 步骤 1: 安装依赖
    python install_opensearch_deps.py
    if %errorlevel% neq 0 (
        echo ❌ 依赖安装失败
        pause
        exit /b 1
    )
    
    echo.
    echo 步骤 2: 测试连接
    python test_vpc_connection.py
    
    echo.
    echo 步骤 3: 导入数据
    set /p import_choice="是否导入数据？(Y/n): "
    if /i not "!import_choice!"=="n" (
        python import_to_opensearch_preserve_fields.py
    )
    
    echo.
    echo 步骤 4: 运行测试
    python test_system_integration.py
    
    echo.
    echo 🎉 手动部署完成!
    echo 运行 'python start_opensearch_system.py' 启动系统
    
) else if "%choice%"=="3" (
    echo 🚀 启动已配置的系统...
    python start_opensearch_system.py
) else (
    echo ❌ 无效选择
    pause
    exit /b 1
)

if %errorlevel% equ 0 (
    echo.
    echo 🎉 操作完成!
    echo.
    echo 💡 系统特性:
    echo    ✅ 保留所有原有字段和数据ID
    echo    ✅ 智能故障现象匹配
    echo    ✅ 灰区路由决策
    echo    ✅ 多维度搜索和过滤
    echo.
    echo 📖 更多信息:
    echo    - 详细文档: OpenSearch_Integration_README.md
    echo    - 完成报告: OPENSEARCH_SYSTEM_COMPLETE.md
    echo    - API 文档: http://127.0.0.1:8000/docs (启动后访问)
) else (
    echo.
    echo ❌ 操作失败，请检查错误信息
)

echo.
pause
