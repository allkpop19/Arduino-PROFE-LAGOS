@echo off
cd /d "%~dp0"
where py >nul 2>nul
if errorlevel 1 (
  python -m venv .venv
) else (
  py -3 -m venv .venv
)
if errorlevel 1 goto error
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto error
echo.
echo Instalacion lista. Carga casa.ino al Arduino y ejecuta iniciar.bat.
pause
exit /b 0
:error
echo.
echo No se pudo instalar. Revisa que Python 3.10 o superior este instalado y haya Internet.
pause
exit /b 1
