@echo off
rem ---------------------------------------------------------------------------
rem Actualiza los precios desde el SISAP y los sube a GitHub (version Windows).
rem La ejecuta la tarea programada "Precios mayoristas El Comercio" a las 7, 8 y
rem 9 a.m. Tiene que correr desde el Peru: el SISAP bloquea IPs del extranjero.
rem Registro: %USERPROFILE%\PreciosMayoristas\actualizar.log
rem ---------------------------------------------------------------------------
setlocal
set "REPO=%~dp0.."
set "BASE=%USERPROFILE%\PreciosMayoristas"
set "PY=%BASE%\venv\Scripts\python.exe"
set "LOG=%BASE%\actualizar.log"
set "PYTHONIOENCODING=utf-8"

cd /d "%REPO%" || exit /b 1
echo ===== %date% %time% >> "%LOG%"

rem Trae cambios del repositorio (por si se edito algo desde otra computadora)
git pull --rebase --autostash -q origin main >> "%LOG%" 2>&1

"%PY%" -W ignore scripts\actualizar_precios.py --salida data\ticker_precios.json --historico data\historico_precios.json >> "%LOG%" 2>&1

rem Solo se hace commit si los datos cambiaron
git status --porcelain -- data | findstr . >nul
if errorlevel 1 (
  echo Sin cambios en los datos >> "%LOG%"
  exit /b 0
)
git add data\ticker_precios.json data\historico_precios.json >> "%LOG%" 2>&1
git commit -q -m "Precios mayoristas (actualizado desde Lima)" >> "%LOG%" 2>&1
git push -q origin HEAD:main >> "%LOG%" 2>&1
if errorlevel 1 (
  echo ERROR al subir a GitHub >> "%LOG%"
  exit /b 1
)
echo Publicado en GitHub >> "%LOG%"
