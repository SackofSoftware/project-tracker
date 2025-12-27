#!/usr/bin/env python3
"""
Database Utilities Script

Command-line tool for common database operations.

Usage:
    python3 db_utils.py init              # Initialize database
    python3 db_utils.py migrate           # Run migration (interactive)
    python3 db_utils.py health            # Check database health
    python3 db_utils.py stats             # Show statistics
    python3 db_utils.py reset             # Reset database (CAUTION!)
    python3 db_utils.py example           # Run examples
    python3 db_utils.py count             # Count records in all tables
"""

import sys
import os
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from modules.database import db, queries
from modules.database.migrate import migrate_from_json


def init_database():
    """Initialize database schema"""
    print("Initializing database...")
    db.init_db()
    print(f"Database initialized at: {db.get_db_path()}")

    health = db.check_database()
    print(f"\nStatus: {health['status']}")
    print(f"Tables created: {health['table_count']}")


def check_health():
    """Check database health"""
    print("Checking database health...\n")

    health = db.check_database()

    print(f"Status:     {health['status']}")
    print(f"Path:       {health['path']}")
    print(f"Tables:     {health['table_count']}")
    print(f"Connection: {health['connection']}")

    if health.get('tables'):
        print("\nDatabase Tables:")
        for table in sorted(health['tables']):
            print(f"  - {table}")


def show_stats():
    """Show database statistics"""
    print("Database Statistics\n")

    stats = queries.get_dashboard_stats()

    print(f"Total Projects:           {stats['total_projects']}")
    print(f"  Local Projects:         {stats['local_projects']}")
    print(f"  ProjectDog Projects:    {stats['projectdog_projects']}")
    print(f"\nUpcoming Bids (30 days):  {stats['upcoming_bids']}")
    print(f"\nProjects with Estimates:  {stats['projects_with_estimates']}")
    print(f"Projects with Scope:      {stats['projects_with_scope']}")
    print(f"\nActive Vendors:           {stats['vendors_count']}")
    print(f"Total Quotes:             {stats['total_quotes']}")


def count_records():
    """Count records in all tables"""
    from modules.database.db import get_session
    from modules.database.models import (
        Project, ProjectStatus, ProjectFile, Division8Scope,
        Vendor, VendorQuote, ProjectDogProject, PlanHubLink,
        ProjectNote, ProjectTag, Competitor, ExtractedProjectData
    )

    print("Record Counts by Table\n")

    with get_session() as session:
        counts = {
            'projects': session.query(Project).count(),
            'project_status': session.query(ProjectStatus).count(),
            'project_files': session.query(ProjectFile).count(),
            'division8_scope': session.query(Division8Scope).count(),
            'vendors': session.query(Vendor).count(),
            'vendor_quotes': session.query(VendorQuote).count(),
            'projectdog_projects': session.query(ProjectDogProject).count(),
            'planhub_links': session.query(PlanHubLink).count(),
            'project_notes': session.query(ProjectNote).count(),
            'project_tags': session.query(ProjectTag).count(),
            'competitors': session.query(Competitor).count(),
            'extracted_project_data': session.query(ExtractedProjectData).count(),
        }

    for table, count in sorted(counts.items()):
        print(f"  {table:.<30} {count:>6}")

    print(f"\n  {'TOTAL':.<30} {sum(counts.values()):>6}")


def run_migration():
    """Run migration with interactive prompts"""
    print("Database Migration Utility\n")

    # Check if database exists
    db_path = db.get_db_path()
    if db_path.exists():
        print(f"Database already exists at: {db_path}")
        response = input("Continue anyway? (y/N): ").strip().lower()
        if response != 'y':
            print("Migration cancelled.")
            return

    # Get bidding folder
    default_folder = os.getenv("BIDDING_FOLDER", "")
    if default_folder:
        print(f"\nDefault bidding folder (from BIDDING_FOLDER env): {default_folder}")
    bidding_folder = input("Enter bidding folder path (or press Enter for default): ").strip()

    if not bidding_folder:
        bidding_folder = default_folder
        if not bidding_folder:
            print("Error: No bidding folder specified and BIDDING_FOLDER not set")
            return

    if not Path(bidding_folder).exists():
        print(f"Error: Folder not found: {bidding_folder}")
        return

    # Ask about options
    print("\nMigration Options:")
    skip_projectdog = input("Skip ProjectDog import? (y/N): ").strip().lower() == 'y'
    skip_local = input("Skip local projects? (y/N): ").strip().lower() == 'y'

    # Confirm
    print("\nMigration Settings:")
    print(f"  Bidding Folder:    {bidding_folder}")
    print(f"  Skip ProjectDog:   {skip_projectdog}")
    print(f"  Skip Local:        {skip_local}")

    response = input("\nProceed with migration? (y/N): ").strip().lower()
    if response != 'y':
        print("Migration cancelled.")
        return

    # Run migration
    print("\nStarting migration...\n")
    stats = migrate_from_json(
        bidding_folder=bidding_folder,
        skip_projectdog=skip_projectdog,
        skip_local=skip_local
    )

    print("\nMigration complete!")


def reset_database():
    """Reset database (DANGER!)"""
    print("=" * 60)
    print("WARNING: DATABASE RESET")
    print("=" * 60)
    print("\nThis will DELETE ALL DATA in the database!")
    print("This action CANNOT be undone!")
    print("\nYou should have a backup before proceeding.")

    response = input("\nType 'DELETE ALL DATA' to confirm: ").strip()

    if response != 'DELETE ALL DATA':
        print("Reset cancelled.")
        return

    print("\nResetting database...")
    db.reset_db()
    print("Database has been reset!")


def run_examples():
    """Run example script"""
    print("Running database examples...\n")
    from modules.database import example
    example.run_all_examples()


def show_help():
    """Show help message"""
    print(__doc__)


def main():
    """Main entry point"""
    if len(sys.argv) < 2:
        show_help()
        return

    command = sys.argv[1].lower()

    commands = {
        'init': init_database,
        'migrate': run_migration,
        'health': check_health,
        'stats': show_stats,
        'reset': reset_database,
        'example': run_examples,
        'count': count_records,
        'help': show_help,
    }

    if command in commands:
        commands[command]()
    else:
        print(f"Unknown command: {command}")
        print()
        show_help()


if __name__ == '__main__':
    main()
