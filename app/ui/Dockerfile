# The UI is static files for now; Caddy serves them. Replace with the real
# build when the streaming interface lands (Milestone 3).
FROM caddy:2-alpine

COPY app/ui/static /usr/share/caddy
COPY app/ui/Caddyfile /etc/caddy/Caddyfile

EXPOSE 80
