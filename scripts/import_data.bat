@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

echo 🚀 OpenSearch 数据导入工具
echo ================================

rem 检查Python是否可用
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ❌ Python 未安装或不在PATH中
    echo 请先安装Python并添加到环境变量
    pause
    exit /b 1
)

rem 检查数据文件是否存在
if not exist "..\data\servicingcase_last.json" (
    echo ❌ 数据文件不存在: ..\data\servicingcase_last.json
    echo 请确认文件路径正确
    pause
    exit /b 1
)

echo ✅ Python 环境检查通过
echo ✅ 数据文件存在

echo.
echo 📦 检查并安装依赖...
python install_opensearch_deps.py
if %errorlevel% neq 0 (
    echo ❌ 依赖安装失败
    pause
    exit /b 1
)

echo.
echo 🔧 开始导入数据...
python run_import.py
if %errorlevel% neq 0 (
    echo ❌ 数据导入失败
    pause
    exit /b 1
)

echo.
echo 🎉 数据导入完成!
echo.
echo 💡 提示:
echo - OpenSearch 地址: http://localhost:9200
echo - 索引名称: automotive_cases
echo - 可以使用 Kibana 或 OpenSearch Dashboards 查看数据
echo.
pause
