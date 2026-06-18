$ErrorActionPreference = "SilentlyContinue"

$appDir = Resolve-Path (Join-Path $PSScriptRoot "..")
$appUrl = "http://localhost:8501/"
$appWindowWidth = 1600
$appWindowHeight = 980

$runtimeDir = "E:\finance_dw_runtime"
$runtimeData = Join-Path $runtimeDir "data"
$runtimeTemp = Join-Path $runtimeData "incoming"
$runtimeDb = Join-Path $runtimeData "finance_dw.db"
$sourceDb = Join-Path $appDir "data\finance_dw.db"

@($runtimeDir, $runtimeTemp, $runtimeData) | ForEach-Object {
    New-Item -ItemType Directory -Force -Path $_ | Out-Null
}

$env:TEMP = $runtimeTemp
$env:TMP = $runtimeTemp
$env:FINANCE_DW_DB_PATH = $runtimeDb
$env:STREAMLIT_BROWSER_GATHER_USAGE_STATS = "false"

if ((-not (Test-Path $runtimeDb)) -and (Test-Path $sourceDb)) {
    Copy-Item -LiteralPath $sourceDb -Destination $runtimeDb -Force
}

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

$backupMarker = Join-Path $runtimeDir "last_launch_backup.txt"
$today = Get-Date -Format "yyyyMMdd"
$lastBackup = if (Test-Path $backupMarker) { Get-Content -LiteralPath $backupMarker -ErrorAction SilentlyContinue } else { "" }
if ($lastBackup -ne $today -and (Test-Path $runtimeDb)) {
    powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $appDir "scripts\run_backup.ps1") | Out-Null
    Set-Content -LiteralPath $backupMarker -Value $today
}

function Test-AppPort {
    try {
        $client = New-Object Net.Sockets.TcpClient
        $task = $client.ConnectAsync("127.0.0.1", 8501)
        $ready = $task.Wait(250)
        $client.Close()
        return $ready
    } catch {
        return $false
    }
}

function Open-App {
    $browserCandidates = @(
        "$env:ProgramFiles\Microsoft\Edge\Application\msedge.exe",
        "${env:ProgramFiles(x86)}\Microsoft\Edge\Application\msedge.exe",
        "$env:LOCALAPPDATA\Microsoft\Edge\Application\msedge.exe",
        "$env:ProgramFiles\Google\Chrome\Application\chrome.exe",
        "${env:ProgramFiles(x86)}\Google\Chrome\Application\chrome.exe",
        "$env:LOCALAPPDATA\Google\Chrome\Application\chrome.exe"
    )
    $browserExe = foreach ($candidate in $browserCandidates) {
        if ($candidate -and (Test-Path $candidate)) {
            $candidate
            break
        }
    }

    if ($browserExe) {
        $browserInfo = [System.Diagnostics.ProcessStartInfo]::new()
        $browserInfo.FileName = $browserExe
        $browserInfo.Arguments = "--app=$appUrl --window-size=$appWindowWidth,$appWindowHeight --window-position=80,40"
        $browserInfo.UseShellExecute = $true
        [System.Diagnostics.Process]::Start($browserInfo) | Out-Null
    } else {
        $urlInfo = [System.Diagnostics.ProcessStartInfo]::new()
        $urlInfo.FileName = $appUrl
        $urlInfo.UseShellExecute = $true
        [System.Diagnostics.Process]::Start($urlInfo) | Out-Null
    }
}

if (Test-AppPort) {
    Open-App
    exit 0
}

$streamlitInfo = [System.Diagnostics.ProcessStartInfo]::new()
$streamlitInfo.FileName = $pythonExe
$streamlitInfo.Arguments = "-m streamlit run app.py --server.port 8501 --server.headless true --server.fileWatcherType none --browser.gatherUsageStats false"
$streamlitInfo.WorkingDirectory = $appDir
$streamlitInfo.WindowStyle = [System.Diagnostics.ProcessWindowStyle]::Hidden
$streamlitInfo.UseShellExecute = $true
[System.Diagnostics.Process]::Start($streamlitInfo) | Out-Null

for ($i = 0; $i -lt 80; $i++) {
    if (Test-AppPort) {
        Open-App
        exit 0
    }
    Start-Sleep -Milliseconds 250
}

Open-App
