# deploy.ps1 — Direct deploy to VPS (no GitHub Actions needed)
# Usage: .\deploy.ps1
#        .\deploy.ps1 -Message "my commit message"

param(
    [string]$Message = ""
)

$VPS_HOST = "217.198.13.160"
$VPS_USER = "root"
$VPS = "$VPS_USER@$VPS_HOST"
$SSH_KEY = "$env:USERPROFILE\.ssh\id_ed25519"

function Write-Step($text) { Write-Host "`n==> $text" -ForegroundColor Cyan }
function Write-OK($text)   { Write-Host "    $text" -ForegroundColor Green }
function Write-Err($text)  { Write-Host "    ERROR: $text" -ForegroundColor Red }

# ── 1. Commit local changes ───────────────────────────────────────────────────
Write-Step "Committing local changes..."
git add -A
$status = git status --porcelain
if ($status) {
    if (-not $Message) { $Message = "deploy: $(Get-Date -Format 'yyyy-MM-dd HH:mm')" }
    git commit -m $Message
    Write-OK "Committed: $Message"
} else {
    Write-OK "Nothing to commit, working tree clean"
}

# ── 2. Push to GitHub (source of truth) ──────────────────────────────────────
Write-Step "Pushing to GitHub..."
git push origin main
if ($LASTEXITCODE -ne 0) { Write-Err "git push failed"; exit 1 }
Write-OK "Pushed to GitHub"

# ── 3. SSH to VPS and deploy ──────────────────────────────────────────────────
Write-Step "Connecting to VPS $VPS_HOST..."

$sshArgs = @(
    "-o", "StrictHostKeyChecking=no",
    "-o", "ConnectTimeout=15",
    "-o", "BatchMode=yes"
)
if (Test-Path $SSH_KEY) { $sshArgs += @("-i", $SSH_KEY) }

$deployScript = @"
set -e
cd /app
echo '[1/4] git pull...'
git pull origin main
echo '[2/4] docker compose down...'
docker compose -f docker-compose.timeweb.yml down
sync && echo 3 > /proc/sys/vm/drop_caches
echo '[3/4] docker compose build + start (BUILDKIT=0)...'
DOCKER_BUILDKIT=0 docker compose -f docker-compose.timeweb.yml up -d --build
echo '[4/4] prune old images...'
docker image prune -f
echo ''
echo 'Deploy complete! https://net1c.ru'
"@

$sshArgs += @($VPS, $deployScript)
& "C:\Windows\System32\OpenSSH\ssh.exe" @sshArgs

if ($LASTEXITCODE -ne 0) {
    Write-Err "SSH connection failed."
    Write-Host ""
    Write-Host "  If this is your first time, run setup first:" -ForegroundColor Yellow
    Write-Host "  .\setup-ssh.ps1" -ForegroundColor Yellow
    exit 1
}

Write-OK "Site live at https://net1c.ru"
