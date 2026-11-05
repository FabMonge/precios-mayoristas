@echo off
rem ---------------------------------------------------------------------------
rem Actualiza los precios desde el SISAP y los sube a GitHub (version Windows).
rem La ejecuta la tarea programada "Precios mayoristas El Comercio" desde una
rem copia del repositorio fuera de Google Drive, para no depender de que Drive
rem haya terminado de iniciar. Tiene que correr desde el Peru: el SISAP bloquea
rem IPs del extranjero.
rem Registro: %USERPROFILE%\PreciosMayoristas\actualizar.log
rem ---------------------------------------------------------------------------
setlocal
set "REPO=%~dp0.."
set "BASE=%USERPROFILE%\PreciosMayoristas"
set "PY=%BASE%\venv\Scripts\python.exe"
set "LOG=%BASE%\actualizar.log"
set "PYTHONIOENCODING=utf-8"
rem Sin ventanas de login: si faltan credenciales, git falla y queda en el registro
set "GIT_TERMINAL_PROMPT=0"
set "GCM_INTERACTIVE=never"

cd /d "%REPO%" || exit /b 1
echo ===== %date% %time% >> "%LOG%"

rem Al despertar la PC la red puede tardar: hasta 6 intentos, 30 s entre cada uno
set INTENTOS=0
:traer
echo [1/3] Trayendo cambios de GitHub >> "%LOG%"
git pull --rebase --autostash -q origin main >> "%LOG%" 2>&1
if not errorlevel 1 goto precios
set /a INTENTOS+=1
if %INTENTOS% geq 6 goto sin_red
echo Sin conexion, nuevo intento en 30 s >> "%LOG%"
ping -n 31 127.0.0.1 >nul
goto traer

:sin_red
echo ERROR: no se pudo conectar con GitHub >> "%LOG%"
exit /b 1

:precios
echo [2/3] Consultando el SISAP >> "%LOG%"
"%PY%" -W ignore scripts\actualizar_precios.py --salida data\ticker_precios.json --historico data\historico_precios.json >> "%LOG%" 2>&1
if errorlevel 1 (
  echo ERROR: fallo el script de precios >> "%LOG%"
  exit /b 1
)

rem Solo se hace commit si los datos cambiaron
git status --porcelain -- data | findstr . >nul
if errorlevel 1 (
  echo Sin cambios en los datos >> "%LOG%"
  exit /b 0
)
echo [3/3] Publicando en GitHub >> "%LOG%"
git add data\ticker_precios.json data\historico_precios.json >> "%LOG%" 2>&1
git commit -q -m "Precios mayoristas (actualizado desde Lima)" >> "%LOG%" 2>&1
git push -q origin HEAD:main >> "%LOG%" 2>&1
if errorlevel 1 (
  echo ERROR al subir a GitHub >> "%LOG%"
  exit /b 1
)
echo Publicado en GitHub >> "%LOG%"
