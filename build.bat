@echo off
REM Crea dist\OrganizadorOptimus.exe (un solo archivo, sin consola)
REM Requiere Python 3.10+ instalado desde python.org (con la casilla "Add to PATH").
chcp 65001 >nul
cd /d "%~dp0"

where py >nul 2>nul && (set PY=py -3) || (set PY=python)

echo == Creando entorno virtual ==
if not exist .venv %PY% -m venv .venv || goto :error
call .venv\Scripts\activate.bat

echo == Instalando dependencias ==
python -m pip install --upgrade pip >nul
python -m pip install -r requirements.txt pyinstaller || goto :error

echo == Probando ==
python -m pytest -q tests || goto :error

echo == Construyendo el .exe ==
pyinstaller --noconfirm --onefile --windowed ^
  --name OrganizadorOptimus ^
  --icon assets\icono.ico ^
  --collect-submodules pypdf ^
  --add-data "assets\icono.png;assets" ^
  run.py || goto :error

echo.
echo Listo: dist\OrganizadorOptimus.exe
pause
exit /b 0

:error
echo.
echo Hubo un error. Revisa los mensajes de arriba.
pause
exit /b 1
