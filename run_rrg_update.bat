@echo off
rem ============================================================
rem  WEEKLY KEYS - daily RRG data update (run by Task Scheduler)
rem  1. Runs update_rrg_data.py (downloads Yahoo Finance data,
rem     recomputes rrg_current.json / rrg_trails.json)
rem  2. Commits and pushes the fresh JSON to GitHub so the
rem     GitHub Pages dashboard stays current
rem  Appends a log to rrg_update.log
rem ============================================================
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"
echo. >> rrg_update.log
echo ===== %date% %time% ===== >> rrg_update.log

"C:\Users\jeror\AppData\Local\Programs\Python\Python314\python.exe" update_rrg_data.py >> rrg_update.log 2>&1
if errorlevel 1 (
    echo Update script FAILED - skipping git push >> rrg_update.log
    exit /b 1
)

git add rrg_current.json rrg_trails.json >> rrg_update.log 2>&1
git diff --cached --quiet
if errorlevel 1 (
    git commit -m "Auto-update RRG data" >> rrg_update.log 2>&1
    git push origin main >> rrg_update.log 2>&1
    echo Pushed updated data to GitHub >> rrg_update.log
) else (
    echo No data changes - nothing to push >> rrg_update.log
)
