@echo off
cd /d "D:\AI_projects\芯片日报\chip-daily"

rem 清除残留 git 锁文件，防止上次异常退出导致阻塞
if exist .git\index.lock del /f .git\index.lock
if exist .git\HEAD.lock  del /f .git\HEAD.lock
if exist .git\MERGE_HEAD  del /f .git\MERGE_HEAD

rem 拉取远端最新（rebase 方式，避免产生