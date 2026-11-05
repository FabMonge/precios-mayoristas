@echo off
rem Registra si el SISAP y el PDF de aves ya publicaron los datos de hoy. No publica nada.
rem La ejecuta la tarea programada "Medicion publicacion SISAP" cada 30 minutos.
rem Resultado: %USERPROFILE%\PreciosMayoristas\medicion_publicacion.csv
setlocal
set "BASE=%USERPROFILE%\PreciosMayoristas"
set "PYTHONIOENCODING=utf-8"
cd /d "%~dp0.." || exit /b 1
"%BASE%\venv\Scripts\python.exe" -W ignore scripts\medir_publicacion.py --salida "%BASE%\medicion_publicacion.csv" >> "%BASE%\medicion.log" 2>&1
