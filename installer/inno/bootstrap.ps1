# bootstrap.ps1 -- runs inside the Inno Setup [Run] step.
# Extracts portable Python, installs dependencies, installs Chromium,
# and writes prepair.json with the pairing code (parsed from installer filename by .iss).
#
# Called by Inno Setup with these parameters:
#   -InstallDir "<{app}>"   -- absolute path where the installer put our files
#   -PairingCode "<CODE>"   -- optional 8-char code from filename (may be empty)
#   -ServerUrl "<URL>"      -- server URL (defaults to https://net1c.ru)

param(
    [Parameter(Mandatory=$true)][string]$InstallDir,
    [string]$PairingCode = '',
    [string]$ServerUrl = 'https://net1c.ru'
)

$ErrorActionPreference = 'Stop'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

function Log($msg) {
    $stamp = (Get-Date -Format 'HH:mm:ss')
    "$stamp  $msg" | Out-File -Append -FilePath (Join-Path $InstallDir 'bootstrap.log') -Encoding UTF8
}

try {
    Log "Bootstrap started. InstallDir=$InstallDir, PairingCode=$PairingCode"

    $PortablePy = Join-Path $InstallDir 'python'
    $PyZip      = Join-Path $InstallDir 'python-3.11.9-embed-amd64.zip'
    $GetPip     = Join-Path $InstallDir 'get-pip.py'
    $AgentDir   = Join-Path $InstallDir 'app'
    $ConfigDir  = Join-Path $env:APPDATA 'net1c-agent'

    # -- 1. Extract embedded Python --------------------------------------------
    Log "Extracting Python to $PortablePy"
    if (Test-Path $PortablePy) {
        Remove-Item "$PortablePy\*" -Recurse -Force -ErrorAction SilentlyContinue
    } else {
        New-Item -ItemType Directory -Force -Path $PortablePy | Out-Null
    }
    # Use .NET ZipFile for reliable extraction on non-ASCII paths (e.g. Cyrillic usernames)
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    [System.IO.Compression.ZipFile]::ExtractToDirectory($PyZip, $PortablePy)

    $PyExe  = Join-Path $PortablePy 'python.exe'
    $PywExe = Join-Path $PortablePy 'pythonw.exe'
    if (-not (Test-Path $PyExe))  { throw "Python exe not found at $PyExe after extraction" }
    if (-not (Test-Path $PywExe)) { throw "pythonw.exe not found at $PywExe after extraction" }

    # Rewrite python*._pth so the embedded Python can find:
    #   - its stdlib (python311.zip, .)
    #   - site-packages installed by pip
    #   - the agent source folder (..\app, relative to python.exe)
    #   - 'import site' so get-pip / pip work
    # NOTE: the default ._pth ships in ISOLATED mode which does NOT add the
    # script's own directory to sys.path, so we must list '..\app' explicitly,
    # otherwise `pythonw.exe main.py` fails with ModuleNotFoundError and exits
    # silently (this is exactly what made the installer look broken).
    $pthFile = Get-ChildItem -Path $PortablePy -Filter 'python*._pth' | Select-Object -First 1
    if (-not $pthFile) { throw "python*._pth not found in $PortablePy" }
    @(
        'python311.zip',
        '.',
        'Lib\site-packages',
        '..\app',
        '',
        'import site'
    ) | Set-Content -Path $pthFile.FullName -Encoding ASCII
    Log "Rewrote $($pthFile.Name) with agent sys.path entries"

    # -- 2. Bootstrap pip ------------------------------------------------------
    Log "Bootstrapping pip..."
    & $PyExe $GetPip --quiet --no-warn-script-location 2>&1 | Out-File -Append -FilePath (Join-Path $InstallDir 'bootstrap.log') -Encoding UTF8
    if ($LASTEXITCODE -ne 0) { throw "get-pip.py failed (exit $LASTEXITCODE)" }

    # -- 3. Install dependencies ----------------------------------------------
    Log "Installing agent dependencies..."
    & $PyExe -m pip install --prefer-binary --no-warn-script-location -r (Join-Path $AgentDir 'requirements.txt') 2>&1 `
        | Out-File -Append -FilePath (Join-Path $InstallDir 'bootstrap.log') -Encoding UTF8
    if ($LASTEXITCODE -ne 0) { throw "pip install failed (exit $LASTEXITCODE). See bootstrap.log" }

    # -- 4. Download Chromium via Playwright ----------------------------------
    Log "Installing Playwright Chromium..."
    & $PyExe -m playwright install chromium 2>&1 | Out-File -Append -FilePath (Join-Path $InstallDir 'bootstrap.log') -Encoding UTF8
    if ($LASTEXITCODE -ne 0) { Log "playwright install returned non-zero; continuing" }

    # -- 5. Write prepair.json so GUI auto-pairs on first run ------------------
    New-Item -ItemType Directory -Force -Path $ConfigDir | Out-Null
    if ($PairingCode) {
        $prepair = [ordered]@{
            server_url        = $ServerUrl
            pending_pair_code = $PairingCode
        }
        $prepair | ConvertTo-Json | Out-File -FilePath (Join-Path $ConfigDir 'prepair.json') -Encoding UTF8
        Log "Wrote prepair.json with code $PairingCode"
    } else {
        Log "No pairing code in filename; user will need to paste it in the GUI manually."
    }

    # -- 6. Smoke test: verify the agent can actually be imported -------------
    # If this fails, the installer will report an error instead of "install OK"
    # followed by a silent no-op on double-click.
    Log "Running import smoke test..."
    $smoke = @'
import sys, importlib
sys.path.insert(0, r"{0}")
for m in ("config", "client", "runner", "gui", "PySide6.QtWidgets", "httpx", "playwright"):
    importlib.import_module(m)
print("OK")
'@ -f $AgentDir
    $smokeOut = & $PyExe -c $smoke 2>&1
    $smokeOut | Out-File -Append -FilePath (Join-Path $InstallDir 'bootstrap.log') -Encoding UTF8
    if ($LASTEXITCODE -ne 0) { throw "Smoke test failed: $smokeOut" }
    Log "Smoke test passed."

    Log "Bootstrap complete."
    exit 0
} catch {
    Log "ERROR: $_"
    Log $_.ScriptStackTrace
    # Exit with non-zero so Inno Setup reports failure
    exit 1
}
