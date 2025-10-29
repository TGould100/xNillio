from fastapi import APIRouter
from app.services.graph import GraphService

router = APIRouter()
graph_service = GraphService()


@router.get("/overview")
async def get_overview():
    """Get basic dictionary statistics."""
    return await graph_service.get_overview_stats()


@router.get("/graph")
async def get_graph_stats():
    """Get detailed graph statistics."""
    return await graph_service.get_graph_statistics()


@router.get("/top-words")
async def get_top_words(limit: int = 10):
    """Get words with highest degree (most connections)."""
    return await graph_service.get_top_words(limit)


@router.get("/cycles")
async def get_cycles():
    """Find circular definition dependencies."""
    return await graph_service.find_cycles()
