#!/usr/bin/env bash
# gt-init — Bootstrap script. Run once. Never touch credentials again.
set -e

ROOT="$(cd "$(dirname "$0")" && pwd)"
ENV_FILE="$ROOT/.env"

# Generate secure random values
DB_PASS=$(openssl rand -hex 16 2>/dev/null || echo "strongpass")
JWT_SECRET=$(openssl rand -hex 32 2>/dev/null || echo "dev-jwt-secret-gt-2026")
HMAC_SECRET=$(openssl rand -hex 32 2>/dev/null || echo "dev-hmac-secret-gt-2026")

# Only create .env if it doesn't exist — never overwrite
if [ ! -f "$ENV_FILE" ]; then
    cat > "$ENV_FILE" <<EOF
DB_PASSWORD=$DB_PASS
MINIO_PASSWORD=minioadmin
JWT_SECRET=$JWT_SECRET
HMAC_SECRET=$HMAC_SECRET
SEGMENTATION_MODE=progressive
SEGMENTATION_REINERT=true
EOF
    echo "✅ .env created at $ENV_FILE"
else
    echo "⏭  .env already exists — skipping"
fi

# Alembic .env
BACKEND_ENV="$ROOT/backend/.env"
if [ ! -f "$BACKEND_ENV" ]; then
    cat > "$BACKEND_ENV" <<EOF
DATABASE_URL=postgresql+asyncpg://app_user:${DB_PASS}@127.0.0.1:5433/gt-db
DB_PASSWORD=$DB_PASS
JWT_SECRET_KEY=$JWT_SECRET
CELERY_HMAC_SECRET=$HMAC_SECRET
EOF
    echo "✅ backend/.env created"
fi

# Build and run
echo ""
echo "🚀 Building and starting..."
docker compose build base
docker compose build
docker compose up -d

echo ""
echo "✅ Done. http://localhost:3000"
echo "   docker compose watch  # for hot reload"
