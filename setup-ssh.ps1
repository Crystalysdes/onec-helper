# setup-ssh.ps1 — One-time SSH key setup for VPS (run once, then deploy.ps1 works without password)

$VPS_HOST = "89.169.1.192"
$VPS_USER = "root"
$KEY_PATH = "$env:USERPROFILE\.ssh\id_ed25519"
$PUB_KEY_PATH = "$KEY_PATH.pub"

Write-Host "`n==> SSH Key Setup for VPS $VPS_HOST" -ForegroundColor Cyan

# Generate key if it doesn't exist
if (-not (Test-Path $PUB_KEY_PATH)) {
    Write-Host "    Generating SSH key..." -ForegroundColor Yellow
    & "C:\Windows\System32\OpenSSH\ssh-keygen.exe" -t ed25519 -f $KEY_PATH -N '""' -C "deploy@onec-helper"
}

$pubkey = (Get-Content $PUB_KEY_PATH).Trim()
Write-Host "    Public key: $pubkey" -ForegroundColor Gray
Write-Host ""
Write-Host "    Copying key to VPS (you will be prompted for password ONCE)..." -ForegroundColor Yellow
Write-Host ""

$cmd = "mkdir -p ~/.ssh && echo '$pubkey' >> ~/.ssh/authorized_keys && sort -u ~/.ssh/authorized_keys -o ~/.ssh/authorized_keys && chmod 700 ~/.ssh && chmod 600 ~/.ssh/authorized_keys && echo 'SSH key added!'"
& "C:\Windows\System32\OpenSSH\ssh.exe" -o StrictHostKeyChecking=no "${VPS_USER}@${VPS_HOST}" $cmd

if ($LASTEXITCODE -eq 0) {
    Write-Host "`n==> Done! From now on run: .\deploy.ps1" -ForegroundColor Green
} else {
    Write-Host "`n    Failed. Check VPS host and password." -ForegroundColor Red
}
