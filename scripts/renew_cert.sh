#!/bin/sh
# Manually trigger a certificate renewal check and reload Nginx if it
# renewed. The `certbot` service already does this automatically every 12h
# — this script is for testing or forcing a renewal on demand.
set -e

docker compose exec certbot certbot renew --webroot -w /var/www/certbot
docker compose exec nginx nginx -s reload

echo "Renewal check complete; Nginx reloaded."
