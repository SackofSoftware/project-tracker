"""
Job Queue API Routes

Provides REST API endpoints for managing background jobs.
"""
from flask import Blueprint, jsonify, request, Response
import queue
import json

jobs_bp = Blueprint('jobs', __name__)

# Lazy import to avoid circular dependencies
_queue_manager = None
_job_worker = None


def get_queue_manager():
    """Get or create the JobQueueManager singleton."""
    global _queue_manager
    if _queue_manager is None:
        from modules.job_queue import JobQueueManager
        _queue_manager = JobQueueManager()
    return _queue_manager


def get_job_worker():
    """Get or create the JobWorker singleton."""
    global _job_worker
    if _job_worker is None:
        from modules.job_queue.worker import get_worker
        _job_worker = get_worker()
    return _job_worker


@jobs_bp.route('/api/jobs', methods=['GET'])
def list_jobs():
    """
    List jobs with optional status filter.

    Query params:
        status: Filter by status (pending, running, completed, failed)
        limit: Max results (default 50)
    """
    queue_mgr = get_queue_manager()

    status = request.args.get('status')
    limit = int(request.args.get('limit', 50))

    if status:
        jobs = queue_mgr.get_jobs_by_status(status, limit)
    else:
        jobs = queue_mgr.get_recent_jobs(limit)

    return jsonify({
        'jobs': [j.to_dict() for j in jobs],
        'count': len(jobs)
    })


@jobs_bp.route('/api/jobs', methods=['POST'])
def create_job():
    """
    Create a new job.

    Request body:
        task: Task type (required) - 'planhub_sync', 'projectdog_sync', etc.
        project_id: Optional project scope
        priority: 1-10, lower = higher priority (default 5)
        message: Optional initial message
    """
    data = request.get_json()

    if not data or 'task' not in data:
        return jsonify({'error': 'task is required'}), 400

    task = data['task']
    project_id = data.get('project_id')
    priority = data.get('priority', 5)
    message = data.get('message')

    # Validate task type
    from modules.job_queue.tasks import list_task_types
    valid_tasks = list_task_types()
    if task not in valid_tasks:
        return jsonify({
            'error': f'Invalid task type: {task}',
            'valid_tasks': valid_tasks
        }), 400

    queue_mgr = get_queue_manager()
    job_id = queue_mgr.enqueue(task, project_id, priority, message)

    return jsonify({
        'job_id': job_id,
        'status': 'queued',
        'message': f'Job {job_id} queued for {task}'
    }), 201


@jobs_bp.route('/api/jobs/<job_id>', methods=['GET'])
def get_job(job_id):
    """
    Get job details and progress.
    """
    queue_mgr = get_queue_manager()
    job = queue_mgr.get_status(job_id)

    if not job:
        return jsonify({'error': f'Job not found: {job_id}'}), 404

    result = job.to_dict()

    # Include logs if requested
    if request.args.get('include_logs') == 'true':
        result['logs'] = queue_mgr.get_logs(job_id)

    return jsonify(result)


@jobs_bp.route('/api/jobs/<job_id>/logs', methods=['GET'])
def get_job_logs(job_id):
    """
    Get log entries for a job.
    """
    queue_mgr = get_queue_manager()
    limit = int(request.args.get('limit', 100))

    logs = queue_mgr.get_logs(job_id, limit)
    return jsonify({
        'job_id': job_id,
        'logs': logs,
        'count': len(logs)
    })


@jobs_bp.route('/api/jobs/<job_id>/cancel', methods=['POST'])
def cancel_job(job_id):
    """
    Cancel a pending or running job.
    """
    queue_mgr = get_queue_manager()

    if queue_mgr.cancel(job_id):
        return jsonify({
            'job_id': job_id,
            'status': 'cancelled',
            'message': f'Job {job_id} cancelled'
        })
    else:
        return jsonify({
            'error': f'Could not cancel job {job_id} - may already be finished'
        }), 400


@jobs_bp.route('/api/jobs/status', methods=['GET'])
def global_status():
    """
    Get global queue status for the footer.

    Returns:
        active_job: Currently running job (if any)
        queue_depth: Number of pending jobs
        worker_status: 'idle', 'busy', or 'stopped'
    """
    queue_mgr = get_queue_manager()
    worker = get_job_worker()

    status = queue_mgr.get_global_status()
    status['worker_status'] = worker.status

    return jsonify(status)


@jobs_bp.route('/api/jobs/tasks', methods=['GET'])
def list_task_types():
    """
    List available task types.
    """
    from modules.job_queue.tasks import list_task_types as get_tasks
    return jsonify({
        'task_types': get_tasks()
    })


@jobs_bp.route('/api/jobs/stream')
def stream_job_events():
    """
    SSE endpoint for real-time job status updates.

    Streams job_update and job_log events to all connected clients.
    """
    def generate():
        # Create a queue for this client
        client_queue = queue.Queue()

        # Subscribe to job updates
        queue_mgr = get_queue_manager()

        def on_job_update(job):
            """Called when any job is updated."""
            try:
                event_data = {
                    'active_job': job.to_dict() if job.status == 'running' else None,
                    'queue_depth': queue_mgr.get_queue_depth(),
                    'job': job.to_dict()
                }
                client_queue.put(('job_update', event_data))
            except Exception:
                pass

        queue_mgr.subscribe(on_job_update)

        try:
            # Send initial status
            status = queue_mgr.get_global_status()
            status['worker_status'] = get_job_worker().status
            yield f"event: connected\ndata: {json.dumps(status)}\n\n"

            while True:
                try:
                    event_type, data = client_queue.get(timeout=30)
                    yield f"event: {event_type}\ndata: {json.dumps(data)}\n\n"
                except queue.Empty:
                    # Send heartbeat
                    yield f"event: heartbeat\ndata: {json.dumps({'status': 'alive'})}\n\n"
        finally:
            queue_mgr.unsubscribe(on_job_update)

    return Response(
        generate(),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
            'X-Accel-Buffering': 'no'
        }
    )


# Quick sync endpoints for common tasks
@jobs_bp.route('/api/jobs/sync/planhub', methods=['POST'])
def trigger_planhub_sync():
    """
    Quick endpoint to trigger PlanHub sync.
    """
    queue_mgr = get_queue_manager()

    # Check if a PlanHub sync is already running
    running = queue_mgr.get_running_jobs()
    for job in running:
        if job.task == 'planhub_sync':
            return jsonify({
                'error': 'PlanHub sync already running',
                'job_id': job.job_id
            }), 409

    job_id = queue_mgr.enqueue('planhub_sync', message='Manual PlanHub sync')

    return jsonify({
        'job_id': job_id,
        'status': 'queued',
        'message': 'PlanHub sync started'
    }), 201
