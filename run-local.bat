@echo off
rem Double-click to run AgriPulse locally on Windows. Arguments are passed through (e.g. -Reset, -NoDemo).
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0run-local.ps1" %*
pause
