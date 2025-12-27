"""
Job Queue Task Handlers

Each task handler is a function that takes (job, progress_callback) and returns a result dict.
"""

# Task handlers will be registered here
TASK_HANDLERS = {}


def register_task(task_type: str):
    """Decorator to register a task handler."""
    def decorator(func):
        TASK_HANDLERS[task_type] = func
        return func
    return decorator


def get_task_handler(task_type: str):
    """Get a task handler by type."""
    return TASK_HANDLERS.get(task_type)


def list_task_types():
    """List all registered task types."""
    return list(TASK_HANDLERS.keys())


def register_all_handlers():
    """Register all built-in task handlers."""
    # Import and register handlers
    try:
        from .planhub_sync import TASK_TYPE, TASK_HANDLER
        TASK_HANDLERS[TASK_TYPE] = TASK_HANDLER
        print(f"[Tasks] Registered handler: {TASK_TYPE}")
    except ImportError as e:
        print(f"[Tasks] Warning: Could not load planhub_sync handler: {e}")

    # Add more handlers here as needed
    # from .projectdog_sync import TASK_TYPE, TASK_HANDLER
    # TASK_HANDLERS[TASK_TYPE] = TASK_HANDLER


# Auto-register handlers on module import
register_all_handlers()
