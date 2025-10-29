"""
Pre-compute word relationships for efficient graph queries.

This script analyzes all word definitions and builds the word_links table,
which stores pre-computed relationships between words. This allows fast
graph queries without expensive on-the-fly extraction.
"""

import re
from typing import Set, List, Tuple, Optional
from tqdm import tqdm
from dotenv import load_dotenv
from psycopg2.extras import execute_batch
from app.db.db_sync import get_db_connection_sync

load_dotenv()


def get_stop_words() -> Set[str]:
    """Get set of stop words to filter out."""
    return {
        "a",
        "also",
        "an",
        "the",
        "and",
        "or",
        "but",
        "in",
        "on",
        "at",
        "to",
        "for",
        "of",
        "with",
        "by",
        "from",
        "as",
        "is",
        "was",
        "are",
        "were",
        "be",
        "been",
        "being",
        "have",
        "has",
        "had",
        "do",
        "does",
        "did",
        "will",
        "would",
        "could",
        "should",
        "may",
        "might",
        "must",
        "can",
        "this",
        "that",
        "these",
        "those",
        "it",
        "its",
        "which",
        "who",
        "what",
        "when",
        "where",
        "why",
        "how",
        "not",
        "no",
        "nor",
        "so",
        "than",
        "too",
        "very",
    }


def find_compound_variations_sync(phrase: str, cursor) -> Optional[str]:
    """
    Check if a phrase exists in dictionary in any variation (spaces, hyphens).
    Returns the actual word_lower from dictionary if found, None otherwise.
    """
    normalized = re.sub(r"\s+", " ", phrase.strip().lower())

    # Try exact match first
    cursor.execute(
        "SELECT word_lower FROM words WHERE word_lower = %s LIMIT 1", (normalized,)
    )
    row = cursor.fetchone()
    if row:
        return row[0]

    # Try with hyphens instead of spaces
    hyphenated = normalized.replace(" ", "-")
    cursor.execute(
        "SELECT word_lower FROM words WHERE word_lower = %s LIMIT 1", (hyphenated,)
    )
    row = cursor.fetchone()
    if row:
        return row[0]

    # Try regex match for flexible spacing/hyphenation
    pattern = re.escape(normalized).replace(r"\ ", r"[\\s\\-]+")
    cursor.execute(
        "SELECT word_lower FROM words WHERE word_lower ~ %s LIMIT 1", (f"^{pattern}$",)
    )
    row = cursor.fetchone()
    if row:
        return row[0]

    return None


def extract_words_from_definition(
    definition: str,
    word_index: dict,
    stop_words: Set[str],
    source_word_lower: str,
    cursor,
) -> Set[str]:
    """
    Extract words from definition text, prioritizing compound phrases.
    If a compound exists, links to it and skips individual words within it.
    """
    definition_lower = definition.lower()
    found_words: Set[str] = set()

    # Track which character positions are covered by compound words
    covered_positions: Set[int] = set()

    # Extract all word positions
    words_list = []
    word_positions: List[Tuple[int, int, str]] = []

    for match in re.finditer(r"\b[a-zA-Z]+\b", definition_lower):
        words_list.append(match.group())
        word_positions.append((match.start(), match.end(), match.group()))

    # Try to find compound phrases (2-5 words), starting with longest first
    for start_idx in range(len(words_list)):
        for phrase_length in range(5, 1, -1):  # Try 5 words, then 4, 3, 2
            end_idx = start_idx + phrase_length
            if end_idx > len(words_list):
                continue

            # Check if any positions in this phrase are already covered
            phrase_start_pos = word_positions[start_idx][0]
            phrase_end_pos = word_positions[end_idx - 1][1]

            if any(
                pos in covered_positions
                for pos in range(phrase_start_pos, phrase_end_pos)
            ):
                continue  # Skip if already covered by a compound

            # Build phrase from words
            phrase = " ".join(words_list[start_idx:end_idx])

            # Check if this phrase exists in dictionary
            compound_word = find_compound_variations_sync(phrase, cursor)

            if compound_word and compound_word in word_index:
                # Found a compound that exists - add it and mark positions
                found_words.add(compound_word)
                # Mark all character positions in this phrase as covered
                for pos in range(phrase_start_pos, phrase_end_pos):
                    covered_positions.add(pos)
                break  # Stop trying shorter phrases from this position

    # Now extract individual words only from uncovered positions
    for start_pos, end_pos, word in word_positions:
        # Check if this word is covered by a compound
        if any(pos in covered_positions for pos in range(start_pos, end_pos)):
            continue  # Skip words that are part of compounds

        word_lower = word.lower()
        # Filter: not stop word, not source word, minimum length
        if (
            word_lower not in stop_words
            and word_lower != source_word_lower
            and len(word_lower) > 2
            and word_lower in word_index
        ):
            found_words.add(word_lower)

    return found_words


