@echo off
setlocal EnableExtensions
cd /d "%~dp0"

set "STATUS_FILE=%TEMP%\compararadar_git_status.txt"
set "HAS_CHANGES="

echo ================================================
echo Compararadar - actualizacion local
echo ================================================
echo.

git rev-parse --is-inside-work-tree >nul 2>&1
if errorlevel 1 goto :not_git

echo [1/5] Protegiendo cambios locales...
git status --porcelain > "%STATUS_FILE%"
for /f "usebackq delims=" %%A in ("%STATUS_FILE%") do set "HAS_CHANGES=1"
if defined HAS_CHANGES (
    git stash -u -m "compararadar-auto-update-backup"
    if errorlevel 1 goto :error
    echo Cambios locales guardados temporalmente.
) else (
    echo No hay cambios locales.
)
if exist "%STATUS_FILE%" del /q "%STATUS_FILE%" >nul 2>&1

echo.
echo [2/5] Sincronizando con GitHub...
git fetch origin
if errorlevel 1 goto :error

git checkout -f main
if errorlevel 1 goto :error

git reset --hard origin/main
if errorlevel 1 goto :error

git clean -fd
if errorlevel 1 goto :error

echo Codigo local sincronizado con origin/main.

echo.
echo [3/5] Instalando dependencias...
py -m pip install -r requirements.txt
if errorlevel 1 goto :pip_error

goto :run_catalog

:pip_error
echo ERROR: No se pudieron instalar las dependencias.
goto :error

:run_catalog
echo.
echo [4/5] Ejecutando actualizacion completa del catalogo...
py actualizar.py
if errorlevel 1 goto :error

echo.
echo [5/5] Verificacion final...
if not exist "productos.json" goto :catalog_missing
if not exist "config\salud_tiendas.json" goto :health_missing

for %%F in (productos.json) do echo Catalogo generado: %%~zF bytes

echo.
echo ================================================
echo ACTUALIZACION COMPLETADA
 echo ================================================
echo.
echo El catalogo fue actualizado y validado.
exit /b 0

:not_git
echo ERROR: esta carpeta no es un repositorio Git.
goto :error

:catalog_missing
echo ERROR: actualizar.py termino sin generar productos.json.
goto :error

:health_missing
echo ERROR: no se genero config\salud_tiendas.json.
goto :error

:error
echo.
echo ================================================
echo ERROR EN LA ACTUALIZACION
 echo ================================================
echo Revisa el mensaje anterior.
exit /b 1
