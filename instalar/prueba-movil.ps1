# Prueba BM en el móvil desde este PC, con datos inventados y un enlace https temporal (Cloudflare).
#   powershell -ExecutionPolicy Bypass -File instalar\prueba-movil.ps1
# No necesita administrador ni toca la base real: usa datos\prueba.sqlite. Al pulsar Enter se cierra todo.
param(
    [int]$Puerto = 8765,
    [string]$Clave = 'prueba2026'
)
$ErrorActionPreference = 'Stop'
$raiz = (Resolve-Path "$PSScriptRoot\..").Path
$datos = Join-Path $raiz 'datos'
$db = Join-Path $datos 'prueba.sqlite'
New-Item -ItemType Directory -Force -Path $datos | Out-Null

Write-Host '1/4 Comprobando Python...' -ForegroundColor Cyan
$py = (Get-Command py -ErrorAction SilentlyContinue).Source
if (-not $py) { throw 'Falta Python 3.11 o superior. Instálalo desde python.org (marca "Add to PATH") y repite.' }
& $py -3 -c "import sys; assert sys.version_info >= (3, 11), sys.version"
if ($LASTEXITCODE -ne 0) { throw 'Se necesita Python 3.11 o superior.' }
if (-not (Test-Path "$raiz\.venv")) { & $py -3 -m venv "$raiz\.venv" }
$python = "$raiz\.venv\Scripts\python.exe"
& $python -m pip install --quiet --disable-pip-version-check -r "$raiz\requirements.txt"
if ($LASTEXITCODE -ne 0) { throw 'No se pudieron instalar las dependencias.' }

Write-Host '2/4 Creando la base de prueba...' -ForegroundColor Cyan
Push-Location $raiz
try { & $python -m bm.prueba --db $db --clave $Clave } finally { Pop-Location }
if ($LASTEXITCODE -ne 0) { throw 'No se pudo crear la base de prueba.' }

$cf = Join-Path $datos 'cloudflared.exe'
if (-not (Test-Path $cf)) {
    Write-Host '   Descargando cloudflared (una sola vez)...'
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    Invoke-WebRequest 'https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe' -OutFile $cf -UseBasicParsing
}

Write-Host "3/4 Arrancando BM en el puerto $Puerto..." -ForegroundColor Cyan
# Lo que quedara abierto de un intento anterior (cerrado a medias) ocupa el puerto: cerrarlo.
$pids = "$datos\prueba.pids"
if (Test-Path $pids) {
    Get-Content $pids | ForEach-Object { Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue }
    Remove-Item $pids
}
$env:BM_DB = $db
$servidor = Start-Process $python -ArgumentList "-m bm.servidor --puerto $Puerto --db `"$db`"" -WorkingDirectory $raiz `
    -WindowStyle Hidden -PassThru -RedirectStandardOutput "$datos\prueba-servidor.log" -RedirectStandardError "$datos\prueba-servidor.err"
$tunel = $null
try {
    $servidor.Id | Set-Content $pids
    $listo = $false
    foreach ($i in 1..60) {
        if ($servidor.HasExited) { break }
        $c = New-Object Net.Sockets.TcpClient
        try { $c.Connect('127.0.0.1', $Puerto); $listo = $true } catch { } finally { $c.Close() }
        if ($listo) { break }
        Write-Host -NoNewline '.'
        Start-Sleep 1
    }
    Write-Host ''
    if (-not $listo) {
        Write-Host 'BM no ha arrancado. Esto es lo que dice:' -ForegroundColor Red
        Get-Content "$datos\prueba-servidor.err" -Tail 25 -ErrorAction SilentlyContinue
        throw 'BM no arranca (mensaje de arriba).'
    }

    Write-Host '4/4 Abriendo el enlace https...' -ForegroundColor Cyan
    $log = "$datos\prueba-tunel.log"
    Remove-Item $log -ErrorAction SilentlyContinue
    $tunel = Start-Process $cf -ArgumentList "tunnel --no-autoupdate --url http://127.0.0.1:$Puerto" `
        -WindowStyle Hidden -PassThru -RedirectStandardError $log -RedirectStandardOutput "$datos\prueba-tunel.out"
    $servidor.Id, $tunel.Id | Set-Content $pids
    $url = $null
    foreach ($i in 1..60) {
        Start-Sleep 1
        if (Test-Path $log) {
            # cloudflared tiene el fichero abierto: leerlo en modo compartido
            $f = [IO.File]::Open($log, 'Open', 'Read', 'ReadWrite')
            try { $texto = (New-Object IO.StreamReader($f)).ReadToEnd() } finally { $f.Close() }
            $m = [regex]::Matches($texto, 'https://[a-z0-9-]+\.trycloudflare\.com') | Where-Object { $_.Value -ne 'https://api.trycloudflare.com' } | Select-Object -First 1
            if ($m) { $url = $m.Value; break }
        }
    }
    if (-not $url) { throw "No se pudo abrir el enlace. Mira $log" }
    try { Set-Clipboard $url } catch {}

    Write-Host ''
    Write-Host "  Abre en el móvil:  $url" -ForegroundColor Green
    Write-Host '  (copiado al portapapeles; tarda unos segundos en funcionar la primera vez)'
    Write-Host ''
    Write-Host "  Usuarios (contraseña $Clave): dueno, admin, jefe, cocina, comandero"
    Write-Host '  En el iPhone: Safari -> Compartir -> Añadir a pantalla de inicio, para usarla como app.'
    Write-Host ''
    Read-Host 'Pulsa Enter para cerrar BM y el enlace'
} finally {
    if ($tunel -and -not $tunel.HasExited) { Stop-Process -Id $tunel.Id -Force }
    if ($servidor -and -not $servidor.HasExited) { Stop-Process -Id $servidor.Id -Force }
    Remove-Item $pids -ErrorAction SilentlyContinue
    Write-Host 'Cerrado. Los datos de prueba quedan en datos\prueba.sqlite (bórralo para empezar de cero).'
}
