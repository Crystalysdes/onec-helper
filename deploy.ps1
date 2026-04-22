# deploy.ps1 — Direct deploy to VPS (no GitHub Actions needed)
# Usage: .\deploy.ps1
#        .\deploy.ps1 -Message "my commit message"
#        .\deploy.ps1 -SkipCommit     (don't commit/push, just redeploy current server code)
#        .\deploy.ps1 -VerifyOnly     (skip deploy, just run health checks)

param(
    [string]$Message = "",
    [switch]$SkipCommit = $false,
    [switch]$VerifyOnly = $false
)

$ErrorActionPreference = "Continue"

$VPS_HOST = "89.169.1.192"
$VPS_USER = "root"
$VPS = "$VPS_USER@$VPS_HOST"
$SSH_KEY = "$env:USERPROFILE\.ssh\id_ed25519"
$SSH_EXE = "C:\Windows\System32\OpenSSH\ssh.exe"

function Write-Step($text) { Write-Host "`n==> $text" -ForegroundColor Cyan }
function Write-OK($text)   { Write-Host "    [OK] $text" -ForegroundColor Green }
function Write-Warn($text) { Write-Host "    [!!] $text" -ForegroundColor Yellow }
function Write-Err($text)  { Write-Host "    [XX] $text" -ForegroundColor Red }

# ── Helper: invoke SSH with key, return exit code ─────────────────────────────
function Invoke-Ssh($cmd, [switch]$AllowFail) {
    $args = @(
        "-o", "StrictHostKeyChecking=no",
        "-o", "ConnectTimeout=15",
        "-o", "BatchMode=yes",
        "-i", $SSH_KEY,
        $VPS,
        $cmd
    )
    & $SSH_EXE @args
    $code = $LASTEXITCODE
    if ($code -ne 0 -and -not $AllowFail) {
        Write-Err "SSH command failed (exit $code)"
    }
    return $code
}

# ── 0. Ensure SSH key exists + is authorized on VPS ───────────────────────────
function Ensure-SshAuth {
    $pub = "$SSH_KEY.pub"
    if (-not (Test-Path $pub)) {
        Write-Warn "No SSH key found. Generating new ed25519 key..."
        & "C:\Windows\System32\OpenSSH\ssh-keygen.exe" -t ed25519 -f $SSH_KEY -N '""' -C "deploy@onec-helper" | Out-Null
    }

    # Quick test — does the key work?
    $testOut = & $SSH_EXE -o StrictHostKeyChecking=no -o ConnectTimeout=10 -o BatchMode=yes -i $SSH_KEY $VPS "echo READY" 2>&1
    if ($LASTEXITCODE -eq 0 -and $testOut -match 'READY') {
        Write-OK "SSH key authorized"
        return $true
    }

    Write-Warn "SSH key not authorized on VPS. Running one-time setup (you will be asked for password ONCE)..."
    $pubkey = (Get-Content $pub).Trim()
    $setupCmd = "mkdir -p ~/.ssh && echo '$pubkey' >> ~/.ssh/authorized_keys && sort -u ~/.ssh/authorized_keys -o ~/.ssh/authorized_keys && chmod 700 ~/.ssh && chmod 600 ~/.ssh/authorized_keys && echo OK"
    & $SSH_EXE -o StrictHostKeyChecking=no "${VPS_USER}@${VPS_HOST}" $setupCmd
    if ($LASTEXITCODE -ne 0) {
        Write-Err "Could not set up SSH key. Try running .\setup-ssh.ps1 manually."
        return $false
    }
    # Verify
    $verify = & $SSH_EXE -o StrictHostKeyChecking=no -o BatchMode=yes -i $SSH_KEY $VPS "echo READY" 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-OK "SSH key now authorized"
        return $true
    }
    Write-Err "Setup appeared successful but key still rejected"
    return $false
}

# ── Health checks ─────────────────────────────────────────────────────────────
function Test-Site {
    Write-Step "Running health checks..."
    $ok = $true
    $urls = @(
        @{ url = "https://net1c.ru/"; name = "Frontend" }
        @{ url = "https://net1c.ru/api/v1/agent/info"; name = "Backend API" }
    )
    foreach ($u in $urls) {
        try {
            $r = Invoke-WebRequest -Uri $u.url -UseBasicParsing -TimeoutSec 15
            if ($r.StatusCode -eq 200) {
                Write-OK "$($u.name): HTTP $($r.StatusCode)"
            } else {
                Write-Warn "$($u.name): HTTP $($r.StatusCode)"
                $ok = $false
            }
        } catch {
            Write-Err "$($u.name): $($_.Exception.Message)"
            $ok = $false
        }
    }
    return $ok
}

if ($VerifyOnly) {
    Test-Site | Out-Null
    exit 0
}

# ── 1. Commit local changes ───────────────────────────────────────────────────
if (-not $SkipCommit) {
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

    # ── 2. Push to GitHub (source of truth) ──────────────────────────────────
    Write-Step "Pushing to GitHub..."
    git push origin main
    if ($LASTEXITCODE -ne 0) { Write-Err "git push failed"; exit 1 }
    Write-OK "Pushed to GitHub"
}

# ── 3. Ensure SSH works ───────────────────────────────────────────────────────
Write-Step "Checking SSH access to $VPS_HOST..."
if (-not (Ensure-SshAuth)) {
    exit 1
}

# ── 4. Deploy on VPS ──────────────────────────────────────────────────────────
Write-Step "Deploying on VPS..."
$deployScript = @'
set -e
cd /app
echo '[1/4] git pull...'
git pull origin main
echo '[2/4] docker compose down...'
docker compose -f docker-compose.timeweb.yml down
sync && echo 3 > /proc/sys/vm/drop_caches 2>/dev/null || true
echo '[3/4] docker compose build + start (BUILDKIT=0)...'
DOCKER_BUILDKIT=0 docker compose -f docker-compose.timeweb.yml up -d --build
echo '[4/4] prune old images...'
docker image prune -f
echo ''
echo 'Deploy script finished.'
'@

$rc = Invoke-Ssh $deployScript -AllowFail
if ($rc -ne 0) {
    Write-Err "Remote deploy failed (exit $rc). Check output above."
    Write-Host ""
    Write-Host "    Last 40 lines of backend logs:" -ForegroundColor Yellow
    Invoke-Ssh "docker compose -f /app/docker-compose.timeweb.yml logs --tail=40 backend 2>&1" -AllowFail | Out-Null
    exit $rc
}

# ── 5. Wait for container to stabilize, then verify ──────────────────────────
Write-Step "Waiting 8s for containers to stabilize..."
Start-Sleep -Seconds 8

if (Test-Site) {
    Write-Host ""
    Write-Host "==> Deploy complete! https://net1c.ru" -ForegroundColor Green
} else {
    Write-Host ""
    Write-Warn "Deploy finished but health checks failed. Showing backend logs:"
    Invoke-Ssh "docker compose -f /app/docker-compose.timeweb.yml logs --tail=60 backend 2>&1" -AllowFail | Out-Null
    exit 1
}
