"""
Script to process GNU GCIDE dictionary data and load it into SQLite database.

The GCIDE dictionary can be downloaded from:
- https://www.gnu.org/software/gcide/
- Or various mirrors hosting the XML files

This script can automatically download the dictionary from a URL specified
in the GCIDE_URL or GCIDE_DOWNLOAD_URL environment variable.

This script expects GCIDE XML files in a directory structure.
"""

import os
import xml.etree.ElementTree as ET
import re
import zipfile
import urllib.request
import urllib.error
import time
from pathlib import Path
from typing import List, Dict
import argparse
from dotenv import load_dotenv
import psycopg2
from psycopg2.extras import execute_batch

load_dotenv()


def _extract_definition_from_content(entry_content: str) -> str:
    """Extract definition text from entry content, preserving proper spacing and sense numbers."""
    definitions = []

    # Extract definition(s) - can be multiple <def> tags
    # Handle nested tags by matching opening/closing pairs
    def_matches = list(
        re.finditer(r"<def>((?:[^<]|<(?!/def>))*?)</def>", entry_content, re.DOTALL)
    )

    # For each definition, find preceding sense number if any
    for def_match in def_matches:
        def_start = def_match.start()
        # Look backwards for sense number before this definition
        text_before = entry_content[max(0, def_start - 200) : def_start]
        sn_match = re.search(r"<sn>([^<]+)</sn>\s*$", text_before)

        def_text = def_match.group(1)

        # Remove tags that shouldn't be in definitions (headword, pronunciation, part of speech, etymology)
        def_text = re.sub(r"<hw>[^<]*</hw>", "", def_text, flags=re.IGNORECASE)
        def_text = re.sub(r"<pr>[^<]*</pr>", "", def_text, flags=re.IGNORECASE)
        def_text = re.sub(r"<pos>[^<]*</pos>", "", def_text, flags=re.IGNORECASE)
        def_text = re.sub(
            r"<ety>.*?</ety>", "", def_text, flags=re.DOTALL | re.IGNORECASE
        )
        def_text = re.sub(r"<sn>[^<]*</sn>", "", def_text, flags=re.IGNORECASE)
        def_text = re.sub(r"\[source[^\]]+\]", "", def_text)
        def_text = re.sub(
            r"<source[^>]*>.*?</source>", "", def_text, flags=re.DOTALL | re.IGNORECASE
        )

        # Remove HTML tags but preserve spacing better
        # First, replace closing tags with space, then remove opening tags
        def_text = re.sub(r"</[^>]+>", " ", def_text)
        def_text = re.sub(r"<[^>]+>", " ", def_text)
        # Clean up multiple spaces but preserve single spaces
        def_text = re.sub(r"[ \t]+", " ", def_text)
        # Convert newlines to spaces (preserve word spacing)
        def_text = re.sub(r"\n+", " ", def_text)
        def_text = def_text.strip()

        if def_text:
            # Prepend sense number if found
            if sn_match:
                sense_num = sn_match.group(1).strip()
                def_text = f"{sense_num} {def_text}"
            definitions.append(def_text)

    # Combine multiple definitions with clear separation
    if len(definitions) > 1:
        # Use double newline + separator for multiple definitions
        definition = "\n\n---\n\n".join(definitions)
    elif definitions:
        definition = definitions[0]
    else:
        definition = ""

    # If no definition found, try simpler pattern (but exclude headword, pronunciation, pos, etymology)
    if not definition:
        # Remove headword, pronunciation, part of speech, and etymology tags before extracting
        # These are not part of the definition
        cleaned_content = entry_content
        cleaned_content = re.sub(
            r"<hw>[^<]*</hw>", "", cleaned_content, flags=re.IGNORECASE
        )
        cleaned_content = re.sub(
            r"<pr>[^<]*</pr>", "", cleaned_content, flags=re.IGNORECASE
        )
        cleaned_content = re.sub(
            r"<pos>[^<]*</pos>", "", cleaned_content, flags=re.IGNORECASE
        )
        cleaned_content = re.sub(
            r"<ety>.*?</ety>", "", cleaned_content, flags=re.DOTALL | re.IGNORECASE
        )
        cleaned_content = re.sub(
            r"<sn>[^<]*</sn>", "", cleaned_content, flags=re.IGNORECASE
        )
        cleaned_content = re.sub(r"\[source[^\]]+\]", "", cleaned_content)
        cleaned_content = re.sub(
            r"<source[^>]*>.*?</source>",
            "",
            cleaned_content,
            flags=re.DOTALL | re.IGNORECASE,
        )

        # Now try to extract any remaining text between tags as definition
        def_text = re.sub(r"</[^>]+>", " ", cleaned_content)
        def_text = re.sub(r"<[^>]+>", " ", def_text)
        def_text = re.sub(r"[ \t]+", " ", def_text)  # Normalize spaces
        def_text = re.sub(r"\n+", " ", def_text)
        def_text = def_text.strip()

        # If after removing headword/pronunciation/etymology we have no meaningful content,
        # return empty (this entry will be skipped)
        # Check if there's substantial content left (more than just metadata)
        if len(def_text) < 10 or not re.search(r"[a-zA-Z]{3,}", def_text):
            return ""

        definition = def_text

    return definition


