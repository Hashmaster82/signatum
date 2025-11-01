@echo off
chcp 65001 >nul
title Project Runner

echo Updating from GitHub...
if exist ".git" (
    git fetch origin
    git reset --hard origin/main
    git pull origin main --force
) else (
    echo Git repository not found, running local version
)

echo Starting main.py...
python main.py

if errorlevel 1 pause