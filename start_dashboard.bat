@echo off
rem ============================================================
rem  WEEKLY KEYS - open the dashboard locally
rem  Double-click this file: it starts a local web server and
rem  opens the dashboard in your browser. Keep the black window
rem  open while using the dashboard; close it when done.
rem ============================================================
cd /d "%~dp0"
start "" "http://localhost:8123/index.html"
"C:\Users\jeror\AppData\Local\Programs\Python\Python314\python.exe" -m http.server 8123
