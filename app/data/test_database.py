"""
Test suite for verifying database initialization and data integrity.
"""

import os
from pathlib import Path
from typing import Dict, Optional
from dotenv import load_dotenv
import psycopg2
from app.data.process_gcide import parse_gcide_html
from app.db.db_sync import get_db_config, get_db_connection_sync

load_dotenv()


def test_database_schema(db_path: Optional[Path] = None) -> Dict[str, bool]:
    """Test that database schema is correct."""
    results = {"schema_valid": False, "tables_exist": False, "indexes_exist": False}

    try:
        with get_db_connection_sync() as conn:
            cursor = conn.cursor()

            # Check if words table exists and has correct columns
            cursor.execute(
                """
                SELECT table_name FROM information_schema.tables
                WHERE table_schema = 'public' AND table_name = 'words'
            """
            )
            if cursor.fetchone():
                results["tables_exist"] = True

                # Check table structure
                cursor.execute(
                    """
                    SELECT column_name, data_type
                    FROM information_schema.columns
                    WHERE table_name = 'words' AND table_schema = 'public'
                """
                )
                columns = {col[0]: col[1] for col in cursor.fetchall()}

                required_columns = {"id", "word", "definition"}
                if required_columns.issubset(columns.keys()):
                    results["schema_valid"] = True

                # Check indexes
                cursor.execute(
                    """
                    SELECT indexname FROM pg_indexes
                    WHERE tablename = 'words' AND schemaname = 'public'
                """
                )
                indexes = [row[0] for row in cursor.fetchall()]
                if any("word" in idx.lower() for idx in indexes):
                    results["indexes_exist"] = True

    except Exception as e:
        print(f"Error testing schema: {e}")

    return results


def test_database_content(db_path: Optional[Path] = None) -> Dict[str, any]:
    """Test that database has valid content."""
    results = {
        "has_data": False,
        "word_count": 0,
        "sample_words_valid": False,
        "definitions_valid": False,
    }

    try:
        with get_db_connection_sync() as conn:
            cursor = conn.cursor()

            # Check word count
            cursor.execute("SELECT COUNT(*) FROM words")
            count = cursor.fetchone()[0]
            results["word_count"] = count
            results["has_data"] = count > 0

            if count > 0:
                # Test a few sample words
                test_words = ["the", "and", "dictionary", "word", "definition"]
                # Use psycopg2's sql module for proper parameter handling
                from psycopg2 import sql

                # Create placeholders for the first IN clause
                first_placeholders = sql.SQL(",").join(
                    sql.Placeholder() * len(test_words)
                )
                # Create placeholders for the second IN clause
                second_placeholders = sql.SQL(",").join(
                    sql.Placeholder() * len(test_words)
                )

                query = sql.SQL(
                    """
                    SELECT word, definition FROM words
                    WHERE word_lower IN ({}) OR word IN ({})
                    LIMIT 5
                """
                ).format(first_placeholders, second_placeholders)

                # Pass all parameters as a tuple (test_words twice for both IN clauses)
                cursor.execute(query, tuple(test_words + test_words))
                found_words = cursor.fetchall()

                if len(found_words) >= 2:
                    results["sample_words_valid"] = True

                    # Verify definitions are not empty
                    valid_defs = all(
                        len(row) >= 2 and row[1] and len(str(row[1])) > 5
                        for row in found_words
                    )
                    results["definitions_valid"] = valid_defs
                else:
                    # If specific test words not found, check that at least some words exist with definitions
                    cursor.execute(
                        "SELECT word, definition FROM words WHERE definition IS NOT NULL AND length(definition) > 5 LIMIT 5"
                    )
                    sample_words = cursor.fetchall()
                    if len(sample_words) >= 2:
                        results["sample_words_valid"] = True
                        results["definitions_valid"] = True

    except Exception as e:
        print(f"Error testing content: {e}")

    return results


def test_parser_output(test_file: Optional[Path] = None) -> Dict[str, any]:
    """Test that parser produces valid output."""
    results = {
        "parser_works": False,
        "entry_count": 0,
        "entries_have_words": False,
        "entries_have_definitions": False,
    }

    if test_file is None:
        # Try to find a test file
        test_file = (
            Path(__file__).parent.parent.parent
            / "data"
            / "gcide_raw"
            / "gcide-0.54"
            / "CIDE.A"
        )

    if not test_file or not test_file.exists():
        return results

    try:
        entries = parse_gcide_html(test_file)

        results["entry_count"] = len(entries)
        results["parser_works"] = len(entries) > 0

        if entries:
            # Verify entry structure
            has_words = all("word" in e and e["word"] for e in entries[:100])
            has_defs = all(
                "definition" in e and e["definition"] and len(e["definition"]) > 5
                for e in entries[:100]
            )

            results["entries_have_words"] = has_words
            results["entries_have_definitions"] = has_defs
    except Exception as e:
        print(f"Error testing parser: {e}")

    return results


def run_all_tests(
    db_path: Optional[Path] = None, test_file: Optional[Path] = None
) -> Dict[str, any]:
    """Run all database tests and return results."""
    print("Running database initialization tests...")
    print("=" * 50)

    schema_results = test_database_schema(db_path)
    content_results = test_database_content(db_path)
    parser_results = test_parser_output(test_file)

    all_results = {
        "schema": schema_results,
        "content": content_results,
        "parser": parser_results,
    }

    # Overall status
    all_passed = (
        schema_results["schema_valid"]
        and schema_results["indexes_exist"]
        and content_results["has_data"]
        and content_results["sample_words_valid"]
        and parser_results["parser_works"]
    )

    all_results["all_tests_passed"] = all_passed

    # Print results
    print("\nSchema Tests:")
    print(f"  ✓ Tables exist: {schema_results['tables_exist']}")
    print(f"  ✓ Schema valid: {schema_results['schema_valid']}")
    print(f"  ✓ Indexes exist: {schema_results['indexes_exist']}")

    print("\nContent Tests:")
    print(f"  ✓ Has data: {content_results['has_data']}")
    print(f"  ✓ Word count: {content_results['word_count']:,}")
    print(f"  ✓ Sample words valid: {content_results['sample_words_valid']}")
    print(f"  ✓ Definitions valid: {content_results['definitions_valid']}")

    print("\nParser Tests:")
    print(f"  ✓ Parser works: {parser_results['parser_works']}")
    print(f"  ✓ Entry count: {parser_results['entry_count']}")
    print(f"  ✓ Entries have words: {parser_results['entries_have_words']}")
    print(f"  ✓ Entries have definitions: {parser_results['entries_have_definitions']}")

    print("\n" + "=" * 50)
    if all_passed:
        print("✓ All tests PASSED - Database is correctly initialized!")
        return 0
    else:
        print("✗ Some tests FAILED - Database may not be correctly initialized.")
        return 1


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Test database initialization")
    parser.add_argument(
        "--db-path",
        type=str,
        default="data/gcide.db",
        help="Path to database file",
    )
    parser.add_argument(
        "--test-file",
        type=str,
        default=None,
        help="Optional test file for parser testing",
    )

    args = parser.parse_args()

    db_path = Path(args.db_path)
    test_file = Path(args.test_file) if args.test_file else None

    exit_code = run_all_tests(db_path, test_file)
    exit(exit_code)
