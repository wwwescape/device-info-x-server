# Wraps the stock coturn image with this project's turnserver.conf baked
# in, so a self-hoster pulling wwwescape/device-info-x-server-coturn from
# Docker Hub never needs this repo's coturn/ directory on disk.
# Deployment-specific values (realm, server-name, static-auth-secret,
# relay port range) still come from docker-compose.yml's CLI args, sourced
# from .env — see the `coturn` service.
FROM coturn/coturn:4.6-alpine

COPY coturn/turnserver.conf /etc/coturn/turnserver.conf
