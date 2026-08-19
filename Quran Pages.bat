@echo off
setlocal
rem Double-clickable Windows launcher.
rem Prefers the "py" launcher: the python.org installer puts py.exe/pyw.exe in
rem C:\Windows, so it works even when "Add Python to PATH" was left unticked.
cd /d "%~dp0"

where py >nul 2>nul && goto :use_py
where python >nul 2>nul && goto :use_python
goto :no_python

:use_py
set "PY_CONSOLE=py -3"
set "PY_WINDOWED=pyw -3"
goto :check_tk

:use_python
set "PY_CONSOLE=python"
set "PY_WINDOWED=pythonw"
goto :check_tk

:check_tk
rem Check Tkinter with a console first. Launching straight into pyw/pythonw
rem would swallow any startup error and the app would appear to do nothing.
%PY_CONSOLE% -c "import tkinter" >nul 2>nul
if errorlevel 1 goto :no_tk
start "" %PY_WINDOWED% run.py %*
exit /b 0

:no_python
echo.
echo Python was not found on this PC.
echo.
echo Install it from https://www.python.org/downloads/
echo (keep "tcl/tk and IDLE" ticked), then double-click this file again.
echo.
pause
exit /b 1

:no_tk
echo.
echo Python is installed, but Tkinter (tcl/tk) is missing, so no window can open.
echo.
echo Re-run the python.org installer, choose Modify, and tick "tcl/tk and IDLE".
echo.
pause
exit /b 1
