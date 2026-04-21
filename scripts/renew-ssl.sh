#!/bin/bash
# =============================================================================
# renew-ssl.sh — SSL certificate renewal for analytics-customer-dashboard.com
#
# Usage:  sudo bash scripts/renew-ssl.sh
# Schedule (crontab on prod — runs at 3 AM daily, certbot skips if not due):
#   0 3 * * * sudo bash /home/semir/semir/scripts/renew-ssl.sh >> /home/semir/logs/ssl.log 2>&1
#
# Why stop nginx:
#   Certbot standalone mode needs port 80 free to complete the ACME challenge.
#   We stop nginx, renew, copy the new certs, then restart nginx.
#
# Cert paths:
#   System (certbot):  /etc/letsencrypt/live/analytics-customer-dashboard.com/
#   Project (nginx):   /home/semir/semir/certbot/conf/live/analytics-customer-dashboard.com/
# =============================================================================
set -e

DOMAIN="analytics-customer-dashboard.com"
PROJECT_DIR="/home/semir/semir"
COMPOSE="docker compose -f $PROJECT_DIR/docker-compose.yml"
CERT_DEST="$PROJECT_DIR/certbot/conf"

echo "======================================================"
echo " SemirDashboard — SSL Renewal"
echo " $(date '+%Y-%m-%d %H:%M:%S')"
echo "======================================================"

# Stop nginx to free port 80 for certbot ACME challenge
echo ""
echo "[1/4] Stopping nginx..."
$COMPOSE stop nginx

# Run certbot renewal (--quiet suppresses output if no renewal needed)
echo ""
echo "[2/4] Running certbot renewal..."
sudo certbot renew --quiet

if [ $? -eq 0 ]; then
    echo "  -> Certificate renewed (or already up to date)"

    # Copy renewed certs from system certbot dir to project dir
    # nginx container reads from the project dir (mounted as volume)
    echo ""
    echo "[3/4] Copying renewed certificates to project dir..."
    sudo cp -rL /etc/letsencrypt/live/$DOMAIN/* $CERT_DEST/live/$DOMAIN/
    sudo cp -r  /etc/letsencrypt/archive/*       $CERT_DEST/archive/ 2>/dev/null || true
    sudo chown -R semir:semir $CERT_DEST
    echo "  -> Certs copied to $CERT_DEST"
else
    echo "  -> Certbot renewal failed — starting nginx back up"
    $COMPOSE start nginx
    exit 1
fi

# Restart nginx to pick up the new certificates
echo ""
echo "[4/4] Restarting nginx..."
$COMPOSE start nginx

echo ""
echo "======================================================"
echo " SSL renewal completed!"
EXPIRY=$(sudo certbot certificates 2>/dev/null | grep "Expiry Date" | head -1 | awk '{print $3, $4}')
echo " $DOMAIN expiry: ${EXPIRY:-run 'sudo certbot certificates' to check}"
echo "======================================================"
