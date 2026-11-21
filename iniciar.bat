@echo off
REM Abre la app sin compilar (útil mientras se desarrolla).
cd /d "%~dp0"
if exist .venv\Scripts\pythonw.exe (
  start "" .venv\Scripts\pythonw.exe run.py
) else (
  where pyw >nul 2>nul && (start "" pyw -3 run.py) || (start "" pythonw run.py)
)
