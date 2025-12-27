"""
Centralized RAG Analysis Database

Stores all RAG analysis data in SQLite for fast lookups by folder name.
This solves the problem of scattered JSON files and folder name mismatches.
"""

import os
import json
import sqlite3
from pathlib import Path
from datetime import datetime
from typing import Dict, Optional, List


class RAGDatabase:
    """Centralized SQLite database for RAG analysis results"""

    def __init__(self, db_path: str = None):
        if db_path is None:
            # Store in project-tracker static/data folder
            db_path = os.path.join(
                os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
                'static', 'data', 'rag_analysis.db'
            )
        self.db_path = db_path
        self._ensure_db_exists()

    def _ensure_db_exists(self):
        """Create database and tables if they don't exist"""
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)

        with sqlite3.connect(self.db_path) as conn:
            conn.execute('''
                CREATE TABLE IF NOT EXISTS rag_analysis (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    folder_name TEXT UNIQUE NOT NULL,
                    folder_name_normalized TEXT NOT NULL,
                    folder_path TEXT,
                    scope_summary TEXT,
                    windows_json TEXT,
                    doors_json TEXT,
                    storefront_json TEXT,
                    hardware_json TEXT,
                    glass_json TEXT,
                    exclusions_json TEXT,
                    confidence TEXT,
                    embedder TEXT,
                    generator TEXT,
                    chunks_analyzed INTEGER,
                    tokens_used INTEGER,
                    analyzed_at TEXT,
                    imported_at TEXT,
                    raw_json TEXT
                )
            ''')

            # Create index for fast lookups
            conn.execute('''
                CREATE INDEX IF NOT EXISTS idx_folder_normalized
                ON rag_analysis(folder_name_normalized)
            ''')

            conn.commit()

    @staticmethod
    def normalize_folder_name(name: str) -> str:
        """Normalize folder name for matching (lowercase, no punctuation)"""
        import re
        # Remove common suffixes like " - City MA"
        normalized = name.lower()
        # Replace hyphens and underscores with spaces first
        normalized = re.sub(r'[-_]', ' ', normalized)
        # Remove other punctuation (not letters, numbers, spaces)
        normalized = re.sub(r'[^\w\s]', '', normalized)
        # Collapse whitespace
        normalized = ' '.join(normalized.split())
        return normalized

    def save_analysis(self, folder_name: str, analysis: Dict, folder_path: str = None) -> bool:
        """Save RAG analysis to database"""
        try:
            normalized = self.normalize_folder_name(folder_name)
            metadata = analysis.get('_rag_metadata', {})

            with sqlite3.connect(self.db_path) as conn:
                conn.execute('''
                    INSERT OR REPLACE INTO rag_analysis (
                        folder_name, folder_name_normalized, folder_path,
                        scope_summary, windows_json, doors_json, storefront_json,
                        hardware_json, glass_json, exclusions_json, confidence,
                        embedder, generator, chunks_analyzed, tokens_used,
                        analyzed_at, imported_at, raw_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    folder_name,
                    normalized,
                    folder_path,
                    analysis.get('scope_summary', ''),
                    json.dumps(analysis.get('windows', {})),
                    json.dumps(analysis.get('doors', {})),
                    json.dumps(analysis.get('storefront', {})),
                    json.dumps(analysis.get('hardware', {})),
                    json.dumps(analysis.get('glass', {})),
                    json.dumps(analysis.get('exclusions', [])),
                    analysis.get('confidence', 'low'),
                    metadata.get('embedder', ''),
                    metadata.get('generator', ''),
                    metadata.get('chunks_analyzed', 0),
                    metadata.get('tokens_used', 0),
                    metadata.get('generated_at', ''),
                    datetime.now().isoformat(),
                    json.dumps(analysis)
                ))
                conn.commit()
            return True
        except Exception as e:
            print(f"Error saving RAG analysis for {folder_name}: {e}")
            return False

    def get_analysis(self, folder_name: str) -> Optional[Dict]:
        """Get RAG analysis by folder name (exact or fuzzy match)"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row

            # First try exact match
            cursor = conn.execute(
                'SELECT * FROM rag_analysis WHERE folder_name = ?',
                (folder_name,)
            )
            row = cursor.fetchone()

            # If not found, try normalized match
            if not row:
                normalized = self.normalize_folder_name(folder_name)
                cursor = conn.execute(
                    'SELECT * FROM rag_analysis WHERE folder_name_normalized = ?',
                    (normalized,)
                )
                row = cursor.fetchone()

            # If still not found, try partial match
            if not row:
                # Try matching just the core project name (first part before " - ")
                core_name = folder_name.split(' - ')[0] if ' - ' in folder_name else folder_name
                normalized_core = self.normalize_folder_name(core_name)
                cursor = conn.execute(
                    'SELECT * FROM rag_analysis WHERE folder_name_normalized LIKE ?',
                    (f'{normalized_core}%',)
                )
                row = cursor.fetchone()

            if row:
                return self._row_to_dict(row)
            return None

    def _row_to_dict(self, row: sqlite3.Row) -> Dict:
        """Convert database row to analysis dict"""
        scope_summary = row['scope_summary'] or ''
        windows = {}
        doors = {}
        storefront = {}
        hardware = {}
        glass = {}
        exclusions = []
        confidence = row['confidence'] or 'low'

        # Handle case where scope_summary contains raw JSON (some imports saved entire JSON as scope_summary)
        # In this case, use raw_json to get the proper data structure
        if scope_summary.strip().startswith('{') and row['raw_json']:
            import re
            try:
                raw_data = json.loads(row['raw_json'])
                raw_scope = raw_data.get('scope_summary', '')

                # If raw_scope is also JSON string (double-encoded), try to parse it
                if isinstance(raw_scope, str) and raw_scope.strip().startswith('{'):
                    try:
                        inner = json.loads(raw_scope)
                        if isinstance(inner, dict) and 'scope_summary' in inner:
                            scope_summary = inner.get('scope_summary', '')
                            windows = inner.get('windows', {}) or {}
                            doors = inner.get('doors', {}) or {}
                            storefront = inner.get('storefront', {}) or {}
                            hardware = inner.get('hardware', {}) or {}
                            glass = inner.get('glass', {}) or {}
                            exclusions = inner.get('exclusions', []) or []
                            confidence = inner.get('confidence', confidence) or confidence
                    except json.JSONDecodeError:
                        # JSON is malformed (truncated GPT response), extract text using regex
                        match = re.search(r'"scope_summary":\s*"([^"]+)', raw_scope)
                        if match:
                            scope_summary = match.group(1)
                            # Unescape any escaped characters
                            scope_summary = scope_summary.replace('\\"', '"').replace('\\n', '\n')
                        else:
                            # Fall back to keeping the raw text but strip JSON syntax
                            scope_summary = re.sub(r'^\s*\{\s*"scope_summary":\s*"?', '', raw_scope)
                            scope_summary = re.sub(r'"\s*,?\s*$', '', scope_summary)
                else:
                    scope_summary = raw_scope
            except json.JSONDecodeError:
                pass  # Keep the original scope_summary if parsing fails

        # Use database columns for structured data if not already set from parsed JSON
        if not windows:
            windows = json.loads(row['windows_json']) if row['windows_json'] else {}
        if not doors:
            doors = json.loads(row['doors_json']) if row['doors_json'] else {}
        if not storefront:
            storefront = json.loads(row['storefront_json']) if row['storefront_json'] else {}
        if not hardware:
            hardware = json.loads(row['hardware_json']) if row['hardware_json'] else {}
        if not glass:
            glass = json.loads(row['glass_json']) if row['glass_json'] else {}
        if not exclusions:
            exclusions = json.loads(row['exclusions_json']) if row['exclusions_json'] else []

        return {
            'scope_summary': scope_summary,
            'windows': windows,
            'doors': doors,
            'storefront': storefront,
            'hardware': hardware,
            'glass': glass,
            'exclusions': exclusions,
            'confidence': confidence,
            '_rag_metadata': {
                'embedder': row['embedder'],
                'generator': row['generator'],
                'chunks_analyzed': row['chunks_analyzed'],
                'tokens_used': row['tokens_used'],
                'generated_at': row['analyzed_at']
            },
            '_db_folder_name': row['folder_name'],
            '_db_folder_path': row['folder_path']
        }

    def get_all_analysis(self) -> List[Dict]:
        """Get all RAG analysis records"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute('SELECT * FROM rag_analysis ORDER BY analyzed_at DESC')
            return [self._row_to_dict(row) for row in cursor.fetchall()]

    def get_stats(self) -> Dict:
        """Get database statistics"""
        with sqlite3.connect(self.db_path) as conn:
            total = conn.execute('SELECT COUNT(*) FROM rag_analysis').fetchone()[0]
            with_summary = conn.execute(
                "SELECT COUNT(*) FROM rag_analysis WHERE scope_summary != ''"
            ).fetchone()[0]

            generators = {}
            cursor = conn.execute(
                'SELECT generator, COUNT(*) FROM rag_analysis GROUP BY generator'
            )
            for row in cursor:
                generators[row[0] or 'unknown'] = row[1]

            return {
                'total_records': total,
                'with_summary': with_summary,
                'generators': generators,
                'db_path': self.db_path
            }

    def import_from_json_files(self, bidding_folder: str) -> Dict:
        """Import all division8_rag_analysis.json files into database"""
        bidding_path = Path(bidding_folder)
        imported = 0
        failed = 0
        skipped = 0

        for rag_file in bidding_path.rglob('division8_rag_analysis.json'):
            try:
                folder_path = rag_file.parent
                folder_name = folder_path.name

                # Skip .chroma_local folders
                if '.chroma_local' in str(rag_file):
                    skipped += 1
                    continue

                with open(rag_file, 'r') as f:
                    analysis = json.load(f)

                if self.save_analysis(folder_name, analysis, str(folder_path)):
                    imported += 1
                else:
                    failed += 1

            except Exception as e:
                print(f"Error importing {rag_file}: {e}")
                failed += 1

        return {
            'imported': imported,
            'failed': failed,
            'skipped': skipped,
            'total': imported + failed + skipped
        }

    def delete_all(self):
        """Clear all records from database"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('DELETE FROM rag_analysis')
            conn.commit()


# Singleton instance
_db_instance = None

def get_rag_database() -> RAGDatabase:
    """Get singleton RAG database instance"""
    global _db_instance
    if _db_instance is None:
        _db_instance = RAGDatabase()
    return _db_instance


if __name__ == '__main__':
    import sys
    from dotenv import load_dotenv
    load_dotenv()

    bidding_folder = os.getenv('BIDDING_FOLDER', '')
    if not bidding_folder:
        print("Error: BIDDING_FOLDER environment variable not set.")
        sys.exit(1)

    db = RAGDatabase()

    if len(sys.argv) > 1 and sys.argv[1] == 'import':
        print(f"Importing RAG analysis files from {bidding_folder}...")
        result = db.import_from_json_files(bidding_folder)
        print(f"Import complete: {result}")

    stats = db.get_stats()
    print(f"\nDatabase stats: {json.dumps(stats, indent=2)}")
