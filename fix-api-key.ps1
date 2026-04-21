# fix-api-key.ps1 — Set OPENROUTER_API_KEY on VPS and restart app
# Run this in YOUR OWN PowerShell (not inside Windsurf)

$VPS_HOST = "89.169.1.192"
$VPS_USER = "root"

Write-Host "`n=== Fix AI API Key on VPS ===" -ForegroundColor Cyan
Write-Host ""

# Ask for VPS root password
$pass = Read-Host "Enter VPS root password (from Timeweb panel)" -AsSecureString
$bstr = [System.Runtime.InteropServices.Marshal]::SecureStringToBSTR($pass)
$plainPass = [System.Runtime.InteropServices.Marshal]::PtrToStringAuto($bstr)

# Ask for API key
Write-Host ""
Write-Host "Get your OpenRouter key at: https://openrouter.ai/keys" -ForegroundColor Yellow
$apiKey = Read-Host "Enter your OPENROUTER_API_KEY (starts with sk-or-v1-)"

if (-not $apiKey.StartsWith("sk-")) {
    Write-Host "ERROR: Key should start with sk-" -ForegroundColor Red
    exit 1
}

# Check if plink (PuTTY) is available
$plink = Get-Command plink -ErrorAction SilentlyContinue

if ($plink) {
    Write-Host "`nConnecting via plink..." -ForegroundColor Cyan
    $cmd = @"
grep -q 'OPENROUTER_API_KEY=' /app/.env && sed -i 's|^OPENROUTER_API_KEY=.*|OPENROUTER_API_KEY=$apiKey|' /app/.env || echo 'OPENROUTER_API_KEY=$apiKey' >> /app/.env
cd /app && docker compose -f docker-compose.timeweb.yml restart app
echo 'DONE'
"@
    echo "y" | plink -pw $plainPass "${VPS_USER}@${VPS_HOST}" $cmd
} else {
    Write-Host "`nplink not found. Creating SSH batch script..." -ForegroundColor Yellow
    
    # Write a temp expect-style script using net use or just give instructions
    $tmpScript = [System.IO.Path]::GetTempFileName() + ".ps1"
    @"
# Auto-generated, delete after use
`$env:SSHPASS = '$plainPass'
ssh -o StrictHostKeyChecking=no ${VPS_USER}@${VPS_HOST} @"
grep -q 'OPENROUTER_API_KEY=' /app/.env && sed -i 's|^OPENROUTER_API_KEY=.*|OPENROUTER_API_KEY=$apiKey|' /app/.env || echo 'OPENROUTER_API_KEY=$apiKey' >> /app/.env
cd /app && docker compose -f docker-compose.timeweb.yml restart app
echo DONE
"@
"@ | Set-Content $tmpScript

    Write-Host "`nSSH doesn't support non-interactive passwords without plink." -ForegroundColor Red
    Write-Host ""
    Write-Host "=== RUN THESE COMMANDS MANUALLY IN YOUR TERMINAL ===" -ForegroundColor Green
    Write-Host ""
    Write-Host "1. Connect:" -ForegroundColor White
    Write-Host "   ssh root@89.169.1.192" -ForegroundColor Yellow
    Write-Host "   Password: $plainPass" -ForegroundColor Gray
    Write-Host ""
    Write-Host "2. After login, run:" -ForegroundColor White
    Write-Host "   sed -i 's|^OPENROUTER_API_KEY=.*||' /app/.env" -ForegroundColor Yellow
    Write-Host "   echo 'OPENROUTER_API_KEY=$apiKey' >> /app/.env" -ForegroundColor Yellow
    Write-Host "   cd /app && docker compose -f docker-compose.timeweb.yml restart app" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "3. Test AI status at:" -ForegroundColor White
    Write-Host "   https://net1c.ru/api/v1/products/ai-status" -ForegroundColor Yellow
}

Write-Host "`nDone! AI invoice recognition should work now." -ForegroundColor Green
