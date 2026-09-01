@echo off
setlocal
cd /d "%~dp0"
py importar_historial_hardgamers.py
if errorlevel 1 (
  echo.
  echo ERROR al importar historial de HardGamers.
  pause
  exit /b 1
)
echo.
echo HISTORIAL IMPORTADO.
pause
