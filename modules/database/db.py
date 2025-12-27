"""
Database Connection and Session Management

Handles SQLite database initialization, connection management, and migrations.
"""

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker, scoped_session
from sqlalchemy.pool import StaticPool
from contextlib import contextmanager
from pathlib import Path
import logging

from .models import Base

logger = logging.getLogger(__name__)

# Database path
DB_PATH = Path(__file__).parent.parent.parent / "data" / "project_tracker.db"


def get_db_path() -> Path:
    """Get database path, ensuring directory exists"""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    return DB_PATH


# Create engine with SQLite optimizations
engine = create_engine(
    f"sqlite:///{get_db_path()}",
    echo=False,  # Set to True for SQL debugging
    connect_args={
        'check_same_thread': False,
        'timeout': 30
    },
    poolclass=StaticPool
)

# Enable foreign keys for SQLite
@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_conn, connection_record):
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA journal_mode=WAL")  # Write-Ahead Logging for better concurrency
    cursor.close()


# Create session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
ScopedSession = scoped_session(SessionLocal)


def init_db():
    """
    Initialize database schema.
    Creates all tables defined in models.py if they don't exist.
    """
    try:
        Base.metadata.create_all(bind=engine)
        logger.info(f"Database initialized at {get_db_path()}")
        # Run migrations for existing tables
        run_migrations()
        return True
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        raise


def run_migrations():
    """
    Run incremental migrations to add new columns to existing tables.
    SQLite doesn't support ALTER TABLE ADD COLUMN IF NOT EXISTS,
    so we check column existence first.
    """
    migrations = [
        # Add workflow status columns to projects table
        ("projects", "workflow_status", "TEXT DEFAULT 'bid_opportunity'"),
        ("projects", "workflow_status_changed_at", "DATETIME"),
        ("projects", "workflow_status_notes", "TEXT"),
        ("projects", "last_synced_at", "DATETIME"),
    ]

    with get_session() as session:
        for table, column, col_type in migrations:
            try:
                # Check if column exists
                result = session.execute(
                    text(f"PRAGMA table_info({table})")
                ).fetchall()
                existing_columns = [row[1] for row in result]

                if column not in existing_columns:
                    session.execute(
                        text(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}")
                    )
                    logger.info(f"Added column {column} to {table}")
            except Exception as e:
                logger.warning(f"Migration for {table}.{column} skipped: {e}")


def drop_all_tables():
    """
    Drop all tables. USE WITH CAUTION!
    Only use this for complete database resets during development.
    """
    logger.warning("Dropping all tables from database")
    Base.metadata.drop_all(bind=engine)
    logger.info("All tables dropped")


def reset_db():
    """
    Complete database reset: drop all tables and recreate them.
    USE WITH CAUTION - ALL DATA WILL BE LOST!
    """
    logger.warning("Resetting database - all data will be lost")
    drop_all_tables()
    init_db()
    logger.info("Database reset complete")


@contextmanager
def get_session():
    """
    Context manager for database sessions.

    Usage:
        with get_session() as session:
            project = session.query(Project).filter_by(id='some-id').first()
    """
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception as e:
        session.rollback()
        logger.error(f"Database session error: {e}")
        raise
    finally:
        session.close()


def get_db():
    """
    Get database session (for dependency injection in Flask/FastAPI).

    Usage:
        db = get_db()
        try:
            project = db.query(Project).filter_by(id='some-id').first()
            db.commit()
        finally:
            db.close()
    """
    db = SessionLocal()
    try:
        return db
    finally:
        pass  # Don't close here, let caller manage


# Database health check
def check_database():
    """
    Verify database connection and schema integrity.
    Returns dict with status information.
    """
    try:
        with get_session() as session:
            # Try a simple query
            result = session.execute(text("SELECT 1")).fetchone()

            # Get table count
            tables = Base.metadata.tables.keys()

            return {
                'status': 'healthy',
                'path': str(get_db_path()),
                'tables': list(tables),
                'table_count': len(tables),
                'connection': 'ok' if result else 'failed'
            }
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        return {
            'status': 'unhealthy',
            'path': str(get_db_path()),
            'error': str(e)
        }


# Convenience function to create a session
def create_session():
    """Create a new database session"""
    return SessionLocal()
