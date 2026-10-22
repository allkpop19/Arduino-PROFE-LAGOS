@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Primero ejecuta instalar.bat.
  pause
  exit /b 1
)
set CASA_DEMO=0
echo Abre http://127.0.0.1:8000 en el navegador.
echo Cierra el Monitor Serie del IDE de Arduino. Deja esta ventana abierta.
".venv\Scripts\python.exe" -m uvicorn app:app --host 127.0.0.1 --port 8000
pause
