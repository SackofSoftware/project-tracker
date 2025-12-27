"""
SQLite Database Module for Project Tracker
Stores takeoff results, user corrections, notes, and version history
"""

import sqlite3
import json
from pathlib import Path
from datetime import datetime
from contextlib import contextmanager
from typing import Optional, Dict, List, Any

# Database path
DB_PATH = Path(__file__).parent.parent / "data" / "project_tracker.db"


def get_db_path() -> Path:
    """Get database path, ensuring directory exists"""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    return DB_PATH


@contextmanager
def get_connection():
    """Context manager for database connections"""
    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def init_db():
    """Initialize database schema"""
    with get_connection() as conn:
        cursor = conn.cursor()

        # Projects table - basic project info
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS projects (
                id TEXT PRIMARY KEY,
                folder_path TEXT,
                title TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Takeoff results table - stores complete takeoff data
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS takeoff_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id TEXT NOT NULL,
                version INTEGER DEFAULT 1,
                result_data TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                created_by TEXT DEFAULT 'system',
                FOREIGN KEY (project_id) REFERENCES projects(id)
            )
        """)

        # User corrections table - edits to quantities
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS corrections (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id TEXT NOT NULL,
                takeoff_id INTEGER,
                field_name TEXT NOT NULL,
                original_value TEXT,
                corrected_value TEXT NOT NULL,
                reason TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                created_by TEXT DEFAULT 'user',
                FOREIGN KEY (project_id) REFERENCES projects(id),
                FOREIGN KEY (takeoff_id) REFERENCES takeoff_results(id)
            )
        """)

        # Notes table - user notes on projects
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id TEXT NOT NULL,
                note_type TEXT DEFAULT 'general',
                content TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                created_by TEXT DEFAULT 'user',
                FOREIGN KEY (project_id) REFERENCES projects(id)
            )
        """)

        # Document organization table - tracks organized files
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS organized_files (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id TEXT NOT NULL,
                original_path TEXT NOT NULL,
                organized_path TEXT NOT NULL,
                doc_type TEXT,
                sheet_number TEXT,
                sheet_title TEXT,
                page_number INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (project_id) REFERENCES projects(id)
            )
        """)

        # Create indexes
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_takeoff_project ON takeoff_results(project_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_corrections_project ON corrections(project_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_notes_project ON notes(project_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_files_project ON organized_files(project_id)")

        conn.commit()


# ==================== PROJECT FUNCTIONS ====================

def get_or_create_project(project_id: str, folder_path: str = None, title: str = None) -> Dict:
    """Get existing project or create new one"""
    with get_connection() as conn:
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM projects WHERE id = ?", (project_id,))
        row = cursor.fetchone()

        if row:
            return dict(row)

        # Create new project
        cursor.execute(
            "INSERT INTO projects (id, folder_path, title) VALUES (?, ?, ?)",
            (project_id, folder_path, title)
        )
        conn.commit()

        return {
            'id': project_id,
            'folder_path': folder_path,
            'title': title,
            'created_at': datetime.now().isoformat()
        }


# ==================== TAKEOFF FUNCTIONS ====================

def save_takeoff_result(project_id: str, result_data: Dict, created_by: str = 'system') -> int:
    """Save takeoff result with version tracking"""
    with get_connection() as conn:
        cursor = conn.cursor()

        # Get current max version
        cursor.execute(
            "SELECT MAX(version) FROM takeoff_results WHERE project_id = ?",
            (project_id,)
        )
        max_version = cursor.fetchone()[0] or 0
        new_version = max_version + 1

        # Insert new result
        cursor.execute(
            """INSERT INTO takeoff_results (project_id, version, result_data, created_by)
               VALUES (?, ?, ?, ?)""",
            (project_id, new_version, json.dumps(result_data), created_by)
        )
        conn.commit()

        return cursor.lastrowid


def get_latest_takeoff(project_id: str) -> Optional[Dict]:
    """Get the latest takeoff result for a project"""
    with get_connection() as conn:
        cursor = conn.cursor()

        cursor.execute(
            """SELECT * FROM takeoff_results
               WHERE project_id = ?
               ORDER BY version DESC LIMIT 1""",
            (project_id,)
        )
        row = cursor.fetchone()

        if row:
            result = dict(row)
            result['result_data'] = json.loads(result['result_data'])
            return result
        return None


def get_takeoff_history(project_id: str) -> List[Dict]:
    """Get all takeoff versions for a project"""
    with get_connection() as conn:
        cursor = conn.cursor()

        cursor.execute(
            """SELECT id, version, created_at, created_by
               FROM takeoff_results
               WHERE project_id = ?
               ORDER BY version DESC""",
            (project_id,)
        )
        return [dict(row) for row in cursor.fetchall()]


def get_takeoff_by_version(project_id: str, version: int) -> Optional[Dict]:
    """Get specific version of takeoff"""
    with get_connection() as conn:
        cursor = conn.cursor()

        cursor.execute(
            """SELECT * FROM takeoff_results
               WHERE project_id = ? AND version = ?""",
            (project_id, version)
        )
        row = cursor.fetchone()

        if row:
            result = dict(row)
            result['result_data'] = json.loads(result['result_data'])
            return result
        return None


# ==================== CORRECTIONS FUNCTIONS ====================

def save_correction(
    project_id: str,
    field_name: str,
    corrected_value: str,
    original_value: str = None,
    reason: str = None,
    takeoff_id: int = None
) -> int:
    """Save a user correction to a quantity"""
    with get_connection() as conn:
        cursor = conn.cursor()

        cursor.execute(
            """INSERT INTO corrections
               (project_id, takeoff_id, field_name, original_value, corrected_value, reason)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (project_id, takeoff_id, field_name, original_value, corrected_value, reason)
        )
        conn.commit()

        return cursor.lastrowid


def get_corrections(project_id: str, takeoff_id: int = None) -> List[Dict]:
    """Get all corrections for a project"""
    with get_connection() as conn:
        cursor = conn.cursor()

        if takeoff_id:
            cursor.execute(
                """SELECT * FROM corrections
                   WHERE project_id = ? AND takeoff_id = ?
                   ORDER BY created_at DESC""",
                (project_id, takeoff_id)
            )
        else:
            cursor.execute(
                """SELECT * FROM corrections
                   WHERE project_id = ?
                   ORDER BY created_at DESC""",
                (project_id,)
            )

        return [dict(row) for row in cursor.fetchall()]


def get_latest_corrections(project_id: str) -> Dict[str, str]:
    """Get latest correction for each field as a dict"""
    with get_connection() as conn:
        cursor = conn.cursor()

        # Get most recent correction for each field
        cursor.execute(
            """SELECT field_name, corrected_value
               FROM corrections
               WHERE project_id = ?
               GROUP BY field_name
               HAVING created_at = MAX(created_at)""",
            (project_id,)
        )

        return {row['field_name']: row['corrected_value'] for row in cursor.fetchall()}


# ==================== NOTES FUNCTIONS ====================

def save_note(project_id: str, content: str, note_type: str = 'general') -> int:
    """Save a note for a project"""
    with get_connection() as conn:
        cursor = conn.cursor()

        cursor.execute(
            """INSERT INTO notes (project_id, note_type, content)
               VALUES (?, ?, ?)""",
            (project_id, note_type, content)
        )
        conn.commit()

        return cursor.lastrowid


def update_note(note_id: int, content: str) -> bool:
    """Update an existing note"""
    with get_connection() as conn:
        cursor = conn.cursor()

        cursor.execute(
            """UPDATE notes
               SET content = ?, updated_at = CURRENT_TIMESTAMP
               WHERE id = ?""",
            (content, note_id)
        )
        conn.commit()

        return cursor.rowcount > 0


def get_notes(project_id: str, note_type: str = None) -> List[Dict]:
    """Get all notes for a project"""
    with get_connection() as conn:
        cursor = conn.cursor()

        if note_type:
            cursor.execute(
                """SELECT * FROM notes
                   WHERE project_id = ? AND note_type = ?
                   ORDER BY updated_at DESC""",
                (project_id, note_type)
            )
        else:
            cursor.execute(
                """SELECT * FROM notes
                   WHERE project_id = ?
                   ORDER BY updated_at DESC""",
                (project_id,)
            )

        return [dict(row) for row in cursor.fetchall()]


def delete_note(note_id: int) -> bool:
    """Delete a note"""
    with get_connection() as conn:
        cursor = conn.cursor()

        cursor.execute("DELETE FROM notes WHERE id = ?", (note_id,))
        conn.commit()

        return cursor.rowcount > 0


# ==================== ORGANIZED FILES FUNCTIONS ====================

def save_organized_file(
    project_id: str,
    original_path: str,
    organized_path: str,
    doc_type: str = None,
    sheet_number: str = None,
    sheet_title: str = None,
    page_number: int = None
) -> int:
    """Save record of an organized file"""
    with get_connection() as conn:
        cursor = conn.cursor()

        cursor.execute(
            """INSERT INTO organized_files
               (project_id, original_path, organized_path, doc_type, sheet_number, sheet_title, page_number)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (project_id, original_path, organized_path, doc_type, sheet_number, sheet_title, page_number)
        )
        conn.commit()

        return cursor.lastrowid


def get_organized_files(project_id: str, doc_type: str = None) -> List[Dict]:
    """Get organized files for a project"""
    with get_connection() as conn:
        cursor = conn.cursor()

        if doc_type:
            cursor.execute(
                """SELECT * FROM organized_files
                   WHERE project_id = ? AND doc_type = ?
                   ORDER BY sheet_number""",
                (project_id, doc_type)
            )
        else:
            cursor.execute(
                """SELECT * FROM organized_files
                   WHERE project_id = ?
                   ORDER BY doc_type, sheet_number""",
                (project_id,)
            )

        return [dict(row) for row in cursor.fetchall()]


# Initialize database on import
init_db()