def build_word_index() -> dict:
    """Build in-memory index of word_lower -> word_id for fast lookups."""
    with get_db_connection_sync() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, word_lower FROM words")
        word_index = {word_lower: word_id for word_id, word_lower in cursor.fetchall()}

    return word_index


def compute_word_links(batch_size: int = 10000):
    """
    Compute and store word links in the database.

    Args:
        batch_size: Number of links to insert in a single transaction
    """
    print("Building word index from database...")
    word_index = build_word_index()
    print(f"Indexed {len(word_index)} words")

    stop_words = get_stop_words()

    with get_db_connection_sync() as conn:
        cursor = conn.cursor()

        # Get total count for progress bar
        cursor.execute("SELECT COUNT(*) FROM words")
        total_words = cursor.fetchone()[0]

        # Check if word_links table exists (should already exist from schema)
        cursor.execute(
            """
            SELECT table_name FROM information_schema.tables
            WHERE table_schema = 'public' AND table_name = 'word_links'
        """
        )

        if not cursor.fetchone():
            print("Warning: word_links table not found. Creating it...")
            # Table should be created by schema, but if not, create it
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS word_links (
                    id SERIAL PRIMARY KEY,
                    source_word_id INTEGER NOT NULL,
                    target_word_id INTEGER NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (source_word_id) REFERENCES words(id) ON DELETE CASCADE,
                    FOREIGN KEY (target_word_id) REFERENCES words(id) ON DELETE CASCADE,
                    UNIQUE(source_word_id, target_word_id)
                )
            """
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_word_links_source ON word_links(source_word_id)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_word_links_target ON word_links(target_word_id)"
            )
            conn.commit()

        # Check if links already exist
        cursor.execute("SELECT COUNT(*) FROM word_links")
        existing_links = cursor.fetchone()[0]

        if existing_links > 0:
            print(
                f"Found {existing_links} existing word links. Clearing for recomputation..."
            )
            cursor.execute("DELETE FROM word_links")
            conn.commit()

        # Process all words
        cursor.execute("SELECT id, word, word_lower, definition FROM words")

        links_batch = []
        processed = 0
        compound_matches = 0
        individual_matches = 0

        print(f"Processing {total_words} words...")
        for word_id, word, word_lower, definition in tqdm(
            cursor.fetchall(), total=total_words
        ):
            # Extract words using improved compound-aware extraction
            words_in_def = extract_words_from_definition(
                definition, word_index, stop_words, word_lower, cursor
            )

            # Remove the source word itself
            words_in_def.discard(word_lower)

            # Find matching word IDs and build links
            for target_word_lower in words_in_def:
                if target_word_lower in word_index:
                    target_word_id = word_index[target_word_lower]
                    links_batch.append((word_id, target_word_id))

                    # Track statistics
                    if " " in target_word_lower or "-" in target_word_lower:
                        compound_matches += 1
                    else:
                        individual_matches += 1

            # Batch insert for performance
            if len(links_batch) >= batch_size:
                execute_batch(
                    cursor,
                    """INSERT INTO word_links (source_word_id, target_word_id)
                       VALUES (%s, %s)
                       ON CONFLICT (source_word_id, target_word_id) DO NOTHING""",
                    links_batch,
                    page_size=batch_size,
                )
                conn.commit()
                links_batch = []

            processed += 1

        # Insert remaining links
        if links_batch:
            execute_batch(
                cursor,
                """INSERT INTO word_links (source_word_id, target_word_id)
                   VALUES (%s, %s)
                   ON CONFLICT (source_word_id, target_word_id) DO NOTHING""",
                links_batch,
                page_size=batch_size,
            )
            conn.commit()

        # Get statistics
        cursor.execute("SELECT COUNT(*) FROM word_links")
        total_links = cursor.fetchone()[0]

    print(f"\nCompleted! Created {total_links} word links from {processed} words")
    print(f"  Compound phrase matches: {compound_matches}")
    print(f"  Individual word matches: {individual_matches}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Pre-compute word relationships")
    parser.add_argument(
        "--batch-size",
        type=int,
        default=10000,
        help="Batch size for inserts",
    )

    args = parser.parse_args()

    compute_word_links(batch_size=args.batch_size)
