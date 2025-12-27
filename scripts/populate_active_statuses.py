#!/usr/bin/env python3
"""
One-Time Migration: Populate Status for Active Projects

Scans the bidding folder for active project indicators (takeoffs, quotes, schedules)
and automatically creates or updates status entries for projects with active work.
"""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from modules.tracking.activity_detector import ActivityDetector
from modules.tracking.project_status import ProjectStatusTracker


def populate_active_statuses(bidding_folder: str, data_dir: str, dry_run: bool = True):
    """
    Scan bidding folder and populate status for active projects.

    Args:
        bidding_folder: Path to bidding folder root
        data_dir: Path to data directory for status tracking
        dry_run: If True, don't make changes (default: True)
    """
    detector = ActivityDetector(bidding_folder)
    tracker = ProjectStatusTracker(data_dir)

    created = 0
    updated = 0
    skipped = 0

    bidding_path = Path(bidding_folder)

    print(f"{'=' * 80}")
    print(f"Active Project Status Population")
    print(f"{'=' * 80}")
    print(f"Bidding Folder: {bidding_folder}")
    print(f"Data Directory: {data_dir}")
    print(f"Mode: {'DRY RUN' if dry_run else 'EXECUTE'}")
    print(f"{'=' * 80}\n")

    active_projects = []

    for folder in sorted(bidding_path.iterdir()):
        if not folder.is_dir() or folder.name.startswith('.'):
            continue

        indicators = detector.detect_activity(folder.name)

        if not detector.is_active_bid(indicators):
            continue

        project_id = folder.name
        existing = tracker.get_status(project_id)

        # Determine action
        action = None
        if not existing:
            action = "CREATE"
        elif not existing.get('bid_decision'):
            action = "UPDATE"
        else:
            action = "SKIP"
            skipped += 1

        # Build activity summary
        activity_parts = []
        if indicators.has_takeoffs:
            activity_parts.append(f"{indicators.takeoff_count} takeoffs")
        if indicators.has_quotes:
            activity_parts.append(f"{indicators.quote_count} quotes")
            if indicators.vendor_names:
                activity_parts.append(f"({', '.join(indicators.vendor_names)})")
        if indicators.has_schedules:
            activity_parts.append(f"{indicators.schedule_count} schedules")
        if indicators.has_recent_activity:
            activity_parts.append(f"{indicators.days_since_activity}d ago")

        activity_summary = ', '.join(activity_parts)

        # Display project
        print(f"{action:8} {folder.name:<45} Score: {indicators.activity_score:.2f}")
        print(f"         {activity_summary}")

        active_projects.append({
            'project_id': project_id,
            'folder_name': folder.name,
            'indicators': indicators,
            'action': action,
            'existing': existing
        })

        if dry_run:
            print()
            continue

        # Execute changes
        if action == "CREATE":
            # Create new status entry
            tracker.create_project_status(project_id, folder.name)
            tracker.update_bid_decision(
                project_id,
                decision="bid",
                reason="Auto-detected: Active work found in folder"
            )

            # Add estimate notes if takeoffs found
            if indicators.has_takeoffs:
                tracker.update_estimate(
                    project_id,
                    notes=f"Takeoffs found: {len(indicators.takeoff_files)} files"
                )

            # Add tag
            tracker.add_tag(project_id, "active_bid")
            created += 1

        elif action == "UPDATE":
            # Update existing entry with bid decision
            tracker.update_bid_decision(
                project_id,
                decision="bid",
                reason="Auto-detected: Active work found in folder"
            )
            tracker.add_tag(project_id, "active_bid")
            updated += 1

        print()

    # Summary
    print(f"{'=' * 80}")
    print(f"Summary")
    print(f"{'=' * 80}")
    print(f"Active Projects Found: {len(active_projects)}")
    if dry_run:
        print(f"Would Create: {sum(1 for p in active_projects if p['action'] == 'CREATE')}")
        print(f"Would Update: {sum(1 for p in active_projects if p['action'] == 'UPDATE')}")
        print(f"Would Skip: {sum(1 for p in active_projects if p['action'] == 'SKIP')}")
        print()
        print("Run with --execute to apply changes")
    else:
        print(f"Created: {created}")
        print(f"Updated: {updated}")
        print(f"Skipped: {skipped}")
    print(f"{'=' * 80}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Populate status entries for active projects"
    )
    parser.add_argument(
        '--bidding-folder',
        default=os.getenv("BIDDING_FOLDER", ""),
        help="Path to bidding folder (default: BIDDING_FOLDER env var)"
    )
    parser.add_argument(
        '--data-dir',
        default="static/data",
        help="Path to data directory"
    )
    parser.add_argument(
        '--execute',
        action='store_true',
        help="Execute changes (default: dry run)"
    )

    args = parser.parse_args()

    populate_active_statuses(
        args.bidding_folder,
        args.data_dir,
        dry_run=not args.execute
    )
