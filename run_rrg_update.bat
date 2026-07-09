@echo off
rem ============================================================
rem  WEEKLY KEYS - daily RRG data update (run by Task Scheduler)
rem  1. Runs update_rrg_data.py (downloads Yahoo Finance data,
rem     recomputes rrg_current.json / rrg_trails.json)
rem  2. Commits and pushes the fresh JSON to GitHub (backup /
rem     future GitHub Pages once Actions is unblocked)
rem  3. Deploys the live site to Cloudflare Pages:
rem     https://weekly-keys-rrg.pages.dev/
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

rem --- deploy to Cloudflare Pages (live site) ---
if exist "%TEMP%\wk_site" rmdir /s /q "%TEMP%\wk_site"
mkdir "%TEMP%\wk_site"
copy /y index.html "%TEMP%\wk_site\" >nul
copy /y rrg_current.json "%TEMP%\wk_site\" >nul
copy /y rrg_trails.json "%TEMP%\wk_site\" >nul
rem wrangler's exit code is unreliable on Windows - check its output instead
call npx --yes wrangler@3 pages deploy "%TEMP%\wk_site" --project-name weekly-keys-rrg --branch main --commit-dirty=true > "%TEMP%\wk_deploy.log" 2>&1
type "%TEMP%\wk_deploy.log" >> rrg_update.log
findstr /c:"Success" "%TEMP%\wk_deploy.log" >nul
if errorlevel 1 (
    echo Cloudflare deploy FAILED - see log above >> rrg_update.log
) else (
    echo Deployed to https://weekly-keys-rrg.pages.dev/ >> rrg_update.log
)
