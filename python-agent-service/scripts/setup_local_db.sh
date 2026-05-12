#!/bin/bash
# Setup Local PostgreSQL for SecManus
# Prerequisites: PostgreSQL installed
# Usage: ./scripts/setup_local_db.sh

set -e
DB_NAME="secmanus"
DB_USER="postgres"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INIT_SCRIPT="$SCRIPT_DIR/db/init_local_db.sql"

echo "SecManus Local DB Setup"
echo "======================="

echo ""
echo "1. Creating database '$DB_NAME' (if not exists)..."
if psql -U "$DB_USER" -d postgres -tc "SELECT 1 FROM pg_database WHERE datname = '$DB_NAME'" | grep -q 1; then
    echo "   Database already exists."
else
    createdb -U "$DB_USER" "$DB_NAME"
    echo "   Database created."
fi

echo ""
echo "2. Running init_local_db.sql..."
psql -U "$DB_USER" -d "$DB_NAME" -f "$INIT_SCRIPT"
echo "   Done."

echo ""
echo "3. Verify .env has:"
echo "   DATABASE_MODE=local"
echo "   LOCAL_DB_HOST=localhost"
echo "   LOCAL_DB_PORT=5432"
echo "   LOCAL_DB_NAME=$DB_NAME"
echo "   LOCAL_DB_USER=$DB_USER"
echo "   LOCAL_DB_PASSWORD=postgres"

echo ""
echo "Setup complete. Restart the backend and register a new user."
