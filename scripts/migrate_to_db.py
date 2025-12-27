#!/usr/bin/env python3
"""
Data Migration Script - Import existing data into unified database.

Run this once to migrate from file-based storage to database-centric architecture.

Usage:
    python scripts/migrate_to_db.py [--dry-run] [--source SOURCE]

Options:
    --dry-run       Show what would be migrated without making changes
    --source        Only migrate specific source (bidding, brad, planhub, govwin, email)
"""

import os
import sys
import argparse
from pathlib import Path
from datetime import datetime

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()


def migrate_folders(dry_run=False):
    """Migrate bidding/brad/current folder projects."""
    from modules.sync.source_importers.folder_importer import FolderImporter

    results = {}
    folder_sources = {
        'bidding': os.environ.get('BIDDING_FOLDER'),
        'brad': os.environ.get('BRAD_PROJECTS_FOLDER'),
        'current': os.environ.get('CURRENT_PROJECTS_FOLDER'),
    }

    for source_name, folder_path in folder_sources.items():
        if not folder_path or not Path(folder_path).exists():
            print(f"  [{source_name}] Skipped - path not configured or doesn't exist")
            results[source_name] = {'status': 'skipped', 'reason': 'path not found'}
            continue

        print(f"  [{source_name}] Importing from: {folder_path}")

        if dry_run:
            # Count folders without importing
            folder_count = sum(1 for f in Path(folder_path).iterdir() if f.is_dir())
            print(f"      Would import ~{folder_count} projects")
            results[source_name] = {'status': 'dry_run', 'count': folder_count}
        else:
            importer = FolderImporter(source_name, folder_path)
            result = importer.import_all()
            results[source_name] = result
            print(f"      Imported: {result.get('new', 0)} new, {result.get('updated', 0)} updated")

    return results


def migrate_planhub(dry_run=False):
    """Migrate PlanHub database."""
    from modules.sync.source_importers.planhub_importer import PlanHubImporter

    db_path = os.environ.get('PLANHUB_DB_PATH')
    if not db_path or not Path(db_path).exists():
        print("  [planhub] Skipped - database not found")
        return {'status': 'skipped', 'reason': 'database not found'}

    print(f"  [planhub] Importing from: {db_path}")

    if dry_run:
        import sqlite3
        conn = sqlite3.connect(db_path)
        cursor = conn.execute("SELECT COUNT(*) FROM leads WHERE status = 'done'")
        count = cursor.fetchone()[0]
        conn.close()
        print(f"      Would import ~{count} PlanHub leads")
        return {'status': 'dry_run', 'count': count}

    importer = PlanHubImporter(db_path)
    result = importer.import_all()
    print(f"      Imported: {result.get('new', 0)} new, {result.get('updated', 0)} updated")
    return result


def migrate_govwin(dry_run=False):
    """Migrate GovWin database to leads table."""
    from modules.sync.source_importers.govwin_importer import GovWinImporter

    db_path = os.environ.get('GOV_DB_PATH')
    if not db_path or not Path(db_path).exists():
        print("  [govwin] Skipped - database not found")
        return {'status': 'skipped', 'reason': 'database not found'}

    print(f"  [govwin] Importing from: {db_path}")

    if dry_run:
        import sqlite3
        conn = sqlite3.connect(db_path)
        cursor = conn.execute("SELECT COUNT(*) FROM opportunities")
        count = cursor.fetchone()[0]
        conn.close()
        print(f"      Would import ~{count} GovWin opportunities")
        return {'status': 'dry_run', 'count': count}

    importer = GovWinImporter(db_path)
    result = importer.import_all()
    print(f"      Imported: {result.get('new', 0)} new, {result.get('updated', 0)} updated")
    return result


def migrate_email(dry_run=False):
    """Migrate Email Monitor data."""
    from modules.sync.source_importers.email_importer import EmailImporter

    output_path = os.environ.get('EMAIL_MONITOR_PATH')
    if not output_path or not Path(output_path).exists():
        print("  [email] Skipped - path not found")
        return {'status': 'skipped', 'reason': 'path not found'}

    print(f"  [email] Importing from: {output_path}")

    if dry_run:
        email_files = list(Path(output_path).glob('*.json'))
        print(f"      Would import ~{len(email_files)} email records")
        return {'status': 'dry_run', 'count': len(email_files)}

    importer = EmailImporter(output_path)
    result = importer.import_all()
    print(f"      Imported: {result.get('new', 0)} new")
    return result


