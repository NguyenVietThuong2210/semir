#!/bin/bash
# =============================================================================
# migrate_rbac.sh
# Run ONCE on PROD after deploying the RBAC feature.
#
# Usage:  bash scripts/migrate_rbac.sh
# =============================================================================
set -e

echo "======================================================"
echo " RBAC Migration — SemirDashboard"
echo "======================================================"

echo ""
echo "[1/3] Running schema migration (Role + UserProfile tables)..."
docker compose exec -T web python manage.py migrate App

echo ""
echo "[2/3] Seeding roles and assigning users..."
docker compose exec -T web python manage.py perm sync

echo ""
echo "[3/3] System check..."
docker compose exec -T web python manage.py check

echo ""
echo "======================================================"
echo " Done. Verify with:"
echo "   docker compose exec web python manage.py perm show"
echo "======================================================"
