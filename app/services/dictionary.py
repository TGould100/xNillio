import re
import os
from typing import Optional, Dict, List, Set, Tuple
import asyncpg
from dotenv import load_dotenv

load_dotenv()


class DictionaryService:
    """Service for dictionary lookups and word extraction."""

    def __init__(self):
        self.db_config = {
            "host": os.getenv("DB_HOST", "localhost"),
            "port": int(os.getenv("DB_PORT", "5432")),
            "database": os.getenv("DB_NAME", "gcide"),
            "user": os.getenv("DB_USER", "xnillio"),
            "password": os.getenv("DB_PASSWORD", ""),
        }
        self._pool = None

    async def _get_pool(self):
        """Get or create database connection pool."""
        if self._pool is None:
            self._pool = await asyncpg.create_pool(
                host=self.db_config["host"],
                port=self.db_config["port"],
                database=self.db_config["database"],
                user=self.db_config["user"],
                password=self.db_config["password"],
                min_size=2,
                max_size=10,
            )
        return self._pool

    async def get_definition(self, word: str) -> Optional[Dict]:
        """Get definition for a word."""
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT id, word, pronunciation, definition FROM words WHERE word_lower = $1",
                word.lower(),
            )
            if row:
                return {
                    "id": row["id"],
                    "word": row["word"],
                    "pronunciation": row.get("pronunciation"),
                    "definition": row["definition"],
                }
        return None

    async def word_exists(self, word: str) -> bool:
        """Check if a word exists in the dictionary."""
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT 1 FROM words WHERE word_lower = $1 LIMIT 1", word.lower()
            )
            return row is not None

    async def _find_compound_variations(
        self, phrase: str, conn: asyncpg.Connection
    ) -> Optional[str]:
        """
        Check if a phrase exists in dictionary in any variation (spaces, hyphens).
        Returns the actual word_lower from dictionary if found, None otherwise.

        Tries: "mother in law" -> checks for "mother-in-law", "mother in law", etc.
        """
        # Normalize: lowercase, normalize whitespace
        normalized = re.sub(r"\s+", " ", phrase.strip().lower())

        # Try exact match first
        row = await conn.fetchrow(
            "SELECT word_lower FROM words WHERE word_lower = $1 LIMIT 1", normalized
        )
        if row:
            return row["word_lower"]

        # Try with hyphens instead of spaces
        hyphenated = normalized.replace(" ", "-")
        row = await conn.fetchrow(
            "SELECT word_lower FROM words WHERE word_lower = $1 LIMIT 1", hyphenated
        )
        if row:
            return row["word_lower"]

        # Try regex match for flexible spacing/hyphenation
        # This handles cases like "mother-in-law" in DB vs "mother in law" in text
        pattern = re.escape(normalized).replace(r"\ ", r"[\\s\\-]+")
        rows = await conn.fetch(
            "SELECT word_lower FROM words WHERE word_lower ~ $1 LIMIT 1", f"^{pattern}$"
        )
        if rows:
            return rows[0]["word_lower"]

        return None

    async def extract_linked_words(
        self, source_word: str, definition: str
    ) -> List[str]:
        """
        Extract words from definition that exist in the dictionary.
        Prioritizes compound phrases - if a compound exists, links to it and
        skips individual words within it.
        """
        stop_words = {
            "a",
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

        definition_lower = definition.lower()
        found_words: Set[str] = set()

        # Track which character positions are covered by compound words
        # This prevents extracting individual words from within compounds
        covered_positions: Set[int] = set()

        pool = await self._get_pool()
        async with pool.acquire() as conn:
            # Extract all potential n-grams (2-5 words) and check if they exist as compounds
            # Start with longest phrases first (greedy matching)
            words_list = re.findall(r"\b[a-zA-Z]+\b", definition_lower)
            word_positions: List[Tuple[int, int, str]] = []

            # Build mapping of word start positions
            for match in re.finditer(r"\b[a-zA-Z]+\b", definition_lower):
                word_positions.append((match.start(), match.end(), match.group()))

            # Try to find compound phrases (2-5 words)
            # Start from each position and try phrases of increasing length
            for start_idx in range(len(words_list)):
                for phrase_length in range(5, 1, -1):  # Try 5 words, then 4, 3, 2
                    end_idx = start_idx + phrase_length
                    if end_idx > len(words_list):
                        continue

                    # Check if any words in this phrase are already covered
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
                    compound_word = await self._find_compound_variations(phrase, conn)

                    if compound_word:
                        # Found a compound - add it and mark positions as covered
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
                    and word_lower != source_word.lower()
                    and len(word_lower) > 2
                ):

                    # Check if word exists in dictionary
                    row = await conn.fetchrow(
                        "SELECT word_lower FROM words WHERE word_lower = $1 LIMIT 1",
                        word_lower,
                    )
                    if row:
                        found_words.add(row["word_lower"])

        return sorted(found_words)

    async def get_neighbors(self, word: str, depth: int = 1) -> Optional[Dict]:
        """Get neighboring words in the definition graph."""
        if not await self.word_exists(word):
            return None

        visited = set()
        neighbors_by_depth = {}

        async def bfs(current_word: str, current_depth: int):
            if current_depth > depth or current_word in visited:
                return

            visited.add(current_word)

            if current_depth not in neighbors_by_depth:
                neighbors_by_depth[current_depth] = []

            definition_data = await self.get_definition(current_word)
            if definition_data:
                linked = await self.extract_linked_words(
                    current_word, definition_data["definition"]
                )
                neighbors_by_depth[current_depth].extend(linked)

                if current_depth < depth:
                    for neighbor in linked:
                        if neighbor not in visited:
                            await bfs(neighbor, current_depth + 1)

        await bfs(word, 1)

        return {
            "word": word,
            "neighbors_by_depth": {
                str(d): list(set(words)) for d, words in neighbors_by_depth.items()
            },
        }

    async def search_words(self, query: str, limit: int = 10) -> List[str]:
        """Search for words matching a prefix."""
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT word FROM words WHERE word_lower LIKE $1 ORDER BY word LIMIT $2",
                f"{query.lower()}%",
                limit,
            )
            return [row["word"] for row in rows]
