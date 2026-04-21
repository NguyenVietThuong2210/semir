#!/bin/bash
# =============================================================================
# deploy.sh — Full deployment script for SemirDashboard
#
# Usage:  bash scripts/deploy.sh
# Run on: Production server (/home/semir/semir/)
#
# Steps:
#   1. Pull latest code from git (main branch)
#   2. Rebuild the web Docker image
#   3. Restart all containers
#   4. Run DB migrations
#   5. Sync role permissions (safe to run repeatedly)
#   6. Collect static files
# =============================================================================
set -e  # Exit immediately on any error

PROJECT_DIR="/home/semir/semir"
COMPOSE="docker compose -f $PROJECT_DIR/docker-compose.yml"

echo "======================================================"
echo " SemirDashboard — Deployment"
echo " $(date '+%Y-%m-%d %H:%M:%S')"
echo "======================================================"

cd $PROJECT_DIR

# Pull latest code from main branch
echo ""
echo "[1/6] Pulling latest code..."
git pull origin main

# Rebuild only the web service image (skip redis/db/nginx — unchanged)
echo ""
echo "[2/6] Building web image..."
$COMPOSE build --no-cache web

# Bring down all containers cleanly, then start fresh
echo ""
echo "[3/6] Restarting containers..."
$COMPOSE down
$COMPOSE up -d

# Wait for PostgreSQL to be ready before running migrations
echo ""
echo "[4/6] Waiting for database to be ready..."
sleep 10

# Apply any pending Django migrations
echo ""
echo "[5/6] Running database migrations..."
$COMPOSE exec -T web python manage.py migrate

# Sync PERMISSION_DEFS → Role.permissions in DB (idempotent, safe every deploy)
echo ""
echo "[5b/6] Syncing role permissions..."
$COMPOSE exec -T web python manage.py perm sync

# Collect static files into STATIC_ROOT for WhiteNoise/nginx to serve
echo ""
echo "[6/6] Collecting static files..."
$COMPOSE exec -T web python manage.py collectstatic --noinput

# Final health check
echo ""
echo "[OK] Container status:"
$COMPOSE ps

echo ""
echo "======================================================"
echo " Deployment completed successfully!"
echo " https://analytics-customer-dashboard.com"
echo ""
echo " Useful commands:"
echo "   docker compose logs -f web          # App logs"
echo "   docker compose logs -f nginx        # Nginx logs"
echo "   docker compose exec web python manage.py shell"
echo "======================================================"
