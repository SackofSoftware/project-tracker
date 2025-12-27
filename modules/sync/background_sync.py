"""
Background sync scheduler for ProjectDog and Email Monitor
Uses APScheduler for periodic background tasks
"""

import os
import threading
from datetime import datetime
from typing import Callable, Optional
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger


class BackgroundSync:
    """Manages background synchronization tasks"""

    def __init__(self, sync_interval_hours: int = 24, email_sync_interval_minutes: int = 30, planhub_sync_interval_hours: int = 24):
        self.sync_interval_hours = sync_interval_hours
        self.email_sync_interval_minutes = email_sync_interval_minutes
        self.planhub_sync_interval_hours = planhub_sync_interval_hours
        self.scheduler = BackgroundScheduler()
        self.last_sync = None
        self.last_email_sync = None
        self.last_planhub_sync = None
        self.sync_in_progress = False
        self.email_sync_in_progress = False
        self.planhub_sync_in_progress = False
        self.sync_callback = None
        self.email_sync_callback = None
        self.planhub_sync_callback = None
        self._lock = threading.Lock()

    def set_sync_callback(self, callback: Callable):
        """Set the callback function to run on each ProjectDog sync"""
        self.sync_callback = callback

    def set_email_sync_callback(self, callback: Callable):
        """Set the callback function to run on each email sync"""
        self.email_sync_callback = callback

    def set_planhub_sync_callback(self, callback: Callable):
        """Set the callback function to run on each PlanHub sync"""
        self.planhub_sync_callback = callback

    def _run_sync(self):
        """Execute the sync operation"""
        with self._lock:
            if self.sync_in_progress:
                print("Sync already in progress, skipping...")
                return

            self.sync_in_progress = True

        try:
            print(f"Starting background sync at {datetime.now().isoformat()}")

            if self.sync_callback:
                self.sync_callback()

            self.last_sync = datetime.now()
            print(f"Background sync completed at {self.last_sync.isoformat()}")

        except Exception as e:
            print(f"Background sync failed: {e}")

        finally:
            with self._lock:
                self.sync_in_progress = False

    def _run_email_sync(self):
        """Execute the email sync operation"""
        with self._lock:
            if self.email_sync_in_progress:
                print("Email sync already in progress, skipping...")
                return
            self.email_sync_in_progress = True

        try:
            print(f"Starting email sync at {datetime.now().isoformat()}")

            if self.email_sync_callback:
                self.email_sync_callback()

            self.last_email_sync = datetime.now()
            print(f"Email sync completed at {self.last_email_sync.isoformat()}")

        except Exception as e:
            print(f"Email sync failed: {e}")

        finally:
            with self._lock:
                self.email_sync_in_progress = False

    def _run_planhub_sync(self):
        """Execute the PlanHub sync operation"""
        with self._lock:
            if self.planhub_sync_in_progress:
                print("PlanHub sync already in progress, skipping...")
                return
            self.planhub_sync_in_progress = True

        try:
            print(f"Starting PlanHub sync at {datetime.now().isoformat()}")

            if self.planhub_sync_callback:
                self.planhub_sync_callback()

            self.last_planhub_sync = datetime.now()
            print(f"PlanHub sync completed at {self.last_planhub_sync.isoformat()}")

        except Exception as e:
            print(f"PlanHub sync failed: {e}")
            import traceback
            traceback.print_exc()

        finally:
            with self._lock:
                self.planhub_sync_in_progress = False

    def start(self):
        """Start the background scheduler with all sync jobs"""
        if not self.scheduler.running:
            # ProjectDog sync job
            self.scheduler.add_job(
                self._run_sync,
                trigger=IntervalTrigger(hours=self.sync_interval_hours),
                id='projectdog_sync',
                name='ProjectDog Division 8 Sync',
                replace_existing=True
            )

            # Email sync job (if callback set)
            if self.email_sync_callback:
                self.scheduler.add_job(
                    self._run_email_sync,
                    trigger=IntervalTrigger(minutes=self.email_sync_interval_minutes),
                    id='email_monitor_sync',
                    name='Email Monitor Sync',
                    replace_existing=True
                )

            # PlanHub sync job (if callback set)
            if self.planhub_sync_callback:
                self.scheduler.add_job(
                    self._run_planhub_sync,
                    trigger=IntervalTrigger(hours=self.planhub_sync_interval_hours),
                    id='planhub_sync',
                    name='PlanHub Scraper Sync',
                    replace_existing=True
                )

            self.scheduler.start()
            msg = f"Background sync started (ProjectDog: every {self.sync_interval_hours}h"
            if self.email_sync_callback:
                msg += f", Email: every {self.email_sync_interval_minutes}m"
            if self.planhub_sync_callback:
                msg += f", PlanHub: every {self.planhub_sync_interval_hours}h"
            msg += ")"
            print(msg)

    def stop(self):
        """Stop the background scheduler"""
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)
            print("Background sync stopped")

    def run_now(self):
        """Trigger an immediate ProjectDog sync"""
        thread = threading.Thread(target=self._run_sync)
        thread.start()
        return thread

    def run_email_sync_now(self):
        """Trigger an immediate email sync"""
        thread = threading.Thread(target=self._run_email_sync)
        thread.start()
        return thread

    def run_planhub_sync_now(self):
        """Trigger an immediate PlanHub sync"""
        thread = threading.Thread(target=self._run_planhub_sync)
        thread.start()
        return thread

    def get_status(self) -> dict:
        """Get current sync status for all sync jobs"""
        return {
            "running": self.scheduler.running,
            "projectdog": {
                "sync_in_progress": self.sync_in_progress,
                "last_sync": self.last_sync.isoformat() if self.last_sync else None,
                "interval_hours": self.sync_interval_hours,
                "next_run": self._get_next_run_time('projectdog_sync')
            },
            "email_monitor": {
                "sync_in_progress": self.email_sync_in_progress,
                "last_sync": self.last_email_sync.isoformat() if self.last_email_sync else None,
                "interval_minutes": self.email_sync_interval_minutes,
                "next_run": self._get_next_run_time('email_monitor_sync'),
                "enabled": self.email_sync_callback is not None
            },
            "planhub": {
                "sync_in_progress": self.planhub_sync_in_progress,
                "last_sync": self.last_planhub_sync.isoformat() if self.last_planhub_sync else None,
                "interval_hours": self.planhub_sync_interval_hours,
                "next_run": self._get_next_run_time('planhub_sync'),
                "enabled": self.planhub_sync_callback is not None
            },
            # Legacy fields for backward compatibility
            "sync_in_progress": self.sync_in_progress,
            "last_sync": self.last_sync.isoformat() if self.last_sync else None,
            "interval_hours": self.sync_interval_hours,
            "next_run": self._get_next_run_time('projectdog_sync')
        }

    def _get_next_run_time(self, job_id: str = 'projectdog_sync') -> Optional[str]:
        """Get the next scheduled run time for a job"""
        try:
            job = self.scheduler.get_job(job_id)
            if job and job.next_run_time:
                return job.next_run_time.isoformat()
        except:
            pass
        return None


if __name__ == "__main__":
    import time

    def test_sync():
        print("Test sync running...")
        time.sleep(2)
        print("Test sync complete!")

    sync = BackgroundSync(sync_interval_hours=1)
    sync.set_sync_callback(test_sync)

    print("Starting sync with 1 hour interval...")
    sync.start()

    print("Running immediate sync...")
    sync.run_now().join()

    print(f"Status: {sync.get_status()}")

    sync.stop()
