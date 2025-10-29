import os
from typing import Dict, List, Optional
from dotenv import load_dotenv
import asyncpg
import networkx as nx

load_dotenv()


class GraphService:
    """Service for computing graph statistics on the dictionary."""

    def __init__(self):
        self.db_config = {
            "host": os.getenv("DB_HOST", "localhost"),
            "port": int(os.getenv("DB_PORT", "5432")),
            "database": os.getenv("DB_NAME", "gcide"),
            "user": os.getenv("DB_USER", "xnillio"),
            "password": os.getenv("DB_PASSWORD", ""),
        }
        self._pool = None
        self._graph_cache: Optional[nx.DiGraph] = None

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

    async def _build_graph(self) -> nx.DiGraph:
        """Build NetworkX graph from dictionary relationships."""
        if self._graph_cache is not None:
            return self._graph_cache

        G = nx.DiGraph()

        # Get all words and their links from word_links table
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            # Get all words
            words_rows = await conn.fetch("SELECT id, word_lower FROM words")

            # Build word_id -> word_lower mapping
            word_id_map = {row["id"]: row["word_lower"] for row in words_rows}

            # Add all nodes
            for word_lower in word_id_map.values():
                G.add_node(word_lower)

            # Get all links
            links_rows = await conn.fetch(
                "SELECT source_word_id, target_word_id FROM word_links"
            )

            # Add edges
            for link in links_rows:
                source = word_id_map.get(link["source_word_id"])
                target = word_id_map.get(link["target_word_id"])
                if source and target:
                    G.add_edge(source, target)

        self._graph_cache = G
        return G

    async def get_overview_stats(self) -> Dict:
        """Get basic dictionary statistics."""
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            # Total words
            total_words = await conn.fetchval("SELECT COUNT(*) FROM words")

            # Average definition length
            avg_length = (
                await conn.fetchval("SELECT AVG(definition_length) FROM words")
                or await conn.fetchval("SELECT AVG(LENGTH(definition)) FROM words")
                or 0
            )

            # Average degree centrality
            avg_degree = (
                await conn.fetchval(
                    "SELECT AVG(degree_centrality) FROM words WHERE degree_centrality > 0"
                )
                or 0
            )

        return {
            "total_words": total_words,
            "average_definition_length": round(avg_length, 2),
            "average_degree_centrality": round(avg_degree, 2),
        }

    async def get_graph_statistics(self) -> Dict:
        """Get detailed graph statistics."""
        G = await self._build_graph()

        if len(G.nodes()) == 0:
            return {"error": "Graph is empty. Please load dictionary data first."}

        # Basic stats
        num_nodes = G.number_of_nodes()
        num_edges = G.number_of_edges()

        # Degree statistics
        in_degrees = dict(G.in_degree())
        out_degrees = dict(G.out_degree())

        # Find words with highest in-degree (defined by many words)
        top_in_degree = sorted(
            [(word, deg) for word, deg in in_degrees.items()],
            key=lambda x: x[1],
            reverse=True,
        )[:10]

        # Find words with highest out-degree (reference many words)
        top_out_degree = sorted(
            [(word, deg) for word, deg in out_degrees.items()],
            key=lambda x: x[1],
            reverse=True,
        )[:10]

        # Connected components
        if nx.is_strongly_connected(G) or len(G.nodes()) > 0:
            try:
                if G.number_of_nodes() > 0:
                    # For large graphs, sample or use weakly connected
                    weakly_connected = list(nx.weakly_connected_components(G))
                    largest_component_size = (
                        max(len(c) for c in weakly_connected) if weakly_connected else 0
                    )
                else:
                    largest_component_size = 0
            except Exception:
                largest_component_size = 0
        else:
            largest_component_size = 0

        # Simple cycle detection (basic)
        try:
            cycles = list(nx.simple_cycles(G))
            cycle_count = len(cycles)
            # Limit cycle reporting for performance
            sample_cycles = cycles[:5] if len(cycles) <= 5 else cycles[:5]
        except Exception:
            cycle_count = 0
            sample_cycles = []

        return {
            "nodes": num_nodes,
            "edges": num_edges,
            "average_in_degree": round(
                sum(in_degrees.values()) / num_nodes if num_nodes > 0 else 0, 2
            ),
            "average_out_degree": round(
                sum(out_degrees.values()) / num_nodes if num_nodes > 0 else 0, 2
            ),
            "top_words_by_in_degree": [
                {"word": word, "count": count} for word, count in top_in_degree
            ],
            "top_words_by_out_degree": [
                {"word": word, "count": count} for word, count in top_out_degree
            ],
            "largest_component_size": largest_component_size,
            "cycle_count": cycle_count,
            "sample_cycles": sample_cycles[:3],  # Limit for response size
        }

    async def get_top_words(self, limit: int = 10) -> List[Dict]:
        """Get words with highest total degree."""
        G = await self._build_graph()

        total_degrees = {
            word: G.in_degree(word) + G.out_degree(word) for word in G.nodes()
        }

        top_words = sorted(
            [(word, deg) for word, deg in total_degrees.items()],
            key=lambda x: x[1],
            reverse=True,
        )[:limit]

        return [
            {
                "word": word,
                "total_degree": degree,
                "in_degree": G.in_degree(word),
                "out_degree": G.out_degree(word),
            }
            for word, degree in top_words
        ]

    async def find_cycles(self) -> Dict:
        """Find circular definition dependencies."""
        G = await self._build_graph()

        try:
            cycles = list(nx.simple_cycles(G))
            return {
                "total_cycles": len(cycles),
                "cycles": cycles[:20],  # Limit for response size
            }
        except Exception as e:
            return {"total_cycles": 0, "cycles": [], "error": str(e)}
