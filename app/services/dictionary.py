import re
import os
from typing import Optional, Dict, List
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

    async def extract_linked_words(
        self, source_word: str, definition: str
    ) -> List[str]:
        """Extract words from definition that exist in the dictionary."""
        # Extract potential words (alphanumeric sequences)
        words_in_def = re.findall(r"\b[a-zA-Z]+\b", definition.lower())

        # Remove duplicates and filter out common stop words
        unique_words = set(words_in_def)

        # Filter stop words and the source word itself
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

        filtered_words = [
            w
            for w in unique_words
            if w not in stop_words
            and w != source_word.lower()
            and len(w) > 2  # Ignore very short words
        ]

        # Check which words exist in dictionary (batch check for performance)
        existing_words = []
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            # Batch check using IN clause for better performance
            if filtered_words:
                placeholders = ",".join(
                    [f"${i + 1}" for i in range(len(filtered_words))]
                )
                rows = await conn.fetch(
                    f"SELECT word_lower FROM words WHERE word_lower IN ({placeholders})",
                    *filtered_words,
                )
                existing_words = [row["word_lower"] for row in rows]

        return sorted(existing_words)

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
