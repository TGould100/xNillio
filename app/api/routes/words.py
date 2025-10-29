from fastapi import APIRouter, HTTPException, Query
from app.services.dictionary import DictionaryService

router = APIRouter()
dict_service = DictionaryService()


@router.get("/{word}")
async def get_word(word: str):
    """Get definition for a word and extract linked words from the definition."""
    word_lower = word.lower().strip()

    definition_data = await dict_service.get_definition(word_lower)
    if not definition_data:
        raise HTTPException(
            status_code=404, detail=f"Word '{word}' not found in dictionary"
        )

    # Extract words that exist in dictionary from the definition
    linked_words = await dict_service.extract_linked_words(
        word_lower, definition_data["definition"]
    )

    return {
        "word": definition_data["word"],
        "pronunciation": definition_data.get("pronunciation"),
        "definition": definition_data["definition"],
        "linked_words": linked_words,
        "word_id": definition_data.get("id"),
        "degree_centrality": definition_data.get("degree_centrality", 0),
        "in_degree": definition_data.get("in_degree", 0),
        "out_degree": definition_data.get("out_degree", 0),
        "in_out_ratio": definition_data.get("in_out_ratio", 0),
    }


@router.get("/{word}/neighbors")
async def get_word_neighbors(word: str, depth: int = Query(1, ge=1, le=3)):
    """Get graph neighborhood of a word."""
    word_lower = word.lower().strip()

    neighbors = await dict_service.get_neighbors(word_lower, depth)
    if neighbors is None:
        raise HTTPException(
            status_code=404, detail=f"Word '{word}' not found in dictionary"
        )

    return {"word": word_lower, "depth": depth, "neighbors": neighbors}


@router.get("/search/{query}")
async def search_words(query: str, limit: int = Query(10, ge=1, le=50)):
    """Search for words matching a query (prefix match)."""
    results = await dict_service.search_words(query.lower().strip(), limit)
    return {"query": query, "results": results, "count": len(results)}
