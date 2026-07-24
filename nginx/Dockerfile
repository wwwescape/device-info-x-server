# Wraps the stock nginx image with this project's config baked in, so a
# self-hoster pulling wwwescape/device-info-x-server-nginx from Docker Hub
# never needs this repo's nginx/ directory on disk — no clone, no manual
# file copying. DOMAIN is still substituted into the template at container
# start (nginx's built-in envsubst-on-templates entrypoint), unaffected by
# whether the template came from a bind mount or, as here, a COPY.
FROM nginx:1.27-alpine

COPY nginx/nginx.conf /etc/nginx/nginx.conf
COPY nginx/templates /etc/nginx/templates
