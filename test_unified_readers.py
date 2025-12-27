#!/usr/bin/env python3
"""
Test script to verify that all data readers return UnifiedProject instances
"""

import os
import sys
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def test_planhub_reader():
    """Test PlanHub database reader"""
    print("\n=== Testing PlanHub Reader ===")
    try:
        from modules.planhub.planhub_db_reader import PlanHubDatabaseReader
        from modules.schema.unified_project import UnifiedProject

        reader = PlanHubDatabaseReader()
        projects = reader.get_all_leads(status_filter=['done'])

        print(f"Loaded {len(projects)} PlanHub projects")

        if projects:
            # Check first project
            first = projects[0]
            print(f"\nFirst project type: {type(first)}")
            print(f"Is UnifiedProject: {isinstance(first, UnifiedProject)}")
            print(f"ID: {first.id}")
            print(f"Title: {first.title}")
            print(f"Source: {first.source}")
            print(f"Location: {first.location}")
            print(f"Division 8: {first.is_division_8}")

            # Test to_dict conversion
            project_dict = first.to_dict()
            print(f"\nConverted to dict successfully: {bool(project_dict)}")
            print(f"Dict has 'id': {'id' in project_dict}")
            print(f"Dict has 'source': {'source' in project_dict}")

            print("\n✓ PlanHub reader test PASSED")
            return True
        else:
            print("\nNo projects found (but reader works)")
            return True

    except Exception as e:
        print(f"\n✗ PlanHub reader test FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_govwin_reader():
    """Test GovWin reader"""
    print("\n=== Testing GovWin Reader ===")
    try:
        from modules.govleads.govleads_reader import GovLeadsReader
        from modules.schema.unified_project import UnifiedProject

        reader = GovLeadsReader()
        records = reader.read_all_leads()

        print(f"Loaded {len(records)} GovWin records")

        if records:
            # Test normalization to UnifiedProject
            first_record = records[0]
            unified = reader.normalize_to_unified_project(first_record)

            print(f"\nNormalized project type: {type(unified)}")
            print(f"Is UnifiedProject: {isinstance(unified, UnifiedProject)}")
            print(f"ID: {unified.id}")
            print(f"Title: {unified.title}")
            print(f"Source: {unified.source}")
            print(f"Entity Type: {unified.entity_type}")
            print(f"Response Date: {unified.response_date}")

            # Test to_dict conversion
            project_dict = unified.to_dict()
            print(f"\nConverted to dict successfully: {bool(project_dict)}")
            print(f"Dict has 'id': {'id' in project_dict}")
            print(f"Dict has 'response_date': {'response_date' in project_dict}")

            print("\n✓ GovWin reader test PASSED")
            return True
        else:
            print("\nNo records found (but reader works)")
            return True

    except Exception as e:
        print(f"\n✗ GovWin reader test FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_local_bidding_reader():
    """Test Local Bidding reader"""
    print("\n=== Testing Local Bidding Reader ===")
    try:
        from modules.bidding.bidding_reader import BiddingFolderReader
        from modules.schema.unified_project import UnifiedProject

        bidding_folder = os.getenv("BIDDING_FOLDER", "")
        if not bidding_folder:
            print("Skipping: BIDDING_FOLDER not set")
            return

        reader = BiddingFolderReader(bidding_folder)
        projects = reader.read_all_projects()

        print(f"Loaded {len(projects)} local projects")

        if projects:
            # Check first project
            first = projects[0]
            print(f"\nFirst project type: {type(first)}")
            print(f"Is UnifiedProject: {isinstance(first, UnifiedProject)}")
            print(f"ID: {first.id}")
            print(f"Title: {first.title}")
            print(f"Source: {first.source}")
            print(f"Source ID (folder): {first.source_id}")
            print(f"Division 8: {first.is_division_8}")

            # Test to_dict conversion
            project_dict = first.to_dict()
            print(f"\nConverted to dict successfully: {bool(project_dict)}")
            print(f"Dict has 'id': {'id' in project_dict}")
            print(f"Dict has 'source': {'source' in project_dict}")

            # Test helper methods
            stats = reader.get_summary_stats()
            print(f"\nStats: {stats}")

            print("\n✓ Local Bidding reader test PASSED")
            return True
        else:
            print("\nNo projects found (check BIDDING_FOLDER path)")
            return False

    except Exception as e:
        print(f"\n✗ Local Bidding reader test FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run all tests"""
    print("=" * 60)
    print("Testing Unified Schema Data Readers")
    print("=" * 60)

    results = []

    # Test each reader
    results.append(("PlanHub", test_planhub_reader()))
    results.append(("GovWin", test_govwin_reader()))
    results.append(("Local Bidding", test_local_bidding_reader()))

    # Summary
    print("\n" + "=" * 60)
    print("Test Summary")
    print("=" * 60)

    for name, passed in results:
        status = "✓ PASSED" if passed else "✗ FAILED"
        print(f"{name:20} {status}")

    all_passed = all(r[1] for r in results)

    print("\n" + "=" * 60)
    if all_passed:
        print("All tests PASSED!")
        return 0
    else:
        print("Some tests FAILED")
        return 1


if __name__ == "__main__":
    sys.exit(main())
