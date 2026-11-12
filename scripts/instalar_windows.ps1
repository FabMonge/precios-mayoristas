# Instala en una PC con Windows el proceso diario de precios mayoristas:
# copia del repositorio, Python con sus librerias y las tareas programadas.
# Se puede repetir sin problema. Uso (en PowerShell, sin permisos de administrador):
#
#   irm https://raw.githubusercontent.com/FabMonge/precios-mayoristas/main/scripts/instalar_windows.ps1 | iex
#
# Mensajes sin tildes a proposito: Windows PowerShell 5.1 las rompe al leer el archivo.

$repoUrl = "https://github.com/FabMonge/precios-mayoristas.git"
$base = Join-Path $env:USERPROFILE "PreciosMayoristas"
$repo = Join-Path $base "repo"
$venv = Join-Path $base "venv"
$tareaPrecios = "Precios mayoristas El Comercio"
$tareaMedicion = "Medicion publicacion SISAP"

function Paso($texto) { Write-Host ""; Write-Host "== $texto" -ForegroundColor Cyan }
function Detener($texto) { Write-Host "ERROR: $texto" -ForegroundColor Red; throw $texto }

function Revisar-Sitio($nombre, $url) {
    try {
        Invoke-WebRequest -Uri $url -Method Head -UseBasicParsing -TimeoutSec 25 | Out-Null
        Write-Host "OK      $nombre"
        return $true
    } catch {
        # Un error HTTP igual prueba que hay conexion; solo falla si nunca respondio
        if ($_.Exception.Response) { Write-Host "OK      $nombre"; return $true }
        Write-Host "BLOQUEO $nombre ($url)" -ForegroundColor Red
        return $false
    }
}

function Accion-Oculta($ruta) {
    New-ScheduledTaskAction -Execute "powershell.exe" -Argument ('-NoProfile -WindowStyle Hidden -Command "& cmd.exe /c ''' + $ruta + '''"')
}

Paso "1/6 Revisando programas"
if (-not (Get-Command git -ErrorAction SilentlyContinue)) { Detener "Falta Git. Instalalo desde https://git-scm.com/download/win y repite este comando." }
if (-not (Get-Command python -ErrorAction SilentlyContinue)) { Detener "Falta Python 3.10 o superior. Instalalo desde https://www.python.org/downloads/ y repite este comando." }
python -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)"
if ($LASTEXITCODE -ne 0) { Detener "Se necesita Python 3.10 o superior." }
Write-Host (git --version); Write-Host (python --version)

Paso "2/6 Revisando conexiones desde esta PC"
$sisap = Revisar-Sitio "SISAP (Midagri)" "http://sistemas.midagri.gob.pe/sisap/portal2/mayorista/"
$siea = Revisar-Sitio "SIEA (PDF de aves)" "https://siea.midagri.gob.pe/"
$github = Revisar-Sitio "GitHub" "https://github.com/"
if (-not ($sisap -and $github)) { Detener "Esta PC no llega al SISAP o a GitHub. Pide a Tecnologia que habilite esos sitios." }
if (-not $siea) { Write-Host "Aviso: sin acceso al SIEA; solo afecta al PDF de aves." -ForegroundColor Yellow }

Paso "3/6 Descargando el proyecto en $repo"
New-Item -ItemType Directory -Force $base | Out-Null
if (Test-Path (Join-Path $repo ".git")) { git -C $repo pull --rebase --autostash -q origin main } else { git clone -q $repoUrl $repo }
if ($LASTEXITCODE -ne 0) { Detener "No se pudo descargar el proyecto." }
git -C $repo config user.name "Fabrizio Monge"
git -C $repo config user.email "206781015+FabMonge@users.noreply.github.com"

Paso "4/6 Preparando Python"
if (-not (Test-Path (Join-Path $venv "Scripts\python.exe"))) { python -m venv $venv }
$py = Join-Path $venv "Scripts\python.exe"
& $py -m pip install -q --disable-pip-version-check -r (Join-Path $repo "scripts\requirements.txt")
if ($LASTEXITCODE -ne 0) { Detener "No se pudieron instalar las librerias de Python." }

Paso "5/6 Permiso para subir a GitHub"
Write-Host "Si aparece una ventana de GitHub, inicia sesion con la cuenta FabMonge."
git -C $repo push --dry-run -q origin HEAD:main
if ($LASTEXITCODE -ne 0) { Detener "GitHub no dio permiso para subir datos." }

Paso "6/6 Programando las tareas"
$usuario = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive -RunLevel Limited

$horas = @("09:00", "12:00", "15:00", "19:00") | ForEach-Object { New-ScheduledTaskTrigger -Daily -At $_ }
$ajustes = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Minutes 30) -MultipleInstances IgnoreNew
Register-ScheduledTask -TaskName $tareaPrecios -Description "Actualiza los precios del SISAP y los sube a GitHub (ticker y dashboard de ECData / Economia)." -Action (Accion-Oculta (Join-Path $repo "scripts\actualizar_y_publicar.cmd")) -Trigger $horas -Settings $ajustes -Principal $usuario -Force | Out-Null

$disparo = New-ScheduledTaskTrigger -Daily -At "05:00"
$disparo.Repetition = (New-ScheduledTaskTrigger -Once -At "05:00" -RepetitionInterval (New-TimeSpan -Minutes 30) -RepetitionDuration (New-TimeSpan -Hours 14)).Repetition
$disparo.EndBoundary = (Get-Date).AddDays(10).ToString("yyyy-MM-dd'T'23:59:00")
$ajustesMedicion = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Minutes 10) -MultipleInstances IgnoreNew
Register-ScheduledTask -TaskName $tareaMedicion -Description "Temporal: registra a que hora publican el SISAP y el PDF de aves. No publica nada." -Action (Accion-Oculta (Join-Path $repo "scripts\medir_publicacion.cmd")) -Trigger $disparo -Settings $ajustesMedicion -Principal $usuario -Force | Out-Null

Write-Host "Probando la tarea de precios..."
Start-ScheduledTask -TaskName $tareaPrecios
$limite = (Get-Date).AddMinutes(8)
do { Start-Sleep -Seconds 5 } while ((Get-ScheduledTask -TaskName $tareaPrecios).State -eq "Running" -and (Get-Date) -lt $limite)
$info = Get-ScheduledTaskInfo -TaskName $tareaPrecios

Write-Host ""
if ($info.LastTaskResult -eq 0) {
    Write-Host "LISTO. Proxima actualizacion: $($info.NextRunTime)" -ForegroundColor Green
} else {
    Write-Host "La tarea termino con codigo $($info.LastTaskResult). Revisa el registro:" -ForegroundColor Red
}
Get-Content (Join-Path $base "actualizar.log") -Encoding UTF8 -ErrorAction SilentlyContinue | Select-Object -Last 5
