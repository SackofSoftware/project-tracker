"""
SQLite Database Operations for PlanHub Scraper
Handles lead state, file metadata, and resume capability.
"""
import sqlite3
import json
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any
from dataclasses import dataclass

from .config import DB_PATH


@dataclass
class Lead:
    id: int
    planhub_id: str
    url: str
    name: str
    status: str
    attempts: int
    skip_reason: Optional[str] = None
    error_msg: Optional[str] = None
    bid_due_date: Optional[str] = None
    time_remaining: Optional[str] = None
    project_info_json: Optional[str] = None
    contractors_json: Optional[str] = None
    market_intel_json: Optional[str] = None
    qa_json: Optional[str] = None
    material_estimates_json: Optional[str] = None
    raw_html_path: Optional[str] = None


@dataclass
class ProjectFile:
    id: int
    lead_id: int
    file_name: str
    file_type: Optional[str]
    file_size: Optional[str]
    upload_date: Optional[str]
    uploaded_by: Optional[str]
    download_url: Optional[str]


class Database:
    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = db_path
        self.conn = None

    def connect(self):
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        return self

    def close(self):
        if self.conn:
            self.conn.close()

    def __enter__(self):
        return self.connect()

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def create_tables(self):
        """Create database tables if they don't exist"""
        cursor = self.conn.cursor()

        # Main leads table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS leads (
                id INTEGER PRIMARY KEY,
                planhub_id TEXT UNIQUE,
                url TEXT,
                name TEXT,
                status TEXT DEFAULT 'queued',
                skip_reason TEXT,
                attempts INTEGER DEFAULT 0,
                error_msg TEXT,
                last_seen_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

                -- Project Info data
                bid_due_date TEXT,
                time_remaining TEXT,
                project_info_json TEXT,

                -- Other tabs data (JSON blobs)
                contractors_json TEXT,
                market_intel_json TEXT,
                qa_json TEXT,
                material_estimates_json TEXT,

                -- Fallback
                raw_html_path TEXT
            )
        """)

        # Project files metadata table (no downloads)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS project_files (
                id INTEGER PRIMARY KEY,
                lead_id INTEGER,
                file_name TEXT,
                file_type TEXT,
                file_size TEXT,
                upload_date TEXT,
                uploaded_by TEXT,
                download_url TEXT,
                FOREIGN KEY (lead_id) REFERENCES leads(id)
            )
        """)

        # Pagination state for resume capability
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS pagination_state (
                id INTEGER PRIMARY KEY,
                last_page INTEGER DEFAULT 1,
                total_leads_found INTEGER DEFAULT 0,
                discovery_complete INTEGER DEFAULT 0,
                last_updated TIMESTAMP
            )
        """)

        # Indexes for faster lookups
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_leads_status ON leads(status)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_leads_planhub_id ON leads(planhub_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_files_lead ON project_files(lead_id)")

        self.conn.commit()
        print("Database tables created/verified.")

    # ==============================================
    # Lead Operations
    # ==============================================

    def add_lead(self, lead_data: dict, is_locked: bool = False) -> bool:
        """Add a lead from discovery, returns True if new lead added"""
        cursor = self.conn.cursor()

        status = 'skipped' if is_locked else 'queued'
        skip_reason = 'locked' if is_locked else None

        try:
            cursor.execute("""
                INSERT OR IGNORE INTO leads
                (planhub_id, url, name, status, skip_reason, last_seen_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                lead_data.get('planhub_id'),
                lead_data.get('url'),
                lead_data.get('name'),
                status,
                skip_reason,
                datetime.now().isoformat()
            ))
            self.conn.commit()
            return cursor.rowcount > 0
        except Exception as e:
            print(f"Error adding lead: {e}")
            return False

    def get_next_queued(self) -> Optional[Lead]:
        """Get next lead to process, skipping locked ones"""
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT * FROM leads
            WHERE status = 'queued'
            AND skip_reason IS NULL
            AND attempts < 3
            ORDER BY id
            LIMIT 1
        """)
        row = cursor.fetchone()
        if row:
            return Lead(**dict(row))
        return None

    def mark_in_progress(self, lead_id: int):
        """Mark a lead as being processed"""
        cursor = self.conn.cursor()
        cursor.execute("""
            UPDATE leads
            SET status = 'in_progress', attempts = attempts + 1
            WHERE id = ?
        """, (lead_id,))
        self.conn.commit()

    def mark_done(self, lead_id: int):
        """Mark a lead as successfully processed"""
        cursor = self.conn.cursor()
        cursor.execute("""
            UPDATE leads
            SET status = 'done', last_seen_at = ?
            WHERE id = ?
        """, (datetime.now().isoformat(), lead_id))
        self.conn.commit()

    def mark_error(self, lead_id: int, error_msg: str):
        """Mark a lead as failed with error message"""
        cursor = self.conn.cursor()
        cursor.execute("""
            UPDATE leads
            SET status = 'error', error_msg = ?, last_seen_at = ?
            WHERE id = ?
        """, (error_msg, datetime.now().isoformat(), lead_id))
        self.conn.commit()

    def save_lead_data(self, lead_id: int, data: dict):
        """Save scraped data for a lead"""
        cursor = self.conn.cursor()

        # Extract specific fields
        project_info = data.get('project_info', {})
        bid_due_date = project_info.get('bid_due_date')
        time_remaining = project_info.get('time_remaining')

        cursor.execute("""
            UPDATE leads SET
                bid_due_date = ?,
                time_remaining = ?,
                project_info_json = ?,
                contractors_json = ?,
                market_intel_json = ?,
                qa_json = ?,
                material_estimates_json = ?
            WHERE id = ?
        """, (
            bid_due_date,
            time_remaining,
            json.dumps(project_info) if project_info else None,
            json.dumps(data.get('contractors', [])),
            json.dumps(data.get('market_intel', {})),
            json.dumps(data.get('qa', [])),
            json.dumps(data.get('material_estimates', {})),
            lead_id
        ))
        self.conn.commit()

    def save_raw_html(self, lead_id: int, html_path: str):
        """Save path to fallback HTML file"""
        cursor = self.conn.cursor()
        cursor.execute("""
            UPDATE leads SET raw_html_path = ? WHERE id = ?
        """, (html_path, lead_id))
        self.conn.commit()

    def reset_in_progress(self) -> int:
        """Reset any in_progress leads back to queued (crash recovery)"""
        cursor = self.conn.cursor()
        cursor.execute("""
            UPDATE leads SET status = 'queued' WHERE status = 'in_progress'
        """)
        count = cursor.rowcount
        self.conn.commit()
        if count > 0:
            print(f"Reset {count} in_progress leads back to queued")
        return count

    # ==============================================
    # File Operations
    # ==============================================

    def add_file(self, lead_id: int, file_data: dict):
        """Add file metadata for a lead"""
        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT INTO project_files
            (lead_id, file_name, file_type, file_size, upload_date, uploaded_by, download_url)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            lead_id,
            file_data.get('file_name'),
            file_data.get('file_type'),
            file_data.get('file_size'),
            file_data.get('upload_date'),
            file_data.get('uploaded_by'),
            file_data.get('download_url')
        ))
        self.conn.commit()

    def get_files_for_lead(self, lead_id: int) -> List[ProjectFile]:
        """Get all file metadata for a lead"""
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM project_files WHERE lead_id = ?", (lead_id,))
        return [ProjectFile(**dict(row)) for row in cursor.fetchall()]

    # ==============================================
    # Pagination State
    # ==============================================

    def get_pagination_state(self) -> Optional[dict]:
        """Get current pagination/discovery state"""
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM pagination_state ORDER BY id DESC LIMIT 1")
        row = cursor.fetchone()
        return dict(row) if row else None

    def update_pagination_state(self, page: int, total_found: int = None):
        """Update pagination state for resume capability"""
        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO pagination_state
            (id, last_page, total_leads_found, last_updated)
            VALUES (1, ?, COALESCE(?, (SELECT total_leads_found FROM pagination_state WHERE id=1)), ?)
        """, (page, total_found, datetime.now().isoformat()))
        self.conn.commit()

    def mark_discovery_complete(self, total_found: int = None):
        """Mark lead discovery as complete"""
        cursor = self.conn.cursor()
        cursor.execute("""
            UPDATE pagination_state
            SET discovery_complete = 1, total_leads_found = COALESCE(?, total_leads_found), last_updated = ?
            WHERE id = 1
        """, (total_found, datetime.now().isoformat()))
        self.conn.commit()

    def reset_discovery(self):
        """Reset discovery state to start over"""
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM pagination_state")
        cursor.execute("UPDATE leads SET status = 'queued' WHERE skip_reason IS NULL")
        self.conn.commit()
        print("Discovery state reset.")

    # ==============================================
    # Statistics
    # ==============================================

    def get_stats(self) -> dict:
        """Get scraping statistics"""
        cursor = self.conn.cursor()

        stats = {}

        # Total leads
        cursor.execute("SELECT COUNT(*) FROM leads")
        stats['total_leads'] = cursor.fetchone()[0]

        # By status
        cursor.execute("SELECT status, COUNT(*) FROM leads GROUP BY status")
        for row in cursor.fetchall():
            stats[row[0]] = row[1]

        # Locked/skipped
        cursor.execute("SELECT COUNT(*) FROM leads WHERE skip_reason = 'locked'")
        stats['locked'] = cursor.fetchone()[0]

        # Total files
        cursor.execute("SELECT COUNT(*) FROM project_files")
        stats['total_files'] = cursor.fetchone()[0]

        # Calculate progress
        done = stats.get('done', 0)
        total = stats['total_leads'] - stats.get('locked', 0)
        stats['progress_pct'] = round(done / total * 100, 1) if total > 0 else 0

        return stats


def init_database():
    """Initialize the database"""
    with Database() as db:
        db.create_tables()
    print(f"Database initialized at: {DB_PATH}")


def show_stats():
    """Display current statistics"""
    with Database() as db:
        stats = db.get_stats()

    print("\n=== PlanHub Scraper Status ===")
    print(f"Total Leads:    {stats.get('total_leads', 0)}")
    print(f"  Queued:       {stats.get('queued', 0)}")
    print(f"  In Progress:  {stats.get('in_progress', 0)}")
    print(f"  Done:         {stats.get('done', 0)}")
    print(f"  Errors:       {stats.get('error', 0)}")
    print(f"  Locked:       {stats.get('locked', 0)}")
    print(f"Files Found:    {stats.get('total_files', 0)}")
    print(f"Progress:       {stats.get('progress_pct', 0)}%")
    print()


if __name__ == "__main__":
    init_database()
    show_stats()
