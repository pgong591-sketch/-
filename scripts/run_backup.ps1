$ErrorActionPreference = "Stop"

$appDir = Resolve-Path (Join-Path $PSScriptRoot "..")
$runtimeDir = "E:\finance_dw_runtime"
$runtimeData = Join-Path $runtimeDir "data"
$runtimeTemp = Join-Path $runtimeData "incoming"
$runtimeDb = Join-Path $runtimeData "finance_dw.db"
$backupDir = Join-Path $runtimeDir "backups"

@($runtimeDir, $runtimeTemp, $runtimeData, $backupDir) | ForEach-Object {
    New-Item -ItemType Directory -Force -Path $_ | Out-Null
}

$env:TEMP = $runtimeTemp
$env:TMP = $runtimeTemp
$env:FINANCE_DW_DB_PATH = $runtimeDb

$pythonCandidates = @(
    (Join-Path $appDir ".venv\Scripts\python.exe"),
    "E:\finance_dw_runtime\.venv\Scripts\python.exe",
    "C:\Python314\python.exe",
    "python"
)

$pythonExe = foreach ($candidate in $pythonCandidates) {
    if ($candidate -eq "python" -or (Test-Path $candidate)) {
        $candidate
        break
    }
}

if (-not $pythonExe) {
    throw "Python runtime not found."
}

& $pythonExe (Join-Path $appDir "scripts\backup_database.py") `
    --db $runtimeDb `
    --out-dir $backupDir `
    --keep 30
