"""
Job Queue Module

Provides a disk-backed job queue system with SQLite persistence for
background task processing.

Usage:
    from modules.job_queue import JobQueueManager

    queue = JobQueueManager()
    job_id = queue.enqueue('planhub_sync')
    status = queue.get_status(job_id)
"""
import threading
import uuid
from datetime import datetime
from typing import Optional, Dict, Any, List, Callable

from .models import JobDatabase, Job

__all__ = ['JobQueueManager', 'Job']


class JobQueueManager:
    """
    Manages the job queue with SQLite persistence.

    Thread-safe singleton that provides FIFO job scheduling with priority support.
    """

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._db = JobDatabase()
        self._db.connect()
        self._subscribers: List[Callable[[Job], None]] = []
        self._db_lock = threading.Lock()

    def subscribe(self, callback: Callable[[Job], None]):
        """Subscribe to job updates."""
        self._subscribers.append(callback)

    def unsubscribe(self, callback: Callable[[Job], None]):
        """Unsubscribe from job updates."""
        if callback in self._subscribers:
            self._subscribers.remove(callback)

    def _notify(self, job: Job):
        """Notify all subscribers of job update."""
        for callback in self._subscribers:
            try:
                callback(job)
            except Exception as e:
                print(f"Error notifying subscriber: {e}")

    def _generate_job_id(self) -> str:
        """Generate a unique job ID."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        short_uuid = uuid.uuid4().hex[:6]
        return f"job_{timestamp}_{short_uuid}"

    def enqueue(self, task: str, project_id: str = None, priority: int = 5,
                message: str = None) -> str:
        """
        Add a new job to the queue.

        Args:
            task: Task type (e.g., 'planhub_sync', 'projectdog_sync')
            project_id: Optional project scope
            priority: 1-10, lower = higher priority (default: 5)
            message: Optional initial message

        Returns:
            job_id: Unique identifier for the job
        """
        job_id = self._generate_job_id()

        job = Job(
            job_id=job_id,
            project_id=project_id,
            task=task,
            status='pending',
            priority=priority,
            message=message or f"Queued {task}",
        )

        with self._db_lock:
            self._db.insert_job(job)
            job = self._db.get_job(job_id)

        self._notify(job)
        print(f"[JobQueue] Enqueued: {job_id} ({task})")
        return job_id

    def get_next(self) -> Optional[Job]:
        """
        Get the next pending job (FIFO within priority).

        Returns None if queue is empty.
        """
        with self._db_lock:
            return self._db.get_next_pending()

    def mark_running(self, job_id: str):
        """Mark a job as running."""
        with self._db_lock:
            self._db.mark_running(job_id)
            job = self._db.get_job(job_id)
        if job:
            self._notify(job)
            print(f"[JobQueue] Running: {job_id}")

    def update_progress(self, job_id: str, progress: float, message: str = None,
                       phase: str = None):
        """
        Update job progress.

        Args:
            job_id: Job identifier
            progress: Progress value 0.0 to 1.0
            message: Optional status message
            phase: Optional current phase name
        """
        with self._db_lock:
            self._db.update_progress(job_id, progress, message, phase)
            job = self._db.get_job(job_id)
        if job:
            self._notify(job)

    def complete(self, job_id: str, result: Dict[str, Any] = None):
        """Mark a job as completed with optional result data."""
        with self._db_lock:
            self._db.mark_completed(job_id, result)
            job = self._db.get_job(job_id)
        if job:
            self._notify(job)
            print(f"[JobQueue] Completed: {job_id}")

    def fail(self, job_id: str, error_message: str):
        """Mark a job as failed with error message."""
        with self._db_lock:
            self._db.mark_failed(job_id, error_message)
            job = self._db.get_job(job_id)
        if job:
            self._notify(job)
            print(f"[JobQueue] Failed: {job_id} - {error_message}")

    def cancel(self, job_id: str) -> bool:
        """
        Cancel a pending or running job.

        Returns True if cancelled, False if job not found or already finished.
        """
        job = self.get_status(job_id)
        if not job:
            return False

        if job.status in ('completed', 'failed', 'cancelled'):
            return False

        with self._db_lock:
            self._db.mark_cancelled(job_id)
            job = self._db.get_job(job_id)

        if job:
            self._notify(job)
            print(f"[JobQueue] Cancelled: {job_id}")
        return True

    def get_status(self, job_id: str) -> Optional[Job]:
        """Get current status of a job."""
        with self._db_lock:
            return self._db.get_job(job_id)

    def get_queue_depth(self) -> int:
        """Get number of pending jobs in queue."""
        with self._db_lock:
            return self._db.count_pending()

    def get_running_jobs(self) -> List[Job]:
        """Get all currently running jobs."""
        with self._db_lock:
            return self._db.get_running_jobs()

    def get_active_job(self) -> Optional[Job]:
        """Get the currently active (running) job, if any."""
        running = self.get_running_jobs()
        return running[0] if running else None

    def get_recent_jobs(self, limit: int = 50) -> List[Job]:
        """Get recent jobs of any status."""
        with self._db_lock:
            return self._db.get_recent_jobs(limit)

    def get_jobs_by_status(self, status: str, limit: int = 50) -> List[Job]:
        """Get jobs filtered by status."""
        with self._db_lock:
            return self._db.get_jobs_by_status(status, limit)

    def add_log(self, job_id: str, message: str, level: str = 'info'):
        """Add a log entry for a job."""
        with self._db_lock:
            self._db.add_log(job_id, message, level)

    def get_logs(self, job_id: str, limit: int = 100) -> List[Dict[str, Any]]:
        """Get log entries for a job."""
        with self._db_lock:
            return self._db.get_logs(job_id, limit)

    def get_global_status(self) -> Dict[str, Any]:
        """
        Get global queue status for the footer.

        Returns dict with active_job, queue_depth, and worker_status.
        """
        active = self.get_active_job()
        return {
            'active_job': active.to_dict() if active else None,
            'queue_depth': self.get_queue_depth(),
            'has_active': active is not None,
        }

    def cleanup(self, days: int = 30):
        """Remove old completed/failed jobs."""
        with self._db_lock:
            self._db.cleanup_old_jobs(days)
        print(f"[JobQueue] Cleaned up jobs older than {days} days")
