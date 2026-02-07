#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEPLOY_DIR="$(dirname "$SCRIPT_DIR")"
cd "$DEPLOY_DIR"

BACKUP_DIR="${DEPLOY_DIR}/backups"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="${BACKUP_DIR}/bloasis_${TIMESTAMP}.sql.gz"

mkdir -p "$BACKUP_DIR"

echo "💾 Backing up PostgreSQL..."

docker-compose exec -T postgres pg_dump -U postgres bloasis | gzip > "$BACKUP_FILE"

echo "✅ Backup saved to: $BACKUP_FILE"

# Keep only last 7 backups
echo "🧹 Cleaning old backups (keeping last 7)..."
ls -t "$BACKUP_DIR"/*.sql.gz 2>/dev/null | tail -n +8 | xargs -r rm -f

echo "📊 Current backups:"
ls -lh "$BACKUP_DIR"/*.sql.gz 2>/dev/null || echo "No backups found"
