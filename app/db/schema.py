"""
Optimized database schema for GCIDE dictionary.

Design decisions:
1. Words table - normalized with lowercase index for fast lookups
2. Word links table - pre-computed relationships to avoid on-the-fly extraction
3. Indexes - optimized for common query patterns
4. Separate tables - allows efficient updates and queries
"""

SCHEMA_SQL = """
-- Main words table
CREATE TABLE IF NOT EXISTS words (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    word TEXT NOT NULL,                    -- Original case word
    word_lower TEXT NOT NULL,               -- Lowercase for fast lookups
    definition TEXT NOT NULL,               -- Full definition text
    definition_length INTEGER,              -- Cached length for filtering
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    CONSTRAINT words_word_unique UNIQUE (word),
    CONSTRAINT words_word_lower_unique UNIQUE (word_lower)
);

-- Word relationships (edges in the definition graph)
-- Pre-computed to avoid expensive on-the-fly extraction
CREATE TABLE IF NOT EXISTS word_links (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_word_id INTEGER NOT NULL,        -- Word that contains the link
    target_word_id INTEGER NOT NULL,       -- Word referenced in definition
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    CONSTRAINT word_links_unique UNIQUE (source_word_id, target_word_id),
    CONSTRAINT word_links_source_fk FOREIGN KEY (source_word_id) 
        REFERENCES words(id) ON DELETE CASCADE,
    CONSTRAINT word_links_target_fk FOREIGN KEY (target_word_id) 
        REFERENCES words(id) ON DELETE CASCADE
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_words_word ON words(word);
CREATE INDEX IF NOT EXISTS idx_words_word_lower ON words(word_lower);
CREATE INDEX IF NOT EXISTS idx_words_definition_length ON words(definition_length);
CREATE INDEX IF NOT EXISTS idx_words_word_lower_prefix ON words(word_lower);

-- Word links indexes - critical for graph queries
CREATE INDEX IF NOT EXISTS idx_word_links_source ON word_links(source_word_id);
CREATE INDEX IF NOT EXISTS idx_word_links_target ON word_links(target_word_id);
CREATE INDEX IF NOT EXISTS idx_word_links_both ON word_links(source_word_id, target_word_id);

-- Full-text search index (SQLite FTS5) - for advanced definition searches
CREATE VIRTUAL TABLE IF NOT EXISTS words_fts USING fts5(
    word,
    definition,
    content='words',
    content_rowid='id'
);

-- Trigger to maintain FTS index
CREATE TRIGGER IF NOT EXISTS words_fts_insert AFTER INSERT ON words BEGIN
    INSERT INTO words_fts(rowid, word, definition)
    VALUES (new.id, new.word, new.definition);
END;

CREATE TRIGGER IF NOT EXISTS words_fts_delete AFTER DELETE ON words BEGIN
    DELETE FROM words_fts WHERE rowid = old.id;
END;

CREATE TRIGGER IF NOT EXISTS words_fts_update AFTER UPDATE ON words BEGIN
    DELETE FROM words_fts WHERE rowid = old.id;
    INSERT INTO words_fts(rowid, word, definition)
    VALUES (new.id, new.word, new.definition);
END;
"""

# Migration from old schema to new schema
MIGRATION_SQL = """
-- Add new columns to existing words table
ALTER TABLE words ADD COLUMN word_lower TEXT;
ALTER TABLE words ADD COLUMN definition_length INTEGER;

-- Populate word_lower and definition_length
UPDATE words SET 
    word_lower = LOWER(word),
    definition_length = LENGTH(definition);

-- Create index on word_lower
CREATE INDEX IF NOT EXISTS idx_words_word_lower ON words(word_lower);

-- Add unique constraint (SQLite doesn't support ALTER TABLE ADD CONSTRAINT)
-- Will be handled by application logic or table recreation
"""
