#!/bin/bash
BACKUP_DIR=/home/semir/backups
DATE=$(date +%Y%m%d_%H%M%S)

mkdir -p $BACKUP_DIR

echo "🔄 Starting backup at $DATE..."

# Backup database
echo "📊 Backing up database..."
docker compose -f ~/semir/docker-compose.yml exec -T db pg_dump -U semir_user semir_db | gzip > $BACKUP_DIR/db_$DATE.sql.gz

if [ $? -eq 0 ]; then
    echo "✅ Database backup completed: db_$DATE.sql.gz"
else
    echo "❌ Database backup failed!"
    exit 1
fi

# Backup media files
echo "📁 Backing up media files..."
if [ -d ~/semir/SemirDashboard/media ]; then
    tar -czf $BACKUP_DIR/media_$DATE.tar.gz -C ~/semir/SemirDashboard media
    echo "✅ Media backup completed: media_$DATE.tar.gz"
fi

# Keep only last 7 days of backups
echo "🗑️  Cleaning old backups (keeping last 7 days)..."
find $BACKUP_DIR -type f -mtime +7 -delete

echo ""
echo "✅ Backup completed successfully!"
echo "📦 Backup location: $BACKUP_DIR"
ls -lh $BACKUP_DIR | tail -5