def _is_valid_word(word: str) -> bool:
    """Check if a word entry is valid and should be stored."""
    if not word:
        return False

    word = word.strip()

    # Reject entries that are too long (likely sentences/metadata)
    # Real dictionary words are rarely over 50 characters
    if len(word) > 50:
        return False

    # Reject entries that start with numbers (e.g., "074", "(2)")
    if re.match(r"^[\d\(\)]+", word):
        return False

    # Reject entries that are mostly non-alphabetic
    # Require at least 30% letters for valid words
    alpha_count = sum(1 for c in word if c.isalpha())
    if len(word) > 0 and alpha_count / len(word) < 0.3:
        return False

    # Reject entries that look like table/metadata rows
    # Patterns like "074  60  3c          lt        $<$"
    # Multiple spaces or tabs separating mostly non-letter characters
    if re.search(r"\s{3,}", word):  # 3+ consecutive spaces
        parts = re.split(r"\s+", word)
        non_alpha_parts = sum(1 for p in parts if not re.search(r"[a-zA-Z]", p))
        if len(parts) > 2 and non_alpha_parts > len(parts) * 0.5:
            return False

    # Reject entries that are only symbols or punctuation
    if not re.search(r"[a-zA-Z]", word):
        return False

    # Reject entries that look like metadata/documentation
    # Patterns like long sentences starting with "A", "An", "The", etc.
    # These are likely documentation, not dictionary entries
    metadata_patterns = [
        r"^(A|An|The|This|That|These|Those)\s+[A-Z][a-z]+\s+(is|are|was|were|contains|contains|represents|used|uses)",  # Sentence patterns
        r"^(A|An)\s+\w+\s+\w+\s+\w+\s+\w+\s+\w+",  # Long phrases (5+ words)
    ]
    for pattern in metadata_patterns:
        if re.match(pattern, word, re.IGNORECASE):
            return False

    # Reject entries that contain common documentation keywords
    doc_keywords = [
        "separate file",
        "contains the list",
        "represent",
        "represented by",
        "used in",
        "used for",
        "used as",
        "placed in",
        "placed after",
        "indicated",
        "described",
        "explained",
        "following",
        "above",
        "below",
    ]
    word_lower = word.lower()
    for keyword in doc_keywords:
        if (
            keyword in word_lower and len(word) > 20
        ):  # Long entries with these are likely docs
            return False

    return True


