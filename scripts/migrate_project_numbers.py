#!/usr/bin/env python3
"""
Migration Script: Assign Project Numbers

Migrates all existing projects to the new numbered format:
- B = Bidding
- L = Lead
- O = Opportunity
- A = Awarded
- X = Lost/Not Bid/Gone

Default prefix assignment based on existing bid_decision:
- bid_decision = 'bid' -> B
- bid_decision = 'awarded' -> A
- bid_decision = 'lost' or 'no-bid' -> X
- All others -> L

Usage:
    python3 scripts/migrate_project_numbers.py
    python3 scripts/migrate_project_numbers.py --dry-run  # Preview only
"""

import sys
import argparse
from pathlib import Path
from datetime import datetime

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from modules.database.db import init_db, create_session
from modules.database.models import Project, ProjectStatus, ProjectNumber
from modules.numbering import ProjectNumberingService


def migrate_projects(dry_run: bool = False):
    """
    Migrate all existing projects to numbered format.

    Args:
        dry_run: If True, only preview changes without applying
    """
    print("=" * 60)
    print("Project Number Migration")
    print("=" * 60)

    # Initialize database (creates tables if needed)
    init_db()

    db = create_session()

    try:
        # Get existing project numbers
        existing_numbers = db.query(ProjectNumber.project_id).all()
        existing_ids = {r[0] for r in existing_numbers}
        print(f"\nProjects already numbered: {len(existing_ids)}")

        # Get all projects
        all_projects = db.query(Project).order_by(Project.created_at.asc()).all()
        print(f"Total projects in database: {len(all_projects)}")

        # Projects to migrate
        to_migrate = [p for p in all_projects if p.id not in existing_ids]
        print(f"Projects to migrate: {len(to_migrate)}")

        if not to_migrate:
            print("\nNo projects need migration!")
            return

        print("\n" + "-" * 60)
        print("Migration Plan:")
        print("-" * 60)

        # Determine prefix for each project
        migration_plan = []
        for project in to_migrate:
            # Get bid decision
            status = db.query(ProjectStatus).filter_by(project_id=project.id).first()
            bid_decision = status.bid_decision if status else None

            # Determine prefix
            if bid_decision == 'bid':
                prefix = 'B'
            elif bid_decision == 'awarded':
                prefix = 'A'
            elif bid_decision in ('lost', 'no-bid', 'no_bid'):
                prefix = 'X'
            else:
                prefix = 'L'  # Default to Lead

            migration_plan.append({
                'project': project,
                'prefix': prefix,
                'bid_decision': bid_decision
            })

        # Print plan
        prefix_counts = {'B': 0, 'L': 0, 'O': 0, 'A': 0, 'X': 0}
        for item in migration_plan:
            prefix_counts[item['prefix']] += 1
            print(f"  {item['prefix']}: {item['project'].title[:50]}...")
            print(f"      ID: {item['project'].id}, Decision: {item['bid_decision']}")

        print("\n" + "-" * 60)
        print("Summary by Prefix:")
        print("-" * 60)
        for prefix, count in prefix_counts.items():
            name = ProjectNumberingService.PREFIXES.get(prefix, prefix)
            print(f"  {prefix} ({name}): {count}")

        if dry_run:
            print("\n[DRY RUN] No changes made.")
            return

        # Confirm
        print("\n")
        confirm = input("Proceed with migration? (y/N): ")
        if confirm.lower() != 'y':
            print("Migration cancelled.")
            return

        # Execute migration
        print("\n" + "-" * 60)
        print("Executing Migration...")
        print("-" * 60)

        numbering = ProjectNumberingService(db)
        migrated = 0
        errors = []

        for item in migration_plan:
            try:
                full_number = numbering.assign_number(item['project'].id, item['prefix'])
                print(f"  Assigned {full_number} to {item['project'].title[:40]}...")
                migrated += 1
            except Exception as e:
                error_msg = f"{item['project'].id}: {str(e)}"
                errors.append(error_msg)
                print(f"  ERROR: {error_msg}")

        print("\n" + "=" * 60)
        print("Migration Complete")
        print("=" * 60)
        print(f"Successfully migrated: {migrated}")
        print(f"Errors: {len(errors)}")

        if errors:
            print("\nErrors:")
            for err in errors:
                print(f"  - {err}")

    finally:
        db.close()


def show_stats():
    """Show current project number statistics."""
    init_db()
    db = create_session()

    try:
        numbering = ProjectNumberingService(db)
        stats = numbering.get_stats()

        print("\n" + "=" * 40)
        print("Project Number Statistics")
        print("=" * 40)
        print(f"\nTotal numbered projects: {stats['total']}")
        print("\nBy prefix:")
        for prefix, info in stats.items():
            if prefix != 'total' and isinstance(info, dict):
                print(f"  {prefix} ({info['name']}): {info['count']}")

    finally:
        db.close()


def main():
    parser = argparse.ArgumentParser(description="Migrate projects to numbered format")
    parser.add_argument('--dry-run', action='store_true', help='Preview changes without applying')
    parser.add_argument('--stats', action='store_true', help='Show current statistics only')

    args = parser.parse_args()

    if args.stats:
        show_stats()
    else:
        migrate_projects(dry_run=args.dry_run)


if __name__ == "__main__":
    main()
