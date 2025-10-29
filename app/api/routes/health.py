"""
Health check endpoints that verify database integrity.
"""

from fastapi import APIRouter
from app.data.test_database import (
    test_database_schema,
    test_database_content,
)
from pathlib import Path

router = APIRouter()


@router.get("/")
def health_check():
    """Basic health check."""
    return {"status": "healthy"}


@router.get("/database")
async def database_health():
    """Detailed database health check."""
    schema_tests = test_database_schema(None)
    content_tests = test_database_content(None)

    is_healthy = (
        schema_tests["schema_valid"]
        and content_tests["has_data"]
        and content_tests["word_count"] > 0
    )

    return {
        "status": "healthy" if is_healthy else "unhealthy",
        "database": {
            "schema": schema_tests,
            "content": content_tests,
        },
    }
