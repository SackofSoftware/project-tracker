"""
Job Queue Worker

Background worker thread that polls the job queue and executes tasks.
"""
import threading
import time
import traceback
from typing import Optional, Callable, Dict, Any

from . import JobQueueManager, Job


class JobWorker:
    """
    Background worker that processes jobs from the queue.

    Runs as a daemon thread, polling for new jobs and executing them
    via registered task handlers.
    """

    def __init__(self, queue: JobQueueManager = None, sse_broadcast: Callable = None):
        """
        Initialize the worker.

        Args:
            queue: JobQueueManager instance (uses singleton if not provided)
            sse_broadcast: Optional callback to broadcast SSE events
        """
        self.queue = queue or JobQueueManager()
        self.sse_broadcast = sse_broadcast
        self.running = False
        self.current_job: Optional[Job] = None
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._task_handlers: Dict[str, Callable] = {}

        # Register built-in task handlers
        self._register_default_handlers()

    def _register_default_handlers(self):
        """Register default task handlers."""
        # Import handlers from tasks module
        try:
            from .tasks import TASK_HANDLERS
            for task_type, handler in TASK_HANDLERS.items():
                self._task_handlers[task_type] = handler
                print(f"[Worker] Loaded handler: {task_type}")
        except ImportError as e:
            print(f"[Worker] Warning: Could not load task handlers: {e}")

    def register_handler(self, task_type: str, handler: Callable):
        """
        Register a task handler.

        Args:
            task_type: Task type string (e.g., 'planhub_sync')
            handler: Callable that takes (job, progress_callback) and returns result dict
        """
        self._task_handlers[task_type] = handler
        print(f"[Worker] Registered handler for: {task_type}")

    def start(self):
        """Start the worker thread."""
        if self.running:
            print("[Worker] Already running")
            return

        self.running = True
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_loop, daemon=True, name="JobWorker")
        self._thread.start()
        print("[Worker] Started")

    def stop(self, timeout: float = 5.0):
        """Stop the worker thread."""
        if not self.running:
            return

        print("[Worker] Stopping...")
        self.running = False
        self._stop_event.set()

        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=timeout)
            if self._thread.is_alive():
                print("[Worker] Warning: Thread did not stop cleanly")

        self._thread = None
        print("[Worker] Stopped")

    def _run_loop(self):
        """Main worker loop - polls for jobs and executes them."""
        poll_interval = 1.0  # seconds

        while self.running and not self._stop_event.is_set():
            try:
                job = self.queue.get_next()

                if job:
                    self._execute_job(job)
                else:
                    # No jobs, wait before polling again
                    self._stop_event.wait(timeout=poll_interval)

            except Exception as e:
                print(f"[Worker] Error in run loop: {e}")
                traceback.print_exc()
                time.sleep(poll_interval)

    def _execute_job(self, job: Job):
        """Execute a single job."""
        self.current_job = job
        job_id = job.job_id

        print(f"[Worker] Starting job: {job_id} ({job.task})")
        self.queue.mark_running(job_id)
        self.queue.add_log(job_id, f"Job started", 'info')
        self._broadcast_status()

        try:
            # Get handler for this task type
            handler = self._task_handlers.get(job.task)

            if not handler:
                raise ValueError(f"No handler registered for task: {job.task}")

            # Create progress callback
            def progress_callback(progress: float = None, message: str = None,
                                 phase: str = None, log: bool = False, level: str = 'info'):
                """Callback for task to report progress."""
                if progress is not None or message or phase:
                    self.queue.update_progress(job_id, progress or 0, message, phase)

                if log and message:
                    self.queue.add_log(job_id, message, level)

                self._broadcast_status()

                # Check if job was cancelled
                current = self.queue.get_status(job_id)
                if current and current.status == 'cancelled':
                    raise InterruptedError("Job was cancelled")

            # Execute the handler
            result = handler(job, progress_callback)

            # Mark completed
            self.queue.complete(job_id, result)
            self.queue.add_log(job_id, "Job completed successfully", 'success')
            print(f"[Worker] Completed: {job_id}")

        except InterruptedError:
            print(f"[Worker] Cancelled: {job_id}")
            self.queue.add_log(job_id, "Job was cancelled", 'warning')

        except Exception as e:
            error_msg = str(e)
            print(f"[Worker] Failed: {job_id} - {error_msg}")
            traceback.print_exc()
            self.queue.fail(job_id, error_msg)
            self.queue.add_log(job_id, f"Job failed: {error_msg}", 'error')

        finally:
            self.current_job = None
            self._broadcast_status()

    def _broadcast_status(self):
        """Broadcast current status via SSE."""
        if self.sse_broadcast:
            try:
                status = self.queue.get_global_status()
                self.sse_broadcast(status)
            except Exception as e:
                print(f"[Worker] SSE broadcast error: {e}")

    @property
    def status(self) -> str:
        """Get worker status string."""
        if not self.running:
            return 'stopped'
        if self.current_job:
            return 'busy'
        return 'idle'

    @property
    def is_busy(self) -> bool:
        """Check if worker is currently executing a job."""
        return self.current_job is not None


# Global worker instance
_worker_instance: Optional[JobWorker] = None
_worker_lock = threading.Lock()


def get_worker() -> JobWorker:
    """Get or create the global worker instance."""
    global _worker_instance
    if _worker_instance is None:
        with _worker_lock:
            if _worker_instance is None:
                _worker_instance = JobWorker()
    return _worker_instance


def start_worker():
    """Start the global worker."""
    worker = get_worker()
    worker.start()
    return worker


def stop_worker():
    """Stop the global worker."""
    global _worker_instance
    if _worker_instance:
        _worker_instance.stop()
