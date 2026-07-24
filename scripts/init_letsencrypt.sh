#!/bin/sh
# One-time Let's Encrypt certificate issuance via the webroot HTTP-01
# challenge. Run this once, after `docker compose up -d nginx` (nginx must
# already be serving port 80 so certbot's challenge requests reach it) and
# before the `certbot` service's renewal loop has anything to renew.
#
# Usage: ./scripts/init_letsencrypt.sh <domain> <email>
set -e

if [ -z "$1" ] || [ -z "$2" ]; then
  echo "Usage: $0 <domain> <email>"
  exit 1
fi

DOMAIN="$1"
EMAIL="$2"

docker compose run --rm --entrypoint certbot certbot certonly \
  --webroot -w /var/www/certbot \
  -d "$DOMAIN" \
  --email "$EMAIL" \
  --agree-tos \
  --no-eff-email \
  --non-interactive

echo "Certificate issued for $DOMAIN. Restart Nginx to pick it up: docker compose restart nginx"
