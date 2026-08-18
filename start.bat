@echo off
echo ========================================
echo  V93K RAG 问答系统 - 一键启动
echo ========================================
echo.

REM ---------- 指定 edu_rag 环境 ----------
set EDU_RAG_PY=D:\Anaconda\envs\edu_rag\python.exe
if not exist "%EDU_RAG_PY%" (
    echo [错误] 找不到 edu_rag 环境: %EDU_RAG_PY%
    echo 请确认 Anaconda 安装位置，或修改本脚本中的路径
    pause
    exit /b 1
)
echo edu_rag: %EDU_RAG_PY%
echo.

REM ---------- 启动后端（edu_rag 环境，FastAPI :8000） ----------
echo [1/2] 启动后端 (FastAPI :8000) ...
start "V93K-Backend" cmd /k "%EDU_RAG_PY% -m uvicorn main:app --host 0.0.0.0 --port 8000"

REM ---------- 启动前端代理（edu_rag 环境，:8888） ----------
echo [2/2] 启动前端 (静态 + 反向代理 :8888) ...
start "V93K-Proxy" cmd /k "%EDU_RAG_PY% web_server.py"

echo.
echo ========================================
echo  两个服务已启动：
echo    后端 API : http://localhost:8000
echo    访问入口 : http://localhost:8888
echo ========================================
echo  （两个新窗口已打开，关闭对应窗口即可停止对应服务）
echo.
pause
