@echo off
cd /d "%~dp0"
where py >nul 2>&1 && (py -3 deinstalleer.py & goto :end)
where python >nul 2>&1 && (python deinstalleer.py & goto :end)
echo Python 3.11 of hoger is vereist. Installeer Python via https://python.org
:end
pause
