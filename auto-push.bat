@echo off
setlocal enabledelayedexpansion
cd /d "D:\AI_projects\芯片日报\chip-daily"

rem ============================================================
rem  芯片日报 auto-push.bat  v3
rem  核心修复：
rem    1. commit 成功但 push 失败后，下次运行检测到"本地领先远端"
rem       仍会继续推送，不会因"无新暂存文件"而提前退出
rem    2. push 重试次数提升至 5 次，间隔从 15s 递增至 60s
rem ============================================================

rem === 0. 获取今日日期 ===
if not "%~1"=="" (
    set TODAY=%~1
) else (
    for /f "tokens=*" %%d in ('powershell -NoProfile -Command "Get-Date -Format 'yyyy-MM-dd'"') do set TODAY=%%d
)
echo [auto-push] %DATE% %TIME% -- %TODAY%

rem === 1. 清理残留锁文件 ===
del /f /q .git\index.lock      2>nul
del /f /q .git\HEAD.lock       2>nul
del /f /q .git\ORIG_HEAD.lock  2>nul
del /f /q .git\index.lock.bak  2>nul
if exist .git\MERGE_HEAD  del /f .git\MERGE_HEAD
if exist .git\MERGE_MSG   del /f .git\MERGE_MSG
if exist .git\rebase-merge rmdir /s /q .git\rebase-merge
if exist .git\rebase-apply rmdir /s /q .git\rebase-apply

rem === 2. 检查今日文件是否存在且完整 ===
set MDFILE=content\posts\%TODAY%.md
if not exist "%MDFILE%" (
    echo [auto-push] No file: %MDFILE% -- skip
    exit /b 0
)
for %%F in ("%MDFILE%") do set FSIZE=%%~zF
if %FSIZE% LSS 15000 (
    echo [auto-push] File too small (%FSIZE% bytes), not ready -- skip
    exit /b 0
)

rem === 3. 暂存新内容 ===
git add content\posts\

rem === 4. 检查是否有新的暂存变更 ===
git diff --staged --quiet
if not errorlevel 1 (
    rem 无新暂存文件——但可能存在之前 push 失败留下的未推送 commit
    rem 检查本地是否领先远端（即有未推送的 commit）
    for /f %%n in ('git rev-list HEAD...origin/main --count 2^>nul') do set AHEAD=%%n
    if "!AHEAD!"=="" set AHEAD=0
    if !AHEAD! EQU 0 (
        echo [auto-push] Nothing to commit, already up to date -- done
        exit /b 0
    )
    echo [auto-push] No new files, but !AHEAD! unpushed commit(s) found -- pushing now
    goto PUSH_RETRY
)

rem === 5. 提交 ===
git commit -m "Daily update: %TODAY%"
if errorlevel 1 (
    echo [auto-push] git commit failed
    exit /b 1
)

rem === 6. 推送（失败重试，最多5次，间隔递增）===
:PUSH_RETRY
set RETRY=0

:PUSH_LOOP
set /a RETRY_DISP=%RETRY%+1
echo [auto-push] Pushing... attempt !RETRY_DISP! of 5
git push origin main
if not errorlevel 1 (
    echo [auto-push] SUCCESS: %TODAY% pushed to GitHub
    exit /b 0
)

set /a RETRY+=1
if !RETRY! GEQ 5 (
    echo [auto-push] FAILED after 5 attempts -- will retry at next scheduled run
    exit /b 1
)

rem 递增等待：15s / 30s / 60s / 60s
if !RETRY! EQU 1 set WAIT=15
if !RETRY! EQU 2 set WAIT=30
if !RETRY! EQU 3 set WAIT=60
if !RETRY! EQU 4 set WAIT=60

echo [auto-push] Push failed, waiting !WAIT!s then retrying...
timeout /t !WAIT! /nobreak >nul

rem 先同步远端，避免分叉冲突
git fetch origin main 2>nul
git merge origin/main --no-edit --strategy-option=theirs 2>nul

goto PUSH_LOOP
