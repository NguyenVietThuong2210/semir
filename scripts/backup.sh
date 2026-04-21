#!/bin/bash
# =============================================================================
# backup.sh — Database and media backup for SemirDashboard
#
# Usage:  bash scripts/backup.sh
# Schedule (crontab on prod):
#   0 2 * * * bash /home/semir/semir/scripts/backup.sh >> /home/semir/logs/backup.log 2>&1
#
# What it does:
#   1. Dump PostgreSQL database → gzipped .sql.gz
#   2. Archive media/ folder → .tar.gz (if exists)
#   3. Delete backups older than 7 days
#
# Backup location: /home/semir/backups/
# Retention: 7 days
# =============================================================================
set -e

BACKUP_DIR=/home/semir/backups
DATE=$(date +%Y%m%d_%H%M%S)
COMPOSE="docker compose -f /home/semir/semir/docker-compose.yml"

mkdir -p $BACKUP_DIR

echo "======================================================"
echo " SemirDashboard — Backup"
echo " $(date '+%Y-%m-%d %H:%M:%S')"
echo "======================================================"

# Dump PostgreSQL via the running db container
# semir_user / semir_db must match docker-compose.yml env vars
echo ""
echo "[1/3] Backing up database..."
$COMPOSE exec -T db pg_dump -U semir_user semir_db | gzip > $BACKUP_DIR/db_$DATE.sql.gz
echo "  -> db_$DATE.sql.gz ($(du -sh $BACKUP_DIR/db_$DATE.sql.gz | cut -f1))"

# Archive media files only if the directory exists
# (media/ stores user-uploaded files, not tracked in git)
echo ""
echo "[2/3] Backing up media files..."
MEDIA_DIR=/home/semir/semir/SemirDashboard/media
if [ -d "$MEDIA_DIR" ]; then
    tar -czf $BACKUP_DIR/media_$DATE.tar.gz -C /home/semir/semir/SemirDashboard media
    echo "  -> media_$DATE.tar.gz ($(du -sh $BACKUP_DIR/media_$DATE.tar.gz | cut -f1))"
else
    echo "  -> No media/ directory found, skipping."
fi

# Remove backups older than 7 days to keep disk usage in check
echo ""
echo "[3/3] Cleaning old backups (retention: 7 days)..."
DELETED=$(find $BACKUP_DIR -type f -mtime +7 -print -delete | wc -l)
echo "  -> Removed $DELETED old file(s)"

echo ""
echo "======================================================"
echo " Backup completed successfully!"
echo " Location: $BACKUP_DIR"
ls -lh $BACKUP_DIR | tail -6
echo "======================================================"
