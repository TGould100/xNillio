import aiosqlite
from typing import Dict, List, Optional
from pathlib import Path
import networkx as nx


class GraphService:
    """Service for computing graph statistics on the dictionary."""

    def __init__(self, db_path: Optional[str] = None):
        if db_path is None:
            self.db_path = Path(__file__).parent.parent.parent / "data" / "gcide.db"
        else:
            self.db_path = Path(db_path)

        self._graph_cache: Optional[nx.DiGraph] = None

    async def _build_graph(self) -> nx.DiGraph:
        """Build NetworkX graph from dictionary relationships."""
        if self._graph_cache is not None:
            return self._graph_cache

        from app.services.dictionary import DictionaryService

        dict_service = DictionaryService(str(self.db_path))

        G = nx.DiGraph()

        # Get all words
        async with aiosqlite.connect(str(self.db_path)) as db:
            async with db.execute("SELECT word, definition FROM words") as cursor:
                async for row in cursor:
                    word = row[0].lower()
                    definition = row[1]

                    # Add node
                    G.add_node(word)

                    # Extract linked words and add edges
                    linked_words = await dict_service.extract_linked_words(
                        word, definition
                    )
                    for linked_word in linked_words:
                        G.add_edge(word, linked_word)

        self._graph_cache = G
        return G

    async def get_overview_stats(self) -> Dict:
        """Get basic dictionary statistics."""
        async with aiosqlite.connect(str(self.db_path)) as db:
            # Total words
            async with db.execute("SELECT COUNT(*) FROM words") as cursor:
                total_words = (await cursor.fetchone())[0]

            # Average definition length
            async with db.execute(
                "SELECT AVG(LENGTH(definition)) FROM words"
            ) as cursor:
                avg_length = (await cursor.fetchone())[0] or 0

        return {
            "total_words": total_words,
            "average_definition_length": round(avg_length, 2),
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
