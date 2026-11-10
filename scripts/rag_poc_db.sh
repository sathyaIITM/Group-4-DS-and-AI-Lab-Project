#!/usr/bin/env bash
# Local Postgres with pgvector for the RAG proof of concept, bound to 127.0.0.1:5433.
# Same image and init script as the Compose `db` service; credentials come from .env.
set -euo pipefail
cd "$(dirname "$0")/.."
set -a; . ./.env; set +a
name=india-analyst-rag-poc-db
if docker ps -a --format '{{.Names}}' | grep -qx "$name"; then
  docker start "$name" >/dev/null
else
  docker run -d --name "$name" \
    -e POSTGRES_USER="${POSTGRES_USER:-analyst}" -e POSTGRES_PASSWORD="$POSTGRES_PASSWORD" \
    -e POSTGRES_DB="${POSTGRES_DB:-analyst}" -p 127.0.0.1:"${RAG_POC_DB_PORT:-5433}":5432 \
    -v "$PWD/infra/db/init:/docker-entrypoint-initdb.d:ro" pgvector/pgvector:pg16 >/dev/null
fi
echo "$name running on 127.0.0.1:${RAG_POC_DB_PORT:-5433}"
