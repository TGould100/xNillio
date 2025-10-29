"""
Script to fix the database schema by removing the word_lower unique constraint.
This allows case variations of the same word to coexist.
"""

from app.db.db_sync import get_db_connection_sync


def fix_word_lower_constraint():
    """Remove the word_lower unique constraint if it exists."""
    try:
        with get_db_connection_sync() as conn:
            cursor = conn.cursor()

            # Check if the constraint exists
            cursor.execute(
                """
                SELECT constraint_name 
                FROM information_schema.table_constraints 
                WHERE table_name = 'words' 
                AND constraint_type = 'UNIQUE'
                AND constraint_name LIKE '%word_lower%'
            """
            )
            constraints = cursor.fetchall()

            if constraints:
                constraint_name = constraints[0][0]
                print(f"Found constraint: {constraint_name}")
                print(f"Dropping constraint: {constraint_name}")

                # Drop the constraint
                cursor.execute(
                    f"ALTER TABLE words DROP CONSTRAINT IF EXISTS {constraint_name}"
                )
                conn.commit()

                print(f"✓ Successfully removed {constraint_name} constraint")
            else:
                print("✓ No word_lower unique constraint found - schema is correct")

            # Ensure index exists (non-unique)
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_words_word_lower ON words(word_lower)"
            )
            conn.commit()
            print("✓ Index on word_lower created/verified")

    except Exception as e:
        print(f"Error fixing schema: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    fix_word_lower_constraint()