def _parse_entry_content(entry_word: str, entry_content: str) -> Dict[str, str]:
    """Parse a single entry and return word/definition/pronunciation dict."""
    # First validate the entry word
    if not _is_valid_word(entry_word):
        return None

    # Extract pronunciation from <pr> tags
    pronunciation = None
    pr_matches = list(re.finditer(r"<pr>([^<]+)</pr>", entry_content))
    if pr_matches:
        # Get the first pronunciation (clean it up)
        pr_text = pr_matches[0].group(1).strip()
        # Remove extra brackets and clean up
        pr_text = re.sub(r"^\(+|\)+$", "", pr_text)  # Remove outer parentheses
        pr_text = pr_text.strip()
        if pr_text and len(pr_text) > 0:
            pronunciation = pr_text

    # Extract all headwords and find one that matches the entry word
    hw_matches = list(re.finditer(r"<hw>([^<]+)</hw>", entry_content))

    word = entry_word  # Default to entry word

    if hw_matches:
        # Normalize entry word for comparison (remove pronunciation marks, lowercase)
        entry_normalized = re.sub(r"[`'\"\*\^<>\?\/\\\s]", "", entry_word.lower())

        # Try to find a headword that matches the entry word
        matching_hw = None
        for hw_match in hw_matches:
            headword = hw_match.group(1).strip()
            hw_normalized = re.sub(r"[`'\"\*\^<>\?\/\\\s]", "", headword.lower())

            # Check if headword matches entry (normalized comparison)
            if hw_normalized == entry_normalized:
                matching_hw = headword
                break

        # If we found a matching headword, use entry_word (it's cleaner)
        # If no match, use first headword only if it's clearly different
        if not matching_hw and len(hw_matches) == 1:
            headword = hw_matches[0].group(1).strip()
            # Only use headword if entry has no alphabetic characters (like punctuation)
            # or if headword is substantially different
            if (
                not re.search(r"[a-zA-Z]", entry_word)
                or len(headword) > len(entry_word) * 1.5
            ):
                word = headword

    # Extract definition
    definition = _extract_definition_from_content(entry_content)

    # Validate the final word choice
    if not _is_valid_word(word):
        return None

    # Additional validation on definition - reject entries that look like metadata
    if definition:
        # Reject definitions that are mostly numbers/symbols (table data)
        def_alpha_count = sum(1 for c in definition if c.isalpha())
        if len(definition) > 0 and def_alpha_count / len(definition) < 0.3:
            return None

        # Reject very short definitions
        if len(definition) < 5:
            return None

        # Reject definitions that look like table rows (many tabs/spaces with non-text)
        if re.search(r"\s{4,}", definition) and def_alpha_count < len(definition) * 0.4:
            return None

    if word and definition and len(definition) > 5:
        result = {"word": word, "definition": definition}
        if pronunciation:
            result["pronunciation"] = pronunciation
        return result
    return None


