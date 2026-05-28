@echo off
chcp 65001 >nul
title Git Trend Monitor

echo ========================================
echo   Git Trend Monitor 一键启动
echo ========================================
echo.

:: 检查 Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [错误] 未找到 Python，请先安装 Python 3.8+
    pause
    exit /b 1
)

:: 检查并安装依赖
echo [1/3] 检查依赖...
pip show fastapi >nul 2>&1
if errorlevel 1 (
    echo [2/3] 首次运行，正在安装依赖...
    pip install -r requirements.txt
    if errorlevel 1 (
        echo [错误] 依赖安装失败
        pause
        exit /b 1
    )
) else (
    echo [2/3] 依赖已安装
)

:: 启动服务
echo [3/3] 启动服务...
echo.
echo ========================================
echo   服务启动中，请稍候...
echo ========================================
echo.

:: 后台启动服务器
start "" cmd /c "python -m uvicorn app.main:app --host 0.0.0.0 --port 8000"

:: 等待服务启动
echo 等待服务启动...
powershell -Command "while(!(Invoke-WebRequest -Uri http://localhost:8000 -UseBasicParsing -ErrorAction SilentlyContinue)){Start-Sleep -Seconds 1}"

:: 打开浏览器
echo 正在打开浏览器...
start "" "http://localhost:8000"

echo.
echo ========================================
echo   服务已启动！
echo   浏览器访问: http://localhost:8000
echo   按任意键停止服务并退出
echo ========================================
echo.

:: 等待用户按键
timeout /t 5 >nul

:: 停止服务 (可选)
echo 正在停止服务...
rem 如果需要手动停止，请在打开的窗口中使用Ctrl+C
