@echo off
setlocal EnableExtensions
cd /d "%~dp0"

echo ================================================
echo Compararadar - actualizacion local
echo ================================================

git rev-parse --is-inside-work-tree >nul 2>&1
if errorlevel 1 (
  echo ERROR: esta carpeta no es un repositorio Git.
  pause
  exit /b 1
)

echo.
echo [1/4] Guardando cambios locales para protegerlos...
git status --porcelain >nul
if errorlevel 1 goto :error

for /f "delims=" %%A in ('git status --porcelain') do set HAS_CHANGES=1
if defined HAS_CHANGES (
  git stash push -u -m "compararadar-auto-update-backup"
  if errorlevel 1 goto :error
)

echo.
echo [2/4] Descargando version nueva desde GitHub...
git fetch origin
if errorlevel 1 goto :error

git checkout main
if errorlevel 1 goto :error

git reset --hard origin/main
if errorlevel 1 goto :error

echo.
echo [3/4] Instalando dependencias...
py -m pip install -r requirements.txt
if errorlevel 1 echo AVISO: no se pudieron actualizar todas las dependencias.

echo.
echo [4/4] Verificando spider de Venex...
cd scraper
py -m scrapy list | findstr /i "venex"
if errorlevel 1 (
  cd ..
  echo ERROR: Scrapy no encontro el spider venex.
  goto :error
)
cd ..

echo.
echo ================================================
echo ACTUALIZACION COMPLETADA
echo ================================================
echo.
echo Para probar Venex:
echo   cd scraper
echo   py -m scrapy crawl venex -O ..\prueba_venex.json

echo.
echo Para actualizar todo el catalogo:
echo   py actualizar.py

echo.
pause
exit /b 0

:error
echo.
echo ================================================
echo ERROR EN LA ACTUALIZACION
echo ================================================
echo Revisa el mensaje anterior.
pause
exit /b 1
