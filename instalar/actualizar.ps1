# Actualiza BM a la última versión sin tocar los datos. Ejecutar como administrador:
#   powershell -ExecutionPolicy Bypass -File instalar\actualizar.ps1
$ErrorActionPreference = 'Stop'
$raiz = (Resolve-Path "$PSScriptRoot\..").Path
$python = "$raiz\.venv\Scripts\python.exe"
# La carpeta de datos es la que usa la tarea programada (argumento --db)
$tarea = (Get-ScheduledTask -TaskName 'BM servidor').Actions[0].Arguments
if ($tarea -match '--db "([^"]+)"') { $env:BM_DB = $Matches[1] }

Write-Host 'Copia de seguridad antes de actualizar...' -ForegroundColor Cyan
& $python -c "from bm import copias, db; print(copias.hacer(db.connect(), 'antes_de_actualizar'))"

Stop-ScheduledTask -TaskName 'BM servidor' -ErrorAction SilentlyContinue
if (Test-Path "$raiz\.git") {
    git -C $raiz pull --ff-only
    if ($LASTEXITCODE -ne 0) { throw 'git pull falló: revisa la carpeta antes de seguir.' }
} else {
    Write-Host 'Sin git: copia la carpeta nueva encima (sin borrar "datos") y vuelve a ejecutar este script.'
}
& $python -m pip install --quiet -r "$raiz\requirements.txt"
& $python -m unittest discover -s "$raiz\bm\tests" -t $raiz
if ($LASTEXITCODE -ne 0) { Write-Warning 'Algún test ha fallado. BM se arranca igualmente; avisa al responsable.' }
Start-ScheduledTask -TaskName 'BM servidor'
Write-Host 'BM actualizado y en marcha.' -ForegroundColor Green
