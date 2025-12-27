"""
Database Module for Project Tracker

Centralizes all project data from scattered JSON files into a single SQLite database.

Usage:
    from modules.database import db, queries

    # Initialize database
    db.init_db()

    # Query projects
    projects = queries.get_all_projects()

    # Get session
    from modules.database import get_session
    session = get_session()
"""

from . import models, db, queries
from .db import get_session, create_session, init_db

__all__ = ['models', 'db', 'queries', 'get_session', 'create_session', 'init_db']
