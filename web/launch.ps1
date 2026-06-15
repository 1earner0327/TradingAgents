$ErrorActionPreference = "Stop"

$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
$Web = Join-Path $Root "web"
$Url = "http://127.0.0.1:5173/"
$BackendUrl = "http://127.0.0.1:8765/api/config"
$Log = Join-Path $Web "launcher.log"

function Write-LauncherLog {
    param([string]$Message)
    $stamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    Add-Content -Path $Log -Value "[$stamp] $Message" -Encoding UTF8
}

function Show-LauncherError {
    param([string]$Message)
    Write-LauncherLog "ERROR: $Message"
    try {
        $shell = New-Object -ComObject WScript.Shell
        [void]$shell.Popup($Message, 0, "TradingAgents Web", 48)
    } catch {
        Write-LauncherLog "Unable to show popup: $($_.Exception.Message)"
    }
}

function Test-HttpReady {
    param(
        [string]$TargetUrl,
        [int]$TimeoutSeconds = 1
    )
    try {
        Invoke-WebRequest -Uri $TargetUrl -UseBasicParsing -TimeoutSec $TimeoutSeconds | Out-Null
        return $true
    } catch {
        return $false
    }
}

function Wait-HttpReady {
    param(
        [string]$TargetUrl,
        [int]$TimeoutSeconds = 45
    )
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        if (Test-HttpReady -TargetUrl $TargetUrl -TimeoutSeconds 2) {
            return $true
        }
        Start-Sleep -Seconds 1
    }
    return $false
}

try {
    Write-LauncherLog "Launcher started."

    $Python = Join-Path $Root ".venv\Scripts\python.exe"
    if (-not (Test-Path $Python)) {
        $Python = "python"
    }

    if (-not (Test-HttpReady -TargetUrl $BackendUrl -TimeoutSeconds 2)) {
        Write-LauncherLog "Starting backend."
        Start-Process `
            -FilePath $Python `
            -ArgumentList @("-u", "web\server.py") `
            -WorkingDirectory $Root `
            -RedirectStandardOutput (Join-Path $Web "backend.log") `
            -RedirectStandardError (Join-Path $Web "backend.err.log") `
            -WindowStyle Hidden
    } else {
        Write-LauncherLog "Backend already running."
    }

    if (-not (Test-Path (Join-Path $Web "node_modules"))) {
        Write-LauncherLog "node_modules missing; running npm install."
        $install = Start-Process `
            -FilePath "npm.cmd" `
            -ArgumentList @("install") `
            -WorkingDirectory $Web `
            -RedirectStandardOutput (Join-Path $Web "npm-install.log") `
            -RedirectStandardError (Join-Path $Web "npm-install.err.log") `
            -WindowStyle Hidden `
            -PassThru
        $install.WaitForExit()
        if ($install.ExitCode -ne 0) {
            throw "npm install failed. See web\npm-install.err.log."
        }
    }

    if (-not (Test-HttpReady -TargetUrl $Url -TimeoutSeconds 2)) {
        Write-LauncherLog "Starting frontend."
        Start-Process `
            -FilePath "npm.cmd" `
            -ArgumentList @("run", "dev", "--", "--host", "127.0.0.1", "--port", "5173") `
            -WorkingDirectory $Web `
            -RedirectStandardOutput (Join-Path $Web "vite.log") `
            -RedirectStandardError (Join-Path $Web "vite.err.log") `
            -WindowStyle Hidden
    } else {
        Write-LauncherLog "Frontend already running."
    }

    $backendReady = Wait-HttpReady -TargetUrl $BackendUrl -TimeoutSeconds 45
    $frontendReady = Wait-HttpReady -TargetUrl $Url -TimeoutSeconds 45

    if (-not $backendReady) {
        throw "Backend did not become ready. See web\backend.err.log."
    }
    if (-not $frontendReady) {
        throw "Frontend did not become ready. See web\vite.err.log."
    }

    Write-LauncherLog "Opening browser."
    Start-Process $Url
} catch {
    Show-LauncherError $_.Exception.Message
}
