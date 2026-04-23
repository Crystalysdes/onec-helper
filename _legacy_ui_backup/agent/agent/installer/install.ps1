<#
.SYNOPSIS
  1C Helper -- installer for the Desktop Bridge Agent (Kontur.Market browser automation).

.DESCRIPTION
  Installs the agent into %LOCALAPPDATA%\net1c-agent:
   * downloads portable Python if no Python 3.10+ is available system-wide
   * downloads agent code from <ServerUrl>/api/v1/agent/package.zip
   * creates venv, installs dependencies, downloads Chromium via Playwright
   * writes prepair.json with the pairing code so agent auto-pairs on first run
   * creates Desktop shortcut and startup entry
   * launches the agent

.PARAMETER PairingCode
  One-time code from net1c.ru settings page.

.PARAMETER ServerUrl
  Base URL of the net1c server. Defaults to https://net1c.ru.
#>
param(
    [Parameter(Mandatory=$true)][string]$PairingCode,
    [string]$ServerUrl = 'https://net1c.ru'
)

$ErrorActionPreference = 'Stop'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

function Write-Step($msg) { Write-Host "==> $msg" -ForegroundColor Cyan }
function Write-OK  ($msg) { Write-Host "[OK] $msg" -ForegroundColor Green }
function Write-Warn($msg) { Write-Host "[!!] $msg" -ForegroundColor Yellow }
function Write-Err ($msg) { Write-Host "[XX] $msg" -ForegroundColor Red }

Write-Host ""
Write-Host "+-----------------------------------------------+" -ForegroundColor Magenta
Write-Host "|  1C Helper - Agent installer (Kontur.Market)  |" -ForegroundColor Magenta
Write-Host "+-----------------------------------------------+" -ForegroundColor Magenta
Write-Host ""

$InstallDir  = Join-Path $env:LOCALAPPDATA 'net1c-agent'
$ConfigDir   = Join-Path $env:APPDATA     'net1c-agent'
$VenvDir     = Join-Path $InstallDir 'venv'
$AgentDir    = Join-Path $InstallDir 'app'
$PortablePy  = Join-Path $InstallDir 'python'

# -- 0. Clean up previous installation -----------------------------------------
Write-Step "Cleaning up any previous installation"

# 0a. Stop running agent processes (python.exe under our install dir)
try {
    $old = Get-Process -ErrorAction SilentlyContinue | Where-Object {
        $_.Path -and $_.Path.StartsWith($InstallDir, [System.StringComparison]::OrdinalIgnoreCase)
    }
    foreach ($p in $old) {
        Write-OK ("Stopping old process PID {0}: {1}" -f $p.Id, $p.ProcessName)
        Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue
    }
    if ($old) { Start-Sleep -Seconds 2 }  # give handles time to release
} catch { }

# 0b. Remove install dir contents (venv, python, app, launchers)
if (Test-Path $InstallDir) {
    try {
        Remove-Item "$InstallDir\*" -Recurse -Force -ErrorAction Stop
        Write-OK "Cleared $InstallDir"
    } catch {
        Write-Warn "Could not fully clean $InstallDir (some files locked). Continuing anyway."
    }
}

# 0c. Remove old config + logs (pairing token is invalid anyway on re-install)
#     KEEP browser-profile/ so Kontur.Market login session survives reinstall
if (Test-Path $ConfigDir) {
    foreach ($item in @('config.json', 'prepair.json', 'logs', 'agent.log')) {
        $p = Join-Path $ConfigDir $item
        if (Test-Path $p) {
            Remove-Item $p -Recurse -Force -ErrorAction SilentlyContinue
        }
    }
    Write-OK "Cleared old config ($ConfigDir)"
}

# 0d. Remove old shortcuts (they point to now-deleted launcher)
$oldShortcuts = @(
    (Join-Path ([Environment]::GetFolderPath('Desktop')) '1C Helper Agent.lnk'),
    (Join-Path ([Environment]::GetFolderPath('Startup')) '1C Helper Agent.lnk')
)
foreach ($s in $oldShortcuts) {
    if (Test-Path $s) { Remove-Item $s -Force -ErrorAction SilentlyContinue }
}

