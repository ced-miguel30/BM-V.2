# Instala BM en el servidor del hotel (Windows). Ejecutar UNA vez, como administrador:
#   powershell -ExecutionPolicy Bypass -File instalar\instalar.ps1
# Deja BM arrancando solo con Windows en http://<servidor>:8000 para todos los PCs y móviles de la red.
param(
    [int]$Puerto = 8000,
    [string]$Datos = "$PSScriptRoot\..\datos"
)
$ErrorActionPreference = 'Stop'
$raiz = (Resolve-Path "$PSScriptRoot\..").Path
$Datos = [IO.Path]::GetFullPath($Datos)
$db = Join-Path $Datos 'bm.sqlite'

if (-not ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw 'Abre PowerShell como administrador y vuelve a ejecutar el instalador.'
}

Write-Host '1/5 Comprobando Python...' -ForegroundColor Cyan
$py = (Get-Command py -ErrorAction SilentlyContinue).Source
if (-not $py) { throw 'Falta Python 3.11 o superior. Instálalo desde python.org (marca "Add to PATH") y repite.' }
& $py -3 -c "import sys; assert sys.version_info >= (3, 11), sys.version"
if ($LASTEXITCODE -ne 0) { throw 'Se necesita Python 3.11 o superior.' }

Write-Host '2/5 Preparando entorno e instalando dependencias...' -ForegroundColor Cyan
if (-not (Test-Path "$raiz\.venv")) { & $py -3 -m venv "$raiz\.venv" }
$python = "$raiz\.venv\Scripts\python.exe"
& $python -m pip install --quiet --upgrade pip
& $python -m pip install --quiet -r "$raiz\requirements.txt"
if ($LASTEXITCODE -ne 0) { throw 'No se pudieron instalar las dependencias.' }

Write-Host "3/5 Carpeta de datos: $Datos" -ForegroundColor Cyan
New-Item -ItemType Directory -Force -Path $Datos | Out-Null

Write-Host '4/5 Registrando BM para que arranque con Windows...' -ForegroundColor Cyan
$accion = New-ScheduledTaskAction -Execute $python -Argument "-m bm.servidor --puerto $Puerto --db `"$db`"" -WorkingDirectory $raiz
$inicio = New-ScheduledTaskTrigger -AtStartup
$ajustes = New-ScheduledTaskSettingsSet -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit ([TimeSpan]::Zero) -StartWhenAvailable
Register-ScheduledTask -TaskName 'BM servidor' -Action $accion -Trigger $inicio -Settings $ajustes -User 'SYSTEM' -RunLevel Highest -Force | Out-Null

Write-Host "5/5 Abriendo el puerto $Puerto en el firewall (solo red del hotel)..." -ForegroundColor Cyan
Get-NetFirewallRule -DisplayName 'BM servidor' -ErrorAction SilentlyContinue | Remove-NetFirewallRule
New-NetFirewallRule -DisplayName 'BM servidor' -Direction Inbound -Protocol TCP -LocalPort $Puerto -Action Allow -Profile Domain, Private | Out-Null

Start-ScheduledTask -TaskName 'BM servidor'
Write-Host ''
Write-Host "Listo. Desde cualquier PC o móvil de la red: http://$($env:COMPUTERNAME):$Puerto" -ForegroundColor Green
Write-Host 'Siguiente paso (solo la primera vez): crear el primer usuario de Dirección:'
Write-Host "  `$env:BM_DB = '$db'; & '$python' -m bm.usuarios <usuario> `"<Nombre>`" direccion"
