"""
Background Scheduler - Periodic sync of all project sources.

Uses APScheduler to run sync jobs on a configurable schedule.
"""

import os
import logging
from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

from .sync_service import get_sync_service

logger = logging.getLogger(__name__)

# Global scheduler instance
_scheduler = None
_scheduler_started = False


def init_scheduler(app=None):
    """
    Initialize and start the background scheduler.

    Args:
        app: Optional Flask app for context
    """
    global _scheduler, _scheduler_started

    if _scheduler_started:
        logger.info("Scheduler already started")
        return _scheduler

    # Check if auto sync is enabled
    auto_sync = os.environ.get('AUTO_SYNC_ENABLED', 'true').lower() == 'true'
    if not auto_sync:
        logger.info("Auto sync disabled, scheduler not started")
        return None

    _scheduler = BackgroundScheduler(
        job_defaults={
            'coalesce': True,  # Combine missed runs
            'max_instances': 1  # Only one sync at a time
        }
    )

    # Schedule periodic full sync
    sync_hours = int(os.environ.get('SYNC_INTERVAL_HOURS', 24))
    _scheduler.add_job(
        _run_full_sync,
        trigger=IntervalTrigger(hours=sync_hours),
        id='full_sync',
        name='Full Source Sync',
        replace_existing=True
    )
    logger.info(f"Scheduled full sync every {sync_hours} hours")

    # Schedule PlanHub sync (may have different interval)
    planhub_hours = int(os.environ.get('PLANHUB_SYNC_INTERVAL_HOURS', 24))
    if planhub_hours != sync_hours:
        _scheduler.add_job(
            _run_planhub_sync,
            trigger=IntervalTrigger(hours=planhub_hours),
            id='planhub_sync',
            name='PlanHub Sync',
            replace_existing=True
        )
        logger.info(f"Scheduled PlanHub sync every {planhub_hours} hours")

    # Run initial sync after a short delay (30 seconds)
    initial_delay = int(os.environ.get('INITIAL_SYNC_DELAY', 30))
    if initial_delay > 0:
        from datetime import timedelta
        run_time = datetime.now() + timedelta(seconds=initial_delay)
        _scheduler.add_job(
            _run_full_sync,
            trigger='date',
            run_date=run_time,
            id='initial_sync',
            name='Initial Sync'
        )
        logger.info(f"Scheduled initial sync in {initial_delay} seconds")

    _scheduler.start()
    _scheduler_started = True
    logger.info("Background scheduler started")

    return _scheduler


def stop_scheduler():
    """Stop the background scheduler."""
    global _scheduler, _scheduler_started

    if _scheduler and _scheduler_started:
        _scheduler.shutdown(wait=False)
        _scheduler_started = False
        logger.info("Background scheduler stopped")


def get_scheduler():
    """Get the scheduler instance."""
    return _scheduler


def is_scheduler_running():
    """Check if scheduler is running."""
    return _scheduler_started and _scheduler is not None


def _run_full_sync():
    """Execute a full sync of all sources."""
    logger.info("Starting scheduled full sync")
    try:
        service = get_sync_service()
        result = service.sync_all_sources()

        if result.get('status') == 'success':
            logger.info(f"Full sync completed: {result.get('total_projects', 0)} projects")
        else:
            logger.warning(f"Full sync completed with issues: {result.get('errors', [])}")

    except Exception as e:
        logger.error(f"Full sync failed: {e}")


def _run_planhub_sync():
    """Execute a PlanHub-only sync."""
    logger.info("Starting scheduled PlanHub sync")
    try:
        service = get_sync_service()
        result = service.trigger_sync('planhub')

        if result.get('status') == 'success':
            logger.info(f"PlanHub sync completed: {result.get('count', 0)} leads")
        else:
            logger.warning(f"PlanHub sync issue: {result}")

    except Exception as e:
        logger.error(f"PlanHub sync failed: {e}")


def trigger_immediate_sync(source=None):
    """
    Trigger an immediate sync (outside of schedule).

    Args:
        source: Optional specific source to sync

    Returns:
        dict: Sync result
    """
    service = get_sync_service()
    return service.trigger_sync(source)


def get_scheduler_status():
    """Get detailed scheduler status."""
    if not _scheduler or not _scheduler_started:
        return {
            'running': False,
            'jobs': []
        }

    jobs = []
    for job in _scheduler.get_jobs():
        jobs.append({
            'id': job.id,
            'name': job.name,
            'next_run': job.next_run_time.isoformat() if job.next_run_time else None,
            'trigger': str(job.trigger)
        })

    return {
        'running': True,
        'jobs': jobs
    }