def parse_gcide_html(gcide_file: Path) -> List[Dict[str, str]]:
    """
    Parse GCIDE HTML-like file format and extract word definitions.

    GCIDE format uses HTML-like tags. Entries can be:
    1. <p><ent>word</ent>...content...</p> (standard entries)
    2. Multiple <ent> tags within one <p> (nested/sub-entries)
    3. Multi-paragraph entries: <p><ent>word</ent>...</p> followed by <p><sn>...</p> paragraphs
    """
    entries = []

    try:
        with open(gcide_file, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()

        # Find all entry positions (<ent> tags) first
        ent_pattern = r"<p><ent>([^<]+)</ent>"
        ent_positions = []
        for match in re.finditer(ent_pattern, content):
            entry_word = match.group(1).strip()
            entry_start = match.start()
            ent_positions.append((entry_start, entry_word))

        # For each entry, collect all paragraphs until the next entry
        for idx, (entry_start, entry_word) in enumerate(ent_positions):
            # Find the end of this entry's content (start of next entry or end of file)
            if idx + 1 < len(ent_positions):
                next_entry_start = ent_positions[idx + 1][0]
                entry_section = content[entry_start:next_entry_start]
            else:
                entry_section = content[entry_start:]

            # Extract all paragraphs that belong to this entry
            # The entry starts with <p><ent>word</ent> and includes subsequent
            # paragraphs until we hit the next <p><ent> tag

            # Find the <ent> tag end position within this section
            ent_tag_match = re.search(r"<ent>[^<]+</ent>", entry_section)
            if not ent_tag_match:
                continue

            entry_content_start = ent_tag_match.end()
            # Get content from after <ent> tag, excluding any trailing whitespace/newlines
            entry_content = entry_section[entry_content_start:].strip()

            # Parse this entry with all its paragraph content
            entry = _parse_entry_content(entry_word, entry_content)
            if entry:
                entries.append(entry)

    except Exception as e:
        print(f"Error parsing GCIDE file {gcide_file}: {e}")
        import traceback

        traceback.print_exc()

    return entries


def parse_gcide_xml(xml_file: Path) -> List[Dict[str, str]]:
    """
    Parse GCIDE XML file and extract word definitions (legacy format).

    This is kept for compatibility but GCIDE uses HTML-like format.
    """
    # Try HTML parser first (actual GCIDE format)
    if xml_file.suffix.lower() not in [".xml"]:
        return parse_gcide_html(xml_file)

    entries = []

    try:
        tree = ET.parse(xml_file)
        root = tree.getroot()

        # Handle different possible XML structures
        entries_list = root.findall(".//entry") or root.findall("entry")

        for entry in entries_list:
            word_elem = entry.find("word") or entry.find("headword") or entry.find("hw")
            def_elem = (
                entry.find("definition") or entry.find("def") or entry.find("text")
            )

            if word_elem is not None and def_elem is not None:
                word = word_elem.text.strip() if word_elem.text else ""
                definition = def_elem.text.strip() if def_elem.text else ""

                if word and definition:
                    entries.append({"word": word, "definition": definition})
    except ET.ParseError:
        # If XML parsing fails, try HTML format
        return parse_gcide_html(xml_file)
    except Exception as e:
        print(f"Unexpected error processing {xml_file}: {e}")

    return entries


def parse_gcide_text(text_file: Path) -> List[Dict[str, str]]:
    """
    Parse GCIDE text format (alternative format).
    Format: WORD\nDefinition text\n\n
    """
    entries = []

    try:
        with open(text_file, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()

        # Split by double newlines (entry separator)
        raw_entries = re.split(r"\n\n+", content)

        for entry_text in raw_entries:
            lines = entry_text.strip().split("\n")
            if len(lines) >= 2:
                word = lines[0].strip()
                definition = "\n".join(lines[1:]).strip()

                if word and definition:
                    entries.append({"word": word, "definition": definition})
    except Exception as e:
        print(f"Error parsing text file {text_file}: {e}")

    return entries


def create_database():
    """Create PostgreSQL database schema."""
    from app.db.schema_pg import POSTGRES_SCHEMA
    from app.db.db_sync import get_db_config, get_db_connection_sync

    config = get_db_config()

    with get_db_connection_sync() as conn:
        cursor = conn.cursor()

        # First, drop the word_lower unique constraint if it exists (migration)
        try:
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
            for constraint in constraints:
                constraint_name = constraint[0]
                print(f"Removing old constraint: {constraint_name}")
                cursor.execute(
                    f"ALTER TABLE words DROP CONSTRAINT IF EXISTS {constraint_name}"
                )
        except Exception as e:
            print(f"Note: Could not check/drop constraint (may not exist): {e}")

        # Execute schema statements one by one
        for statement in POSTGRES_SCHEMA.split(";"):
            statement = statement.strip()
            if statement:
                try:
                    cursor.execute(statement)
                except psycopg2.errors.DuplicateTable:
                    pass  # Table already exists
                except psycopg2.errors.DuplicateObject:
                    pass  # Index/constraint already exists

        # Ensure word_lower index exists (non-unique)
        try:
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_words_word_lower ON words(word_lower)"
            )
        except Exception:
            pass  # Index may already exist

        # Add pronunciation column if it doesn't exist (migration for existing databases)
        try:
            cursor.execute(
                "ALTER TABLE words ADD COLUMN IF NOT EXISTS pronunciation TEXT"
            )
        except Exception:
            pass  # Column may already exist

        conn.commit()

    print(
        f"Created/verified database schema at {config['host']}:{config['port']}/{config['database']}"
    )


def load_entries(entries: List[Dict[str, str]], batch_size: int = 1000):
    """
    Load entries into database with optimized schema.
    Uses batch inserts for better performance.
    """
    from app.db.db_sync import get_db_connection_sync

    inserted = 0
    skipped = 0

    # Batch insert for better performance
    batch = []
    for entry in entries:
        word_lower = entry["word"].lower()
        definition_length = len(entry["definition"])
        pronunciation = entry.get("pronunciation")  # Get pronunciation if present

        batch.append(
            (
                entry["word"],
                word_lower,
                pronunciation,  # Add pronunciation
                entry["definition"],
                definition_length,
            )
        )

        if len(batch) >= batch_size:
            with get_db_connection_sync() as conn:
                inserted_batch, skipped_batch = _insert_batch(conn, batch)
                inserted += inserted_batch
                skipped += skipped_batch
            batch = []

    # Insert remaining entries
    if batch:
        with get_db_connection_sync() as conn:
            inserted_batch, skipped_batch = _insert_batch(conn, batch)
            inserted += inserted_batch
            skipped += skipped_batch

    print(f"Loaded {inserted} entries, skipped {skipped} duplicates")


def _insert_batch(conn, batch):
    """Insert a batch of entries efficiently using PostgreSQL."""
    cursor = conn.cursor()
    inserted = 0
    skipped = 0

    try:
        # Use ON CONFLICT for PostgreSQL
        # Handle conflicts on either word OR word_lower
        execute_batch(
            cursor,
            """INSERT INTO words (word, word_lower, pronunciation, definition, definition_length)
               VALUES (%s, %s, %s, %s, %s)
               ON CONFLICT (word) DO UPDATE SET
                   pronunciation = COALESCE(EXCLUDED.pronunciation, words.pronunciation),
                   definition = words.definition || E'\n\n\n==========\n\n' || EXCLUDED.definition,
                   definition_length = length(words.definition || E'\n\n\n==========\n\n' || EXCLUDED.definition)""",
            batch,
            page_size=1000,
        )
        # With DO UPDATE, rowcount might not reflect the behavior we want
        # Check which ones were actually new vs updated
        inserted = cursor.rowcount
        skipped = 0  # We're merging, not skipping
        conn.commit()
    except psycopg2.errors.UniqueViolation:
        # Handle conflicts individually - could be word or word_lower constraint
        conn.rollback()
        for word, word_lower, pronunciation, definition, def_len in batch:
            try:
                cursor.execute(
                    """INSERT INTO words (word, word_lower, pronunciation, definition, definition_length)
                       VALUES (%s, %s, %s, %s, %s)
                       ON CONFLICT (word) DO UPDATE SET
                           pronunciation = COALESCE(EXCLUDED.pronunciation, words.pronunciation),
                           definition = words.definition || E'\n\n\n==========\n\n' || EXCLUDED.definition,
                           definition_length = length(words.definition || E'\n\n\n==========\n\n' || EXCLUDED.definition)""",
                    (word, word_lower, pronunciation, definition, def_len),
                )
                inserted += 1  # Always count as inserted (even if merged)
            except Exception:
                skipped += 1
        conn.commit()
    except Exception as e:
        print(f"Error in batch insert: {e}")
        conn.rollback()
        # Fallback to individual inserts
        for word, word_lower, pronunciation, definition, def_len in batch:
            try:
                cursor.execute(
                    """INSERT INTO words (word, word_lower, pronunciation, definition, definition_length)
                       VALUES (%s, %s, %s, %s, %s)
                       ON CONFLICT (word) DO UPDATE SET
                           pronunciation = COALESCE(EXCLUDED.pronunciation, words.pronunciation),
                           definition = words.definition || E'\n\n\n==========\n\n' || EXCLUDED.definition,
                           definition_length = length(words.definition || E'\n\n\n==========\n\n' || EXCLUDED.definition)""",
                    (word, word_lower, pronunciation, definition, def_len),
                )
                inserted += 1  # Always count as inserted (even if merged)
            except Exception:
                skipped += 1
        conn.commit()

    return inserted, skipped


def _download_progress_hook(count, block_size, total_size):
    """Progress hook for urlretrieve."""
    downloaded = count * block_size
    percent = min(100, (downloaded * 100) // total_size) if total_size > 0 else 0
    print(f"\rDownloading: {percent}% ({downloaded // 1024 // 1024}MB)", end="")


def download_file_with_retry(
    url: str, output_path: Path, max_retries: int = 3, retry_delay: int = 5
) -> None:
    """
    Download file with retry logic and better error handling for Docker environments.

    Args:
        url: URL to download from
        output_path: Path to save the file
        max_retries: Maximum number of retry attempts
        retry_delay: Delay between retries in seconds
    """
    for attempt in range(1, max_retries + 1):
        try:
            print(f"Download attempt {attempt}/{max_retries}...")

            # Create a request with timeout and user agent
            req = urllib.request.Request(
                url,
                headers={
                    "User-Agent": "Mozilla/5.0 (compatible; GCIDE-Downloader/1.0)"
                },
            )

            # Use urlopen with timeout instead of urlretrieve for better control
            with urllib.request.urlopen(req, timeout=30) as response:
                total_size = int(response.headers.get("Content-Length", 0))
                downloaded = 0

                with open(output_path, "wb") as f:
                    while True:
                        chunk = response.read(8192)  # 8KB chunks
                        if not chunk:
                            break
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total_size > 0:
                            percent = (downloaded * 100) // total_size
                            print(
                                f"\rDownloading: {percent}% ({downloaded // 1024 // 1024}MB)",
                                end="",
                            )

            print("\nDownload complete!")
            return

        except urllib.error.URLError as e:
            error_msg = str(e)
            if (
                "Cannot assign requested address" in error_msg
                or "Errno 99" in error_msg
            ):
                print(f"\nNetwork error (attempt {attempt}/{max_retries}): {e}")
                print(
                    "This may be a Docker networking issue. Trying alternative approach..."
                )

                if attempt < max_retries:
                    print(f"Retrying in {retry_delay} seconds...")
                    time.sleep(retry_delay)
                    retry_delay *= 2  # Exponential backoff
                else:
                    raise Exception(
                        f"Failed to download after {max_retries} attempts. "
                        "This may be a Docker networking issue. "
                        "Try: 1) Restart Docker, 2) Check DNS settings, "
                        "3) Download manually and mount as volume, "
                        "4) Use a different mirror URL"
                    )
            else:
                raise
        except Exception as e:
            if attempt < max_retries:
                print(f"\nError (attempt {attempt}/{max_retries}): {e}")
                print(f"Retrying in {retry_delay} seconds...")
                time.sleep(retry_delay)
                retry_delay *= 2
            else:
                raise


def check_extracted_data_exists(output_dir: Path) -> bool:
    """
    Check if GCIDE data files are already extracted.

    Args:
        output_dir: Directory to check for extracted files

    Returns:
        True if CIDE.* files are found, False otherwise
    """
    # Check for CIDE.* files directly in output_dir or subdirectories
    cide_files = list(output_dir.glob("CIDE.*")) or list(output_dir.glob("**/CIDE.*"))

    # If we find at least one CIDE file, consider data present
    if cide_files:
        print(f"Found {len(cide_files)} existing GCIDE data files, skipping download.")
        return True

    return False


def download_and_extract_gcide(
    url: str, output_dir: Path, keep_zip: bool = True, force_download: bool = False
) -> Path:
    """
    Download GCIDE zip file and extract it to output directory.
    Only downloads if data files are not already present.

    Args:
        url: URL to download the zip file from
        output_dir: Directory to extract files to
        keep_zip: If True, keep the zip file in a downloads subdirectory for reuse
        force_download: If True, download even if data exists
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    # Check if extracted data already exists
    if not force_download and check_extracted_data_exists(output_dir):
        return output_dir

    # Extract filename from URL or use default
    filename = os.path.basename(url) or "gcide.zip"
    if not filename.endswith(".zip"):
        filename = "gcide.zip"

    # Store zip in downloads subdirectory to keep it separate from extracted files
    downloads_dir = output_dir.parent / "downloads"
    downloads_dir.mkdir(parents=True, exist_ok=True)
    zip_path = downloads_dir / filename

    # Check if zip already exists
    if zip_path.exists():
        print(f"Found existing zip file at {zip_path}.")
    else:
        # Download the file with retry logic
        print(f"Downloading GCIDE dictionary from: {url}")
        try:
            print("Starting download...")
            download_file_with_retry(url, zip_path, max_retries=3)
        except Exception as e:
            print(f"\nError downloading file: {e}")
            if zip_path.exists():
                zip_path.unlink()
            raise

    # Check again if extraction is needed (data might have appeared)
    if not force_download and check_extracted_data_exists(output_dir):
        print("Data files already extracted, skipping extraction.")
        return output_dir

    # Extract the zip file
    print(f"Extracting {zip_path}...")
    try:
        with zipfile.ZipFile(zip_path, "r") as zip_ref:
            # Show extraction progress
            file_list = zip_ref.namelist()
            total_files = len(file_list)
            print(f"Found {total_files} files in archive")
            zip_ref.extractall(output_dir)
        print(f"Extraction complete! Files extracted to {output_dir}")
    except zipfile.BadZipFile as e:
        print(f"Error: File is not a valid zip file: {e}")
        if not keep_zip and zip_path.exists():
            zip_path.unlink()
        raise
    except Exception as e:
        print(f"Error extracting zip file: {e}")
        raise

    if keep_zip:
        print(f"Zip file kept at {zip_path} for future use.")
    else:
        # Clean up zip file if not keeping it
        if zip_path.exists():
            zip_path.unlink()
            print("Cleaned up zip file")

    return output_dir


def process_directory(data_dir: Path):
    """Process all dictionary files in a directory."""
    entries = []

    # Look for GCIDE CIDE.* files (the actual GCIDE format)
    cide_files = sorted(list(data_dir.glob("CIDE.*")))
    if not cide_files:
        # Also check in subdirectories (like gcide-0.54/)
        cide_files = sorted(list(data_dir.glob("**/CIDE.*")))

    for cide_file in cide_files:
        print(f"Processing GCIDE file: {cide_file.name}")
        file_entries = parse_gcide_html(cide_file)
        entries.extend(file_entries)
        print(f"  Found {len(file_entries)} entries")

    # Also look for XML files (legacy/alternative format)
    xml_files = list(data_dir.glob("*.xml")) + list(data_dir.glob("**/*.xml"))
    for xml_file in xml_files:
        if "CIDE" not in xml_file.name:  # Don't process if we already did CIDE files
            print(f"Processing XML file: {xml_file}")
            file_entries = parse_gcide_xml(xml_file)
            entries.extend(file_entries)
            print(f"  Found {len(file_entries)} entries")

    # Look for text files
    text_files = list(data_dir.glob("*.txt")) + list(data_dir.glob("**/*.txt"))
    for text_file in text_files:
        print(f"Processing text file: {text_file}")
        file_entries = parse_gcide_text(text_file)
        entries.extend(file_entries)
        print(f"  Found {len(file_entries)} entries")

    if entries:
        print(f"\nTotal entries found: {len(entries)}")
        load_entries(entries)
    else:
        print("No entries found. Please check the data directory format.")


def main():
    parser = argparse.ArgumentParser(description="Process GCIDE dictionary data")
    parser.add_argument(
        "--data-dir",
        type=str,
        default="data/gcide_raw",
        help="Directory containing GCIDE dictionary files",
    )
    # Database path no longer needed - using PostgreSQL from .env
    parser.add_argument(
        "--download-url",
        type=str,
        default=None,
        help="URL to download GCIDE dictionary zip file (overrides env var)",
    )

    args = parser.parse_args()

    data_dir = Path(args.data_dir)

    # Check for download URL in environment variable or argument
    download_url = args.download_url
    if not download_url:
        # Try common environment variable names
        download_url = (
            os.getenv("GCIDE_URL")
            or os.getenv("GCIDE_DOWNLOAD_URL")
            or os.getenv("DICTIONARY_URL")
        )

    # Download and extract if URL is provided
    if download_url:
        print(f"Download URL provided: {download_url}")
        try:
            download_and_extract_gcide(download_url, data_dir)
        except Exception as e:
            print(f"Failed to download dictionary: {e}")
            return
    elif not data_dir.exists():
        print(f"Data directory {data_dir} does not exist.")
        print(
            "Please download GCIDE dictionary files and place them in this directory,"
        )
        print("or set GCIDE_URL environment variable to download automatically.")
        print("\nYou can download GCIDE from: https://www.gnu.org/software/gcide/")
        return

    print(f"Processing dictionary data from {data_dir}")

    create_database()
    process_directory(data_dir)

    # Verify
    from app.db.db_sync import get_db_connection_sync

    with get_db_connection_sync() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM words")
        count = cursor.fetchone()[0]

    print(f"\nDatabase now contains {count} words")


if __name__ == "__main__":
    main()
