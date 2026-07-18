@echo off
rem Double-clickable Windows launcher (Tkinter ships with the python.org installer).
cd /d "%~dp0"
where pythonw >nul 2>nul && (start "" pythonw run.py & exit /b)
python run.py
if errorlevel 1 pause
