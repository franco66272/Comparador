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

set "PY=py -3.14"
%PY% --version >nul 2>&1
if errorlevel 1 set "PY=py"
%PY% --version >nul 2>&1
if errorlevel 1 (
  echo ERROR: no se encontro Python mediante el launcher 'py'.
  pause
  exit /b 1
)

echo.
echo [1/5] Sincronizando codigo desde GitHub...
git status --porcelain >nul 2>&1
if errorlevel 1 goto :error
for /f "delims=" %%A in ('git status --porcelain') do set HAS_CHANGES=1
if defined HAS_CHANGES (
  echo Se encontraron cambios locales. Se guardaran temporalmente.
  git stash push -u -m "compararadar-auto-update-backup"
  if errorlevel 1 goto :error
)
git fetch origin
if errorlevel 1 goto :error
git checkout main
if errorlevel 1 goto :error
git reset --hard origin/main
if errorlevel 1 goto :error

echo.
echo [2/5] Instalando dependencias...
%PY% -m pip install -r requirements.txt
if errorlevel 1 (
  echo ERROR: no se pudieron instalar las dependencias.
  goto :error
)

echo.
echo [3/5] Verificando Scrapy...
cd scraper
%PY% -m scrapy list | findstr /i "venex" >nul
if errorlevel 1 (
  cd ..
  echo ERROR: Scrapy no encontro el spider venex.
  goto :error
)
cd ..

echo.
echo [4/5] Ejecutando actualizacion completa del catalogo...
%PY% actualizar.py
if errorlevel 1 (
  echo ERROR: la actualizacion del catalogo fallo.
  goto :error
)

echo.
echo [5/5] Catalogo actualizado y validado.
if exist productos.json (
  for %%A in (productos.json) do echo productos.json: %%~zA bytes
) else (
  echo AVISO: no se encontro productos.json.
)

echo.
echo ================================================
echo ACTUALIZACION COMPLETADA
 echo ================================================
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
