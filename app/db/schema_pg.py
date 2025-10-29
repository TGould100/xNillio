"""
PostgreSQL-compatible database schema for GCIDE dictionary.
"""

POSTGRES_SCHEMA = """
-- Main words table
CREATE TABLE IF NOT EXISTS words (
    id SERIAL PRIMARY KEY,
    word TEXT NOT NULL,
    word_lower TEXT NOT NULL,
    pronunciation TEXT,
    definition TEXT NOT NULL,
    definition_length INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT words_word_unique UNIQUE (word)
    -- Note: word_lower is not unique to allow case variations
    -- We'll use word_lower for case-insensitive lookups via index
);

-- Word relationships (edges in the definition graph)
CREATE TABLE IF NOT EXISTS word_links (
    id SERIAL PRIMARY KEY,
    source_word_id INTEGER NOT NULL,
    target_word_id INTEGER NOT NULL,
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

-- Word links indexes
CREATE INDEX IF NOT EXISTS idx_word_links_source ON word_links(source_word_id);
CREATE INDEX IF NOT EXISTS idx_word_links_target ON word_links(target_word_id);
CREATE INDEX IF NOT EXISTS idx_word_links_both ON word_links(source_word_id, target_word_id);

-- Full-text search using PostgreSQL tsvector
CREATE INDEX IF NOT EXISTS idx_words_definition_fts ON words
    USING gin(to_tsvector('english', definition));
"""
