#!/bin/bash
set -e

echo "🚀 Starting deployment..."

cd /home/semir/semir

# Pull latest code
echo "📥 Pulling latest code from git..."
git pull origin main

# Build new images
echo "🔨 Building Docker images..."
docker compose build --no-cache web

# Stop old containers
echo "🛑 Stopping old containers..."
docker compose down

# Start new containers
echo "▶️  Starting new containers..."
docker compose up -d

# Wait for database
echo "⏳ Waiting for database..."
sleep 10

# Run migrations
echo "🗄️  Running database migrations..."
docker compose exec -T web python manage.py migrate

# Sync role permissions (safe to run on every deploy)
echo "🔐 Syncing role permissions..."
docker compose exec -T web python manage.py perm sync

# Collect static files
echo "📦 Collecting static files..."
docker compose exec -T web python manage.py collectstatic --noinput

# Check health
echo "🏥 Checking service health..."
docker compose ps

echo ""
echo "Deployment completed successfully!"
echo "🌐 Visit: https://analytics-customer-dashboard.com"
echo ""
echo "📊 View logs: docker compose logs -f web"