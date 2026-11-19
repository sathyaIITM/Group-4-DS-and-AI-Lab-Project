# The UI is one static page (app/ui/static/index.html) that streams answers from the API
# (/api/stream) and draws charts with Vega-Lite; Caddy serves it.
FROM caddy:2-alpine

COPY app/ui/static /usr/share/caddy
COPY app/ui/Caddyfile /etc/caddy/Caddyfile

EXPOSE 80
