#!/bin/bash
# Quick script to check database issues

DB_HOST=${DB_HOST:-localhost}
DB_PORT=${DB_PORT:-5432}
DB_NAME=${DB_NAME:-gcide}
DB_USER=${DB_USER:-xnillio}
DB_PASSWORD=${DB_PASSWORD:-xnillio}

echo "Checking database for issues..."
echo ""

# Check total word count
docker-compose exec -T db psql -U "$DB_USER" -d "$DB_NAME" <<EOF
SELECT COUNT(*) as total_words FROM words;
SELECT COUNT(*) as words_starting_with_a FROM words WHERE word LIKE 'A%';
SELECT word, length(word) as word_len 
FROM words 
WHERE word LIKE 'A%' 
ORDER BY length(word) DESC 
LIMIT 10;
EOF

