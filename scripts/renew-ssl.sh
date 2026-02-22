#!/bin/bash

echo "🔒 Starting SSL certificate renewal..."

# Stop nginx to free port 80
docker compose -f /home/semir/semir/docker-compose.yml stop nginx

# Renew certificates
sudo certbot renew --quiet

if [ $? -eq 0 ]; then
    echo "Certificate renewed successfully"
    
    # Copy renewed certificates
    sudo cp -r /etc/letsencrypt/live/analytics-customer-dashboard.com/* /home/semir/semir/certbot/conf/live/analytics-customer-dashboard.com/
    sudo cp -r /etc/letsencrypt/archive/* /home/semir/semir/certbot/conf/archive/ 2>/dev/null || true
    sudo chown -R semir:semir /home/semir/semir/certbot
    
    echo "📋 Certificate copied to project directory"
else
    echo " Certificate renewal failed"
fi

# Start nginx
docker compose -f ~/semir/docker-compose.yml start nginx

echo "SSL renewal process completed"
echo "📅 Next renewal: $(sudo certbot certificates | grep 'Expiry Date')"