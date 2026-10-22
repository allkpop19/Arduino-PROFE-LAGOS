@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Primero ejecuta instalar.bat.
  pause
  exit /b 1
)
set CASA_DEMO=1
echo SIMULACION: no controla ningun Arduino.
echo Abre http://127.0.0.1:8000 y usa el boton para acercar una persona.
".venv\Scripts\python.exe" -m uvicorn app:app --host 127.0.0.1 --port 8000
pause
