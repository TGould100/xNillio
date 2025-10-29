"""
Synchronous database connection for data processing scripts.
Uses psycopg2 for sync operations.
"""

import os
import psycopg2
import psycopg2.extras
from typing import Optional
from contextlib import contextmanager


def get_db_config() -> dict:
    """Get database configuration from environment variables."""
    return {
        "host": os.getenv("DB_HOST", "localhost"),
        "port": int(os.getenv("DB_PORT", "5432")),
        "database": os.getenv("DB_NAME", "gcide"),
        "user": os.getenv("DB_USER", "xnillio"),
        "password": os.getenv("DB_PASSWORD", ""),
    }


@contextmanager
def get_db_connection_sync():
    """Get a synchronous database connection."""
    config = get_db_config()
    conn = psycopg2.connect(
        host=config["host"],
        port=config["port"],
        database=config["database"],
        user=config["user"],
        password=config["password"],
    )
    try:
        yield conn
    finally:
        conn.close()


def create_database_sync():
    """Create database schema using synchronous connection."""
    from app.db.schema_pg import POSTGRES_SCHEMA
    import psycopg2

    with get_db_connection_sync() as conn:
        cursor = conn.cursor()
        # Execute schema statements one by one
        for statement in POSTGRES_SCHEMA.split(";"):
            statement = statement.strip()
            if statement:
                try:
                    cursor.execute(statement)
                except psycopg2.errors.DuplicateTable:
                    pass  # Table already exists
        conn.commit()
