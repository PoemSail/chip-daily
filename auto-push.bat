@echo off
setlocal enabledelayedexpansion
cd /d "D:\AI_projects\芯片日报\chip-daily"

rem ============================================================
rem  芯片日报 auto-push.bat
rem  每日12:15由 Windows 计划任务触发，将新日报推送到 GitHub
rem ============================================================

rem === 1. 清理残留 git 锁文件（防止上次异常退出后卡死）===
if exist .git\index.lock      del /f .git\index.lock
if exist .git\HEAD.lock        del /f .git\HEAD.lock
if exist .git\MERGE_HEAD       del /f .git\MERGE_HEAD
if exist .git\MERGE_MSG        del /f .git\MERGE_MSG
if exist .git\rebase-merge     rmdir /s /q .git\rebase-merge
if exist .git\rebase-apply     rmdir /s /q .git\rebase-apply

rem === 2. 获取今日日期（用 PowerShell，不依赖系统语言/区域设置）===
for /f "tokens=*" %%d in ('powershell -NoProfile -Command "Get-Date -Format 'yyyy-MM-dd'"') do set TODAY=%%d
echo [INFO] Date: %TODAY%

rem === 3. 暂存今日新文章 ===
git add content\posts\

rem === 4. 检查是否有变更（无变更则直接退出）===
git diff --staged --quiet
if not errorlevel 1 (
    echo [INFO] No new content to push. Exiting.
    exit /b 0
)

rem === 5. 提交 ===
git commit -m "Daily update: %TODAY%"
if errorlevel 1 (
    echo [ERROR] git commit failed.
    exit /b 1
)

rem === 6. 推送（失败时最多重试3次，每次间隔15秒并先同步远端）===
set RETRY=0

:PUSH_RETRY
echo [INFO] Pushing to GitHub (attempt !RETRY! of 3)...
git push
if not errorlevel 1 (
    echo [OK] Push successful: %TODAY%
    exit /b 0
)

set /a RETRY+=1
if !RETRY! GEQ 3 (
    echo [ERROR] Push failed after 3 retries. Manual intervention required.
    exit /b 1
)

echo [WARN] Push failed. Waiting 15s then syncing with remote before retry...
timeout /t 15 /nobreak >nul

rem 与远端同步（merge 方式，不用 rebase 避免冲突中断）
git fetch origin main
git merge origin/main --no-edit --strategy-option=theirs
if errorlevel 1 (
    echo [WARN] Merge also failed, proceeding with push anyway...
    git merge --abort 2>nul
)

goto PUSH_RETRY