Write-Step "Preparing folders"
New-Item -ItemType Directory -Force -Path $InstallDir, $ConfigDir, $AgentDir | Out-Null
Write-OK  "Install dir: $InstallDir"
Write-OK  "Config dir:  $ConfigDir"

# -- 1. Ensure Python 3.10 / 3.11 / 3.12 ---------------------------------------
# We reject 3.13+ because several deps (e.g. greenlet) often lack prebuilt wheels
# for very new Python, which would force users to install Visual C++ Build Tools.
Write-Step "Looking for Python 3.10 / 3.11 / 3.12"
$python = $null
foreach ($cand in @('python', 'py', 'python3')) {
    try {
        $output = & $cand --version 2>&1
        if ($LASTEXITCODE -eq 0 -and $output -match 'Python 3\.(\d+)') {
            $minor = [int]$Matches[1]
            if ($minor -ge 10 -and $minor -le 12) {
                $python = $cand
                Write-OK "Using system Python: $output"
                break
            } elseif ($minor -ge 13) {
                Write-Warn "System has $output -- too new for some C-extensions. Will use portable 3.11 instead."
            }
        }
    } catch { }
}

$script:UsePortable = $false
if (-not $python) {
    Write-Warn "Downloading portable Python 3.11.9 (~15 MB)..."
    $pyVersion  = '3.11.9'
    $pyZipUrl   = "https://www.python.org/ftp/python/$pyVersion/python-$pyVersion-embed-amd64.zip"
    $pyZipFile  = Join-Path $InstallDir 'python-embed.zip'

    Invoke-WebRequest -Uri $pyZipUrl -OutFile $pyZipFile -UseBasicParsing
    New-Item -ItemType Directory -Force -Path $PortablePy | Out-Null
    Expand-Archive -Path $pyZipFile -DestinationPath $PortablePy -Force
    Remove-Item $pyZipFile -Force

    # Enable 'import site' so pip can be bootstrapped
    $pth = Get-ChildItem -Path $PortablePy -Filter 'python*._pth' -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($pth) {
        (Get-Content $pth.FullName) -replace '#\s*import\s+site', 'import site' | Set-Content $pth.FullName
    }

    $getPip = Join-Path $InstallDir 'get-pip.py'
    Invoke-WebRequest -Uri 'https://bootstrap.pypa.io/get-pip.py' -OutFile $getPip -UseBasicParsing

    $portablePyExe = Join-Path $PortablePy 'python.exe'
    & $portablePyExe $getPip --quiet
    Remove-Item $getPip -Force -ErrorAction SilentlyContinue

    # Portable Python can't run 'python -m venv' (no ensurepip). Use the interpreter directly
    # as the "system" Python and skip venv creation -- install deps straight into portable's site-packages.
    $python = $portablePyExe
    Write-OK "Portable Python ready: $portablePyExe"
    $script:UsePortable = $true
}

# -- 2. Download agent code -----------------------------------------------------
Write-Step "Downloading agent code"
$agentZip = Join-Path $InstallDir 'agent.zip'
try {
    Invoke-WebRequest -Uri "$ServerUrl/api/v1/agent/package.zip" -OutFile $agentZip -UseBasicParsing
} catch {
    Write-Err "Failed to download agent package from $ServerUrl"
    throw
}

if (Test-Path $AgentDir) { Remove-Item "$AgentDir\*" -Recurse -Force -ErrorAction SilentlyContinue }
Expand-Archive -Path $agentZip -DestinationPath $AgentDir -Force
Remove-Item $agentZip -Force
Write-OK "Code extracted: $AgentDir"

# -- 3. Create venv (or use portable) -------------------------------------------
if ($UsePortable) {
    Write-Step "Using portable Python directly (venv not supported in embeddable build)"
    $Py = $python
    $Pyw = Join-Path (Split-Path $python) 'pythonw.exe'
    if (-not (Test-Path $Pyw)) { $Pyw = $Py }  # fallback
} else {
    Write-Step "Creating virtual environment"
    & $python -m venv $VenvDir
    $Py = Join-Path $VenvDir 'Scripts\python.exe'
    $Pyw = Join-Path $VenvDir 'Scripts\pythonw.exe'
    if (-not (Test-Path $Py)) { throw "venv creation failed" }
    if (-not (Test-Path $Pyw)) { $Pyw = $Py }
    Write-OK "venv ready"
}

