#!/bin/bash
# One-time VPS setup script for Timeweb Cloud (Ubuntu 22.04)
# Run as root: bash vps-setup.sh YOUR_DOMAIN
set -e

DOMAIN=${1:-"YOUR_DOMAIN"}
REPO="https://github.com/Crystalysdes/onec-helper.git"
APP_DIR="/opt/onec-helper"

echo "=== Installing Docker ==="
apt-get update -q
apt-get install -y docker.io docker-compose-v2 git certbot nginx python3-certbot-nginx curl

systemctl enable docker
systemctl start docker

echo "=== Cloning repo ==="
git clone "$REPO" "$APP_DIR" || (cd "$APP_DIR" && git pull)

echo "=== Getting SSL certificate ==="
# Temporarily allow port 80 through Nginx for certbot challenge
systemctl stop nginx 2>/dev/null || true
certbot certonly --standalone -d "$DOMAIN" --non-interactive --agree-tos -m admin@${DOMAIN}
systemctl start nginx 2>/dev/null || true

echo "=== Replacing YOUR_DOMAIN in nginx config ==="
sed -i "s/YOUR_DOMAIN/$DOMAIN/g" "$APP_DIR/nginx/nginx.prod.conf"

echo "=== Setting up auto-renew for SSL ==="
(crontab -l 2>/dev/null; echo "0 3 * * * certbot renew --quiet && docker compose -f $APP_DIR/docker-compose.prod.yml restart nginx") | crontab -

echo "=== Setting up SSH key for GitHub Actions ==="
SSH_KEY_FILE="/root/.ssh/github_deploy"
ssh-keygen -t ed25519 -C "github-actions-deploy" -f "$SSH_KEY_FILE" -N ""
echo ""
echo ">>> Add this PUBLIC key to your VPS authorized_keys (already done below):"
cat "${SSH_KEY_FILE}.pub" >> /root/.ssh/authorized_keys
echo ""
echo ">>> Add this PRIVATE key as GitHub Secret VPS_SSH_KEY:"
echo "------------------------------------------------------------"
cat "$SSH_KEY_FILE"
echo "------------------------------------------------------------"
echo ""
echo ">>> Also add these GitHub Secrets:"
echo "  VPS_HOST = $(curl -s ifconfig.me)"
echo "  VPS_USER = root"
echo ""
echo "=== Done! Now:"
echo "1. Copy .env file to $APP_DIR/.env"
echo "2. Run: cd $APP_DIR && docker compose -f docker-compose.prod.yml up -d"
