#!/usr/bin/env python3
"""
Batch PlanHub Auto-Linker

Automatically links PlanHub projects to local bidding folders using
fuzzy matching on project name, location, and bid date.

Uses the existing PlanHubLocalMatcher to find and create links.
"""

import json
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from modules.planhub.planhub_reader import load_planhub_projects
from modules.planhub.planhub_matcher import PlanHubLocalMatcher
from modules.bidding.bidding_reader import BiddingFolderReader

import os
from dotenv import load_dotenv
load_dotenv()

_bidding_folder = os.getenv('BIDDING_FOLDER', '')
if not _bidding_folder:
    raise RuntimeError("BIDDING_FOLDER environment variable not set. Copy .env.example to .env and configure.")
BIDDING_FOLDER = Path(_bidding_folder)


def run_auto_link(confidence_threshold: float = 0.65, dry_run: bool = False):
    """
    Auto-link PlanHub projects to local folders.

    Args:
        confidence_threshold: Minimum confidence score to auto-link (default: 0.65)
        dry_run: If True, show what would be linked without saving
    """
    print("=" * 60)
    print("PLANHUB AUTO-LINKER")
    print("=" * 60)

    # Load PlanHub projects
    print("\nLoading PlanHub projects...")
    planhub_projects = load_planhub_projects()
    print(f"  Found {len(planhub_projects)} PlanHub projects")

    # Load local bidding projects
    print("\nLoading local bidding projects...")
    reader = BiddingFolderReader(str(BIDDING_FOLDER))
    local_projects = reader.read_all_projects()
    print(f"  Found {len(local_projects)} local projects")

    # Initialize matcher
    matcher = PlanHubLocalMatcher()

    # Get current stats
    print("\nCurrent linking status:")
    stats = matcher.get_match_stats(planhub_projects, local_projects)
    print(f"  Total matches: {stats['total_matches']}")
    print(f"  Manual links: {stats['manual_matches']}")
    print(f"  Auto matches: {stats['auto_matches']}")
    print(f"  Unmatched: {stats['unmatched_planhub']}")

    # Find all potential matches
    print("\n" + "-" * 60)
    print("ANALYZING MATCHES")
    print("-" * 60)

    new_links = []
    unmatched = []

    for ph_proj in planhub_projects:
        planhub_id = ph_proj.get('project_id') or ph_proj.get('id', '').replace('planhub-', '')
        ph_name = ph_proj.get('project_name') or ph_proj.get('title', '')
        ph_city = ph_proj.get('city', '')
        ph_state = ph_proj.get('state', '')

        # Skip if already manually linked
        if matcher.get_link(planhub_id):
            print(f"\n[SKIP] {ph_name} - Already linked")
            continue

        # Get best match
        match = matcher.get_best_match(ph_proj, local_projects)

        if match and match['confidence'] >= confidence_threshold:
            local_proj = None
            for lp in local_projects:
                if lp.get('id') == match['local_id']:
                    local_proj = lp
                    break

            local_name = local_proj.get('title', '') if local_proj else match['local_id']

            print(f"\n[MATCH] {ph_name}")
            print(f"  -> {local_name}")
            print(f"  Confidence: {match['confidence']:.2f}")
            print(f"  Name sim: {match['match_details'].get('name_similarity', 0):.2f}")
            print(f"  Location match: {match['match_details'].get('location_match', False)}")
            print(f"  Bid date match: {match['match_details'].get('bid_date_match', False)}")

            new_links.append({
                'planhub_id': planhub_id,
                'planhub_name': ph_name,
                'local_id': match['local_id'],
                'local_name': local_name,
                'confidence': match['confidence'],
                'details': match['match_details']
            })
        else:
            # Show top suggestions for unmatched
            suggestions = matcher.get_match_suggestions(ph_proj, local_projects, limit=2)

            print(f"\n[NO MATCH] {ph_name} ({ph_city}, {ph_state})")
            if suggestions:
                print(f"  Top suggestions:")
                for sug in suggestions:
                    print(f"    - {sug['local_title']} (conf: {sug['confidence']:.2f})")
            else:
                print(f"  No similar projects found")

            unmatched.append({
                'planhub_id': planhub_id,
                'planhub_name': ph_name,
                'city': ph_city,
                'state': ph_state,
                'suggestions': suggestions
            })

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"New links to create: {len(new_links)}")
    print(f"Unmatched projects: {len(unmatched)}")

    if new_links:
        print("\nLinks to create:")
        for link in new_links:
            print(f"  {link['planhub_name'][:40]:40} -> {link['local_name'][:40]}")

    # Create links (if not dry run)
    if new_links and not dry_run:
        print("\n" + "-" * 60)
        print("CREATING LINKS...")
        print("-" * 60)

        created = 0
        for link in new_links:
            success = matcher.link_projects(link['planhub_id'], link['local_id'])
            if success:
                print(f"  Linked: {link['planhub_id']} -> {link['local_id']}")
                created += 1
            else:
                print(f"  FAILED: {link['planhub_id']}")

        print(f"\nCreated {created}/{len(new_links)} links")

        # Save summary to file
        summary = {
            'total_planhub': len(planhub_projects),
            'total_local': len(local_projects),
            'new_links_created': created,
            'unmatched_count': len(unmatched),
            'links': new_links,
            'unmatched': unmatched
        }

        summary_file = Path(__file__).parent / 'planhub_link_summary.json'
        with open(summary_file, 'w') as f:
            json.dump(summary, f, indent=2)
        print(f"\nSummary saved to: {summary_file}")

    elif dry_run:
        print("\n[DRY RUN] No links created")

    return {
        'new_links': new_links,
        'unmatched': unmatched
    }


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Auto-link PlanHub projects to local folders')
    parser.add_argument('--threshold', '-t', type=float, default=0.65,
                       help='Confidence threshold for auto-linking (default: 0.65)')
    parser.add_argument('--dry-run', '-d', action='store_true',
                       help='Show matches without creating links')
    args = parser.parse_args()

    run_auto_link(
        confidence_threshold=args.threshold,
        dry_run=args.dry_run
    )
