"""
Database connection module using PostgreSQL.
Loads credentials from environment variables.
"""

import os
from typing import Optional
import asyncpg
from contextlib import asynccontextmanager


def get_db_config() -> dict:
    """Get database configuration from environment variables."""
    return {
        "host": os.getenv("DB_HOST", "localhost"),
        "port": int(os.getenv("DB_PORT", "5432")),
        "database": os.getenv("DB_NAME", "gcide"),
        "user": os.getenv("DB_USER", "xnillio"),
        "password": os.getenv("DB_PASSWORD", ""),
    }


def get_connection_string() -> str:
    """Get PostgreSQL connection string."""
    config = get_db_config()
    return (
        f"postgresql://{config['user']}:{config['password']}"
        f"@{config['host']}:{config['port']}/{config['database']}"
    )


async def get_db_pool():
    """Get or create database connection pool."""
    config = get_db_config()
    return await asyncpg.create_pool(
        host=config["host"],
        port=config["port"],
        database=config["database"],
        user=config["user"],
        password=config["password"],
        min_size=2,
        max_size=10,
    )


@asynccontextmanager
async def get_db_connection():
    """Get a database connection from the pool."""
    pool = await get_db_pool()
    async with pool.acquire() as connection:
        yield connection


async def execute_query(query: str, *args):
    """Execute a query and return results."""
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        return await conn.fetch(query, *args)


async def execute_command(query: str, *args):
    """Execute a command (INSERT, UPDATE, DELETE) and return row count."""
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        return await conn.execute(query, *args)
