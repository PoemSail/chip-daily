@echo off
cd /d "D:\AI_projects\芯片日报\chip-daily"
git add content\posts\
git diff --staged --quiet
if errorlevel 1 (
    for /f "tokens=1-3 delims=/ " %%a in ("%DATE%") do set TODAY=%%c-%%a-%%b
    git commit -m "Daily update: %TODAY%"
    git push
    echo Push successful.
) else (
    echo No new content to push.
)
