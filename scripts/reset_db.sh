#!/bin/bash
# Script to reset the database and regenerate fresh data

set -e

echo "Resetting GCIDE dictionary database..."

# Option 1: Drop Docker volume (cleanest, complete reset)
if [ "$1" == "--full" ]; then
    echo "Stopping containers..."
    docker-compose down
    
    echo "Removing database volume..."
    # Try common volume name patterns
    docker volume rm xnillio_postgres_data 2>/dev/null || \
    docker volume rm $(docker volume ls -q | grep postgres) 2>/dev/null || \
    echo "No postgres volume found or already removed"
    
    echo "Starting containers (will auto-download and process data)..."
    docker-compose up -d
    
    echo "Waiting for database to be ready..."
    sleep 5
    
    echo "Database reset complete! The API will automatically download and process the GCIDE data on startup."
    echo "This may take several minutes. Check logs with: docker-compose logs -f api"
    
# Option 2: Just drop tables (faster, keeps container)
else
    echo "Dropping all tables in existing database..."
    
    # Get database credentials from .env or use defaults
    DB_HOST=${DB_HOST:-localhost}
    DB_PORT=${DB_PORT:-5432}
    DB_NAME=${DB_NAME:-gcide}
    DB_USER=${DB_USER:-xnillio}
    DB_PASSWORD=${DB_PASSWORD:-xnillio}
    
    # Drop tables using psql via Docker
    docker-compose exec -T db psql -U "$DB_USER" -d "$DB_NAME" <<EOF
DROP TABLE IF EXISTS word_links CASCADE;
DROP TABLE IF EXISTS words CASCADE;
EOF
    
    echo "Tables dropped. Restarting API to regenerate data..."
    docker-compose restart api
    
    echo "Database reset complete! The API will automatically process the GCIDE data on startup."
    echo "Check logs with: docker-compose logs -f api"
fi