# -- 4. Install Python dependencies ---------------------------------------------
Write-Step "Installing Python dependencies (1-2 min)"
& $Py -m pip install --upgrade pip --quiet
# --prefer-binary: try wheels first; only compile from source if no wheel exists at all
& $Py -m pip install --prefer-binary -r (Join-Path $AgentDir 'requirements.txt')
if ($LASTEXITCODE -ne 0) {
    Write-Err "pip install failed."
    Write-Err "This usually means a dependency has no prebuilt wheel for your Python version."
    Write-Err "Run the installer again -- it will download portable Python 3.11 which has all wheels available."
    # Mark system Python unusable so on next run we skip it
    $python = $null
    throw "pip install failed"
}
Write-OK "Dependencies installed"

# -- 5. Download Chromium -------------------------------------------------------
Write-Step "Downloading Chromium browser (~130 MB, 2-3 min)"
& $Py -m playwright install chromium
if ($LASTEXITCODE -ne 0) { Write-Warn "playwright install returned non-zero; continuing anyway" }
Write-OK "Browser ready"

# -- 6. Save pairing config for auto-pair on first run --------------------------
Write-Step "Saving pairing config"
$prepair = [ordered]@{
    server_url        = $ServerUrl
    pending_pair_code = $PairingCode
}
$prepairFile = Join-Path $ConfigDir 'prepair.json'
$prepair | ConvertTo-Json | Out-File -FilePath $prepairFile -Encoding UTF8
Write-OK "Pairing code saved (will be used on first launch)"

# -- 7. Create launcher (pythonw = GUI, no console window) ---------------------
# GUI launcher -- double-click opens the Qt window; no black CMD box.
# We use a .cmd wrapper that invokes pythonw via `start` so the wrapper exits
# immediately, leaving only the GUI process visible.
$launcher = Join-Path $InstallDir 'Start-Agent.cmd'
$launcherContent = @"
@echo off
start "" /D "$AgentDir" "$Pyw" main.py
"@
[System.IO.File]::WriteAllText($launcher, $launcherContent, [System.Text.Encoding]::ASCII)

# -- 8. Desktop shortcut + startup entry ----------------------------------------
Write-Step "Creating shortcuts"
$WshShell = New-Object -ComObject WScript.Shell

$desktop = [Environment]::GetFolderPath('Desktop')
$scPath  = Join-Path $desktop '1C Helper Agent.lnk'
$sc = $WshShell.CreateShortcut($scPath)
$sc.TargetPath = $Pyw
$sc.Arguments = '"main.py"'
$sc.WorkingDirectory = $AgentDir
$sc.IconLocation = 'shell32.dll,21'
$sc.Description = 'net1c Helper agent for Kontur.Market'
$sc.WindowStyle = 1   # Normal window
$sc.Save()

$startup = [Environment]::GetFolderPath('Startup')
$suPath  = Join-Path $startup '1C Helper Agent.lnk'
$su = $WshShell.CreateShortcut($suPath)
$su.TargetPath = $Pyw
$su.Arguments = '"main.py"'
$su.WorkingDirectory = $AgentDir
$su.IconLocation = 'shell32.dll,21'
$su.Description = 'net1c Helper agent auto-start'
$su.WindowStyle = 7   # Minimized (will go straight to tray)
$su.Save()
Write-OK "Shortcuts: Desktop + Startup"

# -- 9. Finish & launch ---------------------------------------------------------
Write-Host ""
Write-Host "+=================================================+" -ForegroundColor Green
Write-Host "|  Agent installed successfully!                  |" -ForegroundColor Green
Write-Host "+=================================================+" -ForegroundColor Green
Write-Host "|  Launching agent GUI now...                     |" -ForegroundColor Green
Write-Host "|  Chromium will open - log into Kontur.Market    |" -ForegroundColor Green
Write-Host "|  manually ONCE. Session is saved afterwards.    |" -ForegroundColor Green
Write-Host "+=================================================+" -ForegroundColor Green
Write-Host ""

# Launch the GUI directly via pythonw (no intermediate console)
Start-Process -FilePath $Pyw -ArgumentList 'main.py' -WorkingDirectory $AgentDir
