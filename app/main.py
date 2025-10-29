import os
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from app.api.routes import words, stats, health as health_router
from app.data.process_gcide import (
    download_and_extract_gcide,
    create_database,
    process_directory,
)

load_dotenv()

app = FastAPI(
    title="GCIDE Dictionary Explorer",
    description="Explore word relationships in the GNU GCIDE dictionary",
    version="1.0.0",
)

# CORS middleware for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:5173",
    ],  # Vite default port
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(words.router, prefix="/api/words", tags=["words"])
app.include_router(stats.router, prefix="/api/stats", tags=["stats"])
app.include_router(health_router.router, prefix="/api/health", tags=["health"])


def check_database_exists() -> bool:
    """Check if database exists and has data."""
    try:
        import psycopg2
        import psycopg2.errors
        from app.db.db_sync import get_db_config

        config = get_db_config()
        conn = psycopg2.connect(
            host=config["host"],
            port=config["port"],
            database=config["database"],
            user=config["user"],
            password=config["password"],
        )
        cursor = conn.cursor()

        # Check if table exists first
        cursor.execute(
            """
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_name = 'words'
            )
        """
        )
        table_exists = cursor.fetchone()[0]

        if not table_exists:
            conn.close()
            return False

        cursor.execute("SELECT COUNT(*) FROM words")
        count = cursor.fetchone()[0]
        conn.close()
        return count > 0
    except psycopg2.errors.UndefinedTable:
        # Table doesn't exist yet
        return False
    except Exception:
        return False


async def ensure_gcide_data():
    """Ensure GCIDE dictionary data is available, download if necessary."""
    # Determine paths for data files
    base_dir = Path(__file__).parent.parent
    data_dir = base_dir / "data" / "gcide_raw"

    # Check if database exists and has data
    if check_database_exists():
        print("GCIDE dictionary database found and populated.")

        # Run validation tests to ensure database integrity
        from app.data.test_database import run_all_tests

        print("Running database validation tests...")
        test_result = run_all_tests(None, None)

        if test_result == 0:
            print("✓ Database validation passed.")
        else:
            print("⚠ Database validation found issues, but continuing...")

        # Check if word_links table needs to be populated
        import psycopg2
        from app.db.db_sync import get_db_config

        config = get_db_config()
        conn = psycopg2.connect(
            host=config["host"],
            port=config["port"],
            database=config["database"],
            user=config["user"],
            password=config["password"],
        )
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM word_links")
        link_count = cursor.fetchone()[0]
        conn.close()

        if link_count == 0:
            print("\nWord links table is empty. Computing relationships...")
            from app.data.compute_word_links import compute_word_links

            try:
                compute_word_links()
                print("✓ Word links computed successfully.")
            except Exception as e:
                print(f"⚠ Warning: Failed to compute word links: {e}")
                print(
                    "Graph features may not work, but basic dictionary lookup will still function."
                )

        return

    print("GCIDE dictionary database not found or empty.")

    # Check for download URL in environment variables
    download_url = (
        os.getenv("GCIDE_URL")
        or os.getenv("GCIDE_DOWNLOAD_URL")
        or os.getenv("DICTIONARY_URL")
    )

    if not download_url:
        print(
            "WARNING: No GCIDE_URL environment variable set. "
            "Dictionary lookup will not work until data is loaded."
        )
        print(
            "Set GCIDE_URL, GCIDE_DOWNLOAD_URL, or DICTIONARY_URL environment variable "
            "to automatically download the dictionary."
        )
        # Create empty database so app can start
        create_database()
        return

    print(f"Download URL found: {download_url}")

    # Check if extracted data files already exist
    from app.data.process_gcide import check_extracted_data_exists

    has_extracted_data = check_extracted_data_exists(data_dir)

    if not has_extracted_data:
        print("Extracted data files not found. Downloading and extracting...")
        try:
            # Download and extract
            download_and_extract_gcide(download_url, data_dir)
        except Exception as e:
            print(f"ERROR: Failed to download/extract GCIDE dictionary: {e}")
            print("The application will start but dictionary features will not work.")
            create_database()
            return
    else:
        print("Extracted data files found, skipping download.")

    # Create database schema if needed (and fix any existing constraints)
    create_database()

    # Process extracted files (will only process if not already in database)
    print("Processing dictionary files...")
    try:
        process_directory(data_dir)

        # Verify with tests
        from app.data.test_database import run_all_tests

        # Find a test file for parser validation
        test_file = None
        if data_dir.exists():
            cide_files = list(data_dir.glob("CIDE.*")) or list(
                data_dir.glob("**/CIDE.*")
            )
            if cide_files:
                test_file = cide_files[0]

        print("\n" + "=" * 50)
        print("Running database initialization tests...")
        print("=" * 50)
        test_result = run_all_tests(None, test_file)

        if test_result != 0:
            print(
                "\nWARNING: Some database tests failed. "
                "Dictionary features may not work correctly."
            )
        else:
            import psycopg2
            from app.db.db_sync import get_db_config

            config = get_db_config()
            conn = psycopg2.connect(
                host=config["host"],
                port=config["port"],
                database=config["database"],
                user=config["user"],
                password=config["password"],
            )
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM words")
            count = cursor.fetchone()[0]
            conn.close()
            print(f"\n✓ Database initialized successfully with {count:,} words.")

            # Compute word links for graph functionality
            print("\nComputing word relationships (this may take a few minutes)...")
            from app.data.compute_word_links import compute_word_links

            try:
                compute_word_links()
                print("✓ Word links computed successfully.")
            except Exception as e:
                print(f"⚠ Warning: Failed to compute word links: {e}")
                print(
                    "Graph features may not work, but basic dictionary lookup will still function."
                )
    except Exception as e:
        print(f"ERROR: Failed to download/process GCIDE dictionary: {e}")
        import traceback

        traceback.print_exc()
        print("The application will start but dictionary features will not work.")
        # Create empty database so app can start
        create_database()


@app.on_event("startup")
async def startup_event():
    """Run startup tasks."""
    await ensure_gcide_data()


@app.get("/")
def root():
    return {
        "message": "GCIDE Dictionary API",
        "version": "1.0.0",
        "endpoints": {"words": "/api/words/{word}", "stats": "/api/stats/overview"},
    }


@app.get("/health")
def health():
    """Basic health endpoint."""
    return {"status": "healthy"}


@app.get("/ready")
def ready():
    """Readiness check - verifies database is initialized."""
    from app.data.test_database import test_database_content

    base_dir = Path(__file__).parent.parent
    db_path = base_dir / "data" / "gcide.db"

    content_tests = test_database_content(db_path)
    is_ready = content_tests["has_data"] and content_tests["word_count"] > 0

    return {
        "status": "ready" if is_ready else "not_ready",
        "database": {
            "word_count": content_tests["word_count"],
            "has_data": content_tests["has_data"],
        },
    }
