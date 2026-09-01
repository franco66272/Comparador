@echo off
setlocal
cd /d "%~dp0"

echo ================================================================
echo TECNORADAR - HISTORIAL HARDGAMERS
 echo ================================================================
echo.

echo [1/2] Verificando Playwright...
py -c "import playwright" >nul 2>&1
if errorlevel 1 (
  echo Playwright no esta instalado. Instalando...
  py -m pip install playwright
  if errorlevel 1 goto :error
)

echo [2/2] Verificando Chromium...
py -m playwright install chromium
if errorlevel 1 goto :error

echo.
echo Usando IDs directos de HardGamers; no se ejecuta el buscador por producto.
echo Esto reduce los 429 y evita falsos matches.
echo.
py importar_historial_hardgamers.py
if errorlevel 1 goto :error

echo.
echo ================================================================
echo HISTORIAL IMPORTADO CORRECTAMENTE
echo Revisar logs_auto\hardgamers_historial.json para el resumen.
echo ================================================================
pause
exit /b 0

:error
echo.
echo ================================================================
echo ERROR durante la preparacion o importacion del historial.
echo ================================================================
pause
exit /b 1
