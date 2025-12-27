#!/usr/bin/env python3
"""
Example usage of PlanHub-Local Matcher

This script demonstrates how to use the PlanHubLocalMatcher to:
1. Find automatic matches between PlanHub and local projects
2. Manually link projects
3. Get match suggestions
4. View statistics
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from modules.planhub.planhub_reader import load_planhub_projects
from modules.bidding.bidding_reader import BiddingFolderReader
from modules.planhub.planhub_matcher import PlanHubLocalMatcher


def main():
    """Main example function"""
    # Load environment
    load_dotenv()

    print("=" * 70)
    print("PlanHub-Local Project Matcher Example")
    print("=" * 70)

    # Load projects
    print("\n1. Loading projects...")
    planhub_projects = load_planhub_projects()
    print(f"   Loaded {len(planhub_projects)} PlanHub projects")

    bidding_folder = os.getenv('BIDDING_FOLDER', '')
    if not bidding_folder:
        print("Error: BIDDING_FOLDER environment variable not set.")
        import sys
        sys.exit(1)
    reader = BiddingFolderReader(bidding_folder)
    local_projects = reader.read_all_projects()
    print(f"   Loaded {len(local_projects)} local projects")

    # Initialize matcher
    matcher = PlanHubLocalMatcher()

    # Find matches
    print("\n2. Finding matches...")
    matches = matcher.find_matches(planhub_projects, local_projects)
    print(f"   Found {len(matches)} matches")

    if matches:
        print("\n   Matches:")
        for match in matches:
            # Find project names
            ph_proj = next(
                (p for p in planhub_projects
                 if matcher._get_planhub_id(p) == match['planhub_id']),
                None
            )
            local_proj = next(
                (p for p in local_projects if p.get('id') == match['local_id']),
                None
            )

            if ph_proj and local_proj:
                print(f"\n   - PlanHub: {ph_proj.get('project_name')}")
                print(f"     Local:   {local_proj.get('title') or local_proj.get('folder')}")
                print(f"     Confidence: {match['confidence']}")
                print(f"     Type: {match['match_type']}")

    # Show statistics
    print("\n3. Statistics:")
    stats = matcher.get_match_stats(planhub_projects, local_projects)
    print(f"   Total PlanHub projects: {stats['total_planhub']}")
    print(f"   Total local projects: {stats['total_local']}")
    print(f"   Total matches: {stats['total_matches']}")
    print(f"     - Manual: {stats['manual_matches']}")
    print(f"     - Auto: {stats['auto_matches']}")
    print(f"   Unmatched PlanHub: {stats['unmatched_planhub']}")
    print(f"   Match rate: {stats['match_rate']:.1%}")

    # Show match suggestions for first unmatched project
    print("\n4. Match suggestions for unmatched projects:")
    unmatched = matcher.get_unmatched_planhub_projects(
        planhub_projects,
        local_projects
    )

    if unmatched:
        ph_proj = unmatched[0]
        print(f"\n   PlanHub Project: {ph_proj.get('project_name')}")
        print(f"   Location: {ph_proj.get('city')}, {ph_proj.get('state')}")
        print(f"   Bid Date: {ph_proj.get('bid_date')}")

        suggestions = matcher.get_match_suggestions(
            ph_proj,
            local_projects,
            limit=5
        )

        if suggestions:
            print("\n   Top match suggestions:")
            for i, sug in enumerate(suggestions, 1):
                print(f"\n   {i}. {sug['local_title']}")
                print(f"      Folder: {sug['local_folder']}")
                print(f"      Confidence: {sug['confidence']}")
                details = sug['match_details']
                print(f"      Name similarity: {details['name_similarity']:.3f}")
                print(f"      Location match: {details['location_match']}")
                print(f"      Date match: {details['bid_date_match']}")
        else:
            print("\n   No suggestions found (all below 0.3 threshold)")
    else:
        print("\n   All PlanHub projects are matched!")

    # Example of manual linking
    print("\n5. Manual linking example:")
    if unmatched and local_projects:
        ph_proj = unmatched[0]
        local_proj = local_projects[0]

        ph_id = matcher._get_planhub_id(ph_proj)
        local_id = local_proj.get('id')

        print(f"\n   Creating manual link:")
        print(f"   PlanHub: {ph_proj.get('project_name')} ({ph_id})")
        print(f"   Local:   {local_proj.get('title') or local_proj.get('folder')} ({local_id})")

        # Create link
        success = matcher.link_projects(ph_id, local_id)
        print(f"\n   Link created: {success}")

        # Verify
        retrieved = matcher.get_link(ph_id)
        print(f"   Link verified: {retrieved == local_id}")

        # Show in matches
        matches_after = matcher.find_matches(planhub_projects, local_projects)
        manual_count = sum(1 for m in matches_after if m['match_type'] == 'manual')
        print(f"   Total manual matches now: {manual_count}")

        # Clean up - remove the test link
        matcher.unlink_project(ph_id)
        print(f"   Test link removed")

    print("\n" + "=" * 70)
    print("Example complete!")
    print("=" * 70)


if __name__ == "__main__":
    main()
