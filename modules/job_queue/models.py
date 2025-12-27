"""
Job Queue SQLite Models

Provides disk-backed persistence for the job queue system.
"""
import sqlite3
import json
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List

# Database path
DB_PATH = Path(__file__).parent.parent.parent / "data" / "job_queue.db"


@dataclass
class Job:
    """Represents a job in the queue."""
    id: Optional[int] = None
    job_id: str = ""
    project_id: Optional[str] = None
    task: str = ""
    status: str = "pending"  # pending, running, completed, failed, cancelled
    priority: int = 5  # 1-10, lower = higher priority
    progress: float = 0.0  # 0.0 to 1.0
    current_phase: Optional[str] = None
    message: Optional[str] = None
    error_message: Optional[str] = None
    result_json: Optional[str] = None
    created_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    retries: int = 0
    max_retries: int = 3

    @property
    def result(self) -> Optional[Dict[str, Any]]:
        """Parse result_json into dict."""
        if self.result_json:
            try:
                return json.loads(self.result_json)
            except json.JSONDecodeError:
                return None
        return None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses."""
        return {
            'id': self.id,
            'job_id': self.job_id,
            'project_id': self.project_id,
            'task': self.task,
            'status': self.status,
            'priority': self.priority,
            'progress': self.progress,
            'current_phase': self.current_phase,
            'message': self.message,
            'error_message': self.error_message,
            'result': self.result,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'started_at': self.started_at.isoformat() if self.started_at else None,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None,
            'retries': self.retries,
            'max_retries': self.max_retries,
        }


class JobDatabase:
    """SQLite database for job queue persistence."""

    def __init__(self, db_path: Path = None):
        self.db_path = db_path or DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn: Optional[sqlite3.Connection] = None

    def connect(self):
        """Open database connection."""
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self.create_tables()

    def close(self):
        """Close database connection."""
        if self._conn:
            self._conn.close()
            self._conn = None

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    @property
    def conn(self) -> sqlite3.Connection:
        if not self._conn:
            self.connect()
        return self._conn

    def create_tables(self):
        """Create database tables if they don't exist."""
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id TEXT UNIQUE NOT NULL,
                project_id TEXT,
                task TEXT NOT NULL,
                status TEXT DEFAULT 'pending',
                priority INTEGER DEFAULT 5,
                progress REAL DEFAULT 0.0,
                current_phase TEXT,
                message TEXT,
                error_message TEXT,
                result_json TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                started_at TIMESTAMP,
                completed_at TIMESTAMP,
                retries INTEGER DEFAULT 0,
                max_retries INTEGER DEFAULT 3
            );

            CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
            CREATE INDEX IF NOT EXISTS idx_jobs_project ON jobs(project_id);
            CREATE INDEX IF NOT EXISTS idx_jobs_priority_created ON jobs(priority, created_at);

            CREATE TABLE IF NOT EXISTS job_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id TEXT NOT NULL,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                level TEXT DEFAULT 'info',
                message TEXT NOT NULL,
                FOREIGN KEY (job_id) REFERENCES jobs(job_id)
            );

            CREATE INDEX IF NOT EXISTS idx_job_logs_job ON job_logs(job_id);
        """)
        self.conn.commit()

    def _row_to_job(self, row: sqlite3.Row) -> Job:
        """Convert database row to Job object."""
        return Job(
            id=row['id'],
            job_id=row['job_id'],
            project_id=row['project_id'],
            task=row['task'],
            status=row['status'],
            priority=row['priority'],
            progress=row['progress'],
            current_phase=row['current_phase'],
            message=row['message'],
            error_message=row['error_message'],
            result_json=row['result_json'],
            created_at=datetime.fromisoformat(row['created_at']) if row['created_at'] else None,
            started_at=datetime.fromisoformat(row['started_at']) if row['started_at'] else None,
            completed_at=datetime.fromisoformat(row['completed_at']) if row['completed_at'] else None,
            retries=row['retries'],
            max_retries=row['max_retries'],
        )

    def insert_job(self, job: Job) -> int:
        """Insert a new job into the database."""
        cursor = self.conn.execute("""
            INSERT INTO jobs (job_id, project_id, task, status, priority, message)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (job.job_id, job.project_id, job.task, job.status, job.priority, job.message))
        self.conn.commit()
        return cursor.lastrowid

    def get_job(self, job_id: str) -> Optional[Job]:
        """Get a job by its job_id."""
        cursor = self.conn.execute(
            "SELECT * FROM jobs WHERE job_id = ?", (job_id,)
        )
        row = cursor.fetchone()
        return self._row_to_job(row) if row else None

    def get_next_pending(self) -> Optional[Job]:
        """Get the next pending job (FIFO within priority)."""
        cursor = self.conn.execute("""
            SELECT * FROM jobs
            WHERE status = 'pending'
            ORDER BY priority ASC, created_at ASC
            LIMIT 1
        """)
        row = cursor.fetchone()
        return self._row_to_job(row) if row else None

    def get_running_jobs(self) -> List[Job]:
        """Get all currently running jobs."""
        cursor = self.conn.execute(
            "SELECT * FROM jobs WHERE status = 'running' ORDER BY started_at ASC"
        )
        return [self._row_to_job(row) for row in cursor.fetchall()]

    def get_jobs_by_status(self, status: str, limit: int = 50) -> List[Job]:
        """Get jobs filtered by status."""
        cursor = self.conn.execute(
            "SELECT * FROM jobs WHERE status = ? ORDER BY created_at DESC LIMIT ?",
            (status, limit)
        )
        return [self._row_to_job(row) for row in cursor.fetchall()]

    def get_recent_jobs(self, limit: int = 50) -> List[Job]:
        """Get recent jobs of any status."""
        cursor = self.conn.execute(
            "SELECT * FROM jobs ORDER BY created_at DESC LIMIT ?", (limit,)
        )
        return [self._row_to_job(row) for row in cursor.fetchall()]

    def count_pending(self) -> int:
        """Count pending jobs in queue."""
        cursor = self.conn.execute(
            "SELECT COUNT(*) FROM jobs WHERE status = 'pending'"
        )
        return cursor.fetchone()[0]

    def mark_running(self, job_id: str):
        """Mark a job as running."""
        self.conn.execute("""
            UPDATE jobs
            SET status = 'running', started_at = CURRENT_TIMESTAMP
            WHERE job_id = ?
        """, (job_id,))
        self.conn.commit()

    def update_progress(self, job_id: str, progress: float, message: str = None,
                       phase: str = None):
        """Update job progress."""
        self.conn.execute("""
            UPDATE jobs
            SET progress = ?, message = COALESCE(?, message),
                current_phase = COALESCE(?, current_phase)
            WHERE job_id = ?
        """, (progress, message, phase, job_id))
        self.conn.commit()

    def mark_completed(self, job_id: str, result: Dict[str, Any] = None):
        """Mark a job as completed."""
        result_json = json.dumps(result) if result else None
        self.conn.execute("""
            UPDATE jobs
            SET status = 'completed', progress = 1.0,
                completed_at = CURRENT_TIMESTAMP, result_json = ?
            WHERE job_id = ?
        """, (result_json, job_id))
        self.conn.commit()

    def mark_failed(self, job_id: str, error_message: str):
        """Mark a job as failed."""
        self.conn.execute("""
            UPDATE jobs
            SET status = 'failed', completed_at = CURRENT_TIMESTAMP,
                error_message = ?
            WHERE job_id = ?
        """, (error_message, job_id))
        self.conn.commit()

    def mark_cancelled(self, job_id: str):
        """Mark a job as cancelled."""
        self.conn.execute("""
            UPDATE jobs
            SET status = 'cancelled', completed_at = CURRENT_TIMESTAMP
            WHERE job_id = ?
        """, (job_id,))
        self.conn.commit()

    def add_log(self, job_id: str, message: str, level: str = 'info'):
        """Add a log entry for a job."""
        self.conn.execute("""
            INSERT INTO job_logs (job_id, level, message)
            VALUES (?, ?, ?)
        """, (job_id, level, message))
        self.conn.commit()

    def get_logs(self, job_id: str, limit: int = 100) -> List[Dict[str, Any]]:
        """Get log entries for a job."""
        cursor = self.conn.execute("""
            SELECT timestamp, level, message FROM job_logs
            WHERE job_id = ?
            ORDER BY timestamp DESC
            LIMIT ?
        """, (job_id, limit))
        return [
            {'timestamp': row['timestamp'], 'level': row['level'], 'message': row['message']}
            for row in cursor.fetchall()
        ]

    def cleanup_old_jobs(self, days: int = 30):
        """Remove completed/failed jobs older than specified days."""
        self.conn.execute("""
            DELETE FROM job_logs WHERE job_id IN (
                SELECT job_id FROM jobs
                WHERE status IN ('completed', 'failed', 'cancelled')
                AND completed_at < datetime('now', ?)
            )
        """, (f'-{days} days',))
        self.conn.execute("""
            DELETE FROM jobs
            WHERE status IN ('completed', 'failed', 'cancelled')
            AND completed_at < datetime('now', ?)
        """, (f'-{days} days',))
        self.conn.commit()
