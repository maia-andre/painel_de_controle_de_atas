#!/usr/bin/env bash
# Backup do banco do painel via docker compose (pg_dump).
# Uso: ./scripts/backup.sh [arquivo_saida.sql]
# Restaurar: cat arquivo.sql | docker compose exec -T db psql -U "$POSTGRES_USER" "$POSTGRES_DB"
set -euo pipefail

cd "$(dirname "$0")/.."

# Carrega POSTGRES_USER/DB do .env (com defaults iguais ao docker-compose.yml).
[ -f .env ] && set -a && . ./.env && set +a
USER_DB="${POSTGRES_USER:-painel}"
NAME_DB="${POSTGRES_DB:-atas}"

OUT="${1:-backup_atas_$(date +%Y%m%d_%H%M%S).sql}"

docker compose exec -T db pg_dump -U "$USER_DB" "$NAME_DB" > "$OUT"
echo "Backup salvo em: $OUT"
