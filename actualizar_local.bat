@echo off
setlocal EnableExtensions
cd /d "%~dp0"

echo ================================================
echo Compararadar - actualizacion local
echo ================================================
echo.

git rev-parse --is-inside-work-tree >nul 2>&1
if errorlevel 1 goto :not_git

echo [1/4] Sincronizando codigo desde GitHub...
git fetch origin
if errorlevel 1 goto :error

rem Los JSON de catalogo, salud e historial son artefactos generados.
rem No se intenta mezclar esos cambios con el codigo del repositorio.
git reset --hard origin/main
if errorlevel 1 goto :error

git clean -fd
if errorlevel 1 goto :error

echo Codigo local sincronizado con origin/main.
echo.

echo [2/4] Instalando dependencias...
py -m pip install -r requirements.txt
if errorlevel 1 goto :error

echo.
echo [3/4] Ejecutando actualizacion completa del catalogo...
py actualizar.py
if errorlevel 1 goto :error

echo.
echo [4/4] Verificacion final...
if not exist "productos.json" goto :catalog_missing
if not exist "config\salud_tiendas.json" goto :health_missing

for %%F in (productos.json) do echo Catalogo generado: %%~zF bytes

echo.
echo ================================================
echo ACTUALIZACION COMPLETADA
echo ================================================
echo.
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
