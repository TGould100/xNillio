#!/bin/bash
# Full database reset - removes volume and regenerates everything

echo "Performing full database reset..."
echo "This will DELETE all existing database data!"

read -p "Are you sure? (yes/no): " confirm
if [ "$confirm" != "yes" ]; then
    echo "Cancelled."
    exit 1
fi

echo "Stopping containers..."
docker-compose down

echo "Removing database volume..."
docker volume rm xnillio_postgres_data

echo "Starting containers (will auto-download and process data)..."
docker-compose up --build

echo ""
echo "✓ Database volume removed and containers restarted"
echo "The API will automatically detect empty DB and regenerate data."
echo "Monitor progress with: docker-compose logs -f api"

