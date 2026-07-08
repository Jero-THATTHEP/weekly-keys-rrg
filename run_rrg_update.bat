@echo off
rem ============================================================
rem  WEEKLY KEYS - daily RRG data update (run by Task Scheduler)
rem  Runs update_rrg_data.py and appends a log to rrg_update.log
rem ============================================================
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"
echo. >> rrg_update.log
echo ===== %date% %time% ===== >> rrg_update.log
"C:\Users\jeror\AppData\Local\Programs\Python\Python314\python.exe" update_rrg_data.py >> rrg_update.log 2>&1