def migrate_project_status(dry_run=False):
    """Migrate existing project_status.json data."""
    from modules.database.db import get_session
    from modules.database.models import Project

    status_file = Path(__file__).parent.parent / 'static' / 'data' / 'project_status.json'
    if not status_file.exists():
        print("  [status] Skipped - project_status.json not found")
        return {'status': 'skipped', 'reason': 'file not found'}

    import json
    with open(status_file) as f:
        status_data = json.load(f)

    print(f"  [status] Found {len(status_data)} status records")

    if dry_run:
        return {'status': 'dry_run', 'count': len(status_data)}

    updated = 0
    with get_session() as session:
        for project_id, status in status_data.items():
            # Find matching project
            project = session.query(Project).filter(
                (Project.id == project_id) |
                (Project.id == project_id.replace(' ', '-').lower())
            ).first()

            if project:
                # Apply status data
                if status.get('bid_decision'):
                    project.bid_decision = status['bid_decision']
                if status.get('archived'):
                    project.archived = True
                    project.archived_reason = status.get('archived_reason', 'migrated')
                if status.get('tags'):
                    project.trades = ', '.join(status['tags']) if isinstance(status['tags'], list) else status['tags']

                updated += 1

        session.commit()

    print(f"      Updated {updated} project statuses")
    return {'status': 'success', 'updated': updated}


def run_deduplication(dry_run=False):
    """Run deduplication scan after migration."""
    from modules.database.dedup_service import get_dedup_service

    print("  [dedup] Scanning for duplicates...")

    if dry_run:
        print("      Would scan all projects for potential duplicates")
        return {'status': 'dry_run'}

    service = get_dedup_service()
    new_duplicates = service.find_all_potential_duplicates()
    print(f"      Found {len(new_duplicates)} potential duplicates for review")
    return {'status': 'success', 'duplicates_found': len(new_duplicates)}


def main():
    parser = argparse.ArgumentParser(description='Migrate data to unified database')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be done without changes')
    parser.add_argument('--source', choices=['bidding', 'brad', 'planhub', 'govwin', 'email', 'status', 'all'],
                       default='all', help='Specific source to migrate')
    args = parser.parse_args()

    print("=" * 60)
    print("DATABASE MIGRATION")
    print(f"Started: {datetime.now().isoformat()}")
    print(f"Mode: {'DRY RUN' if args.dry_run else 'LIVE'}")
    print("=" * 60)

    # Initialize database
    print("\n1. Initializing database...")
    from modules.database.db import init_db, run_migrations

    if not args.dry_run:
        init_db()
        run_migrations()
        print("   Database initialized")
    else:
        print("   [dry run] Would initialize database")

    results = {}

    # Migrate sources
    print("\n2. Migrating project sources...")

    if args.source in ['all', 'bidding', 'brad']:
        folder_results = migrate_folders(args.dry_run)
        results.update(folder_results)

    if args.source in ['all', 'planhub']:
        results['planhub'] = migrate_planhub(args.dry_run)

    if args.source in ['all', 'govwin']:
        results['govwin'] = migrate_govwin(args.dry_run)

    if args.source in ['all', 'email']:
        results['email'] = migrate_email(args.dry_run)

    if args.source in ['all', 'status']:
        results['status'] = migrate_project_status(args.dry_run)

    # Run deduplication
    print("\n3. Running deduplication...")
    if args.source == 'all':
        results['dedup'] = run_deduplication(args.dry_run)
    else:
        print("   [skipped] Only runs on full migration")

    # Summary
    print("\n" + "=" * 60)
    print("MIGRATION SUMMARY")
    print("=" * 60)

    for source, result in results.items():
        status = result.get('status', 'unknown')
        if status == 'success':
            new = result.get('new', 0)
            updated = result.get('updated', 0)
            print(f"  {source}: {new} new, {updated} updated")
        elif status == 'dry_run':
            count = result.get('count', '?')
            print(f"  {source}: would import ~{count}")
        elif status == 'skipped':
            reason = result.get('reason', 'unknown')
            print(f"  {source}: skipped ({reason})")
        else:
            print(f"  {source}: {status}")

    print("\n" + "=" * 60)
    print(f"Completed: {datetime.now().isoformat()}")

    if args.dry_run:
        print("\nThis was a dry run. Run without --dry-run to apply changes.")


if __name__ == '__main__':
    main()
