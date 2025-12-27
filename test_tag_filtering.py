"""
Test Tag Filtering and Extraction

Tests:
- Tag extraction from database
- Tag-based classification (project_type, sector)
- Filter logic for various criteria
"""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from modules.planhub.planhub_db_reader import PlanHubDatabaseReader


def test_tag_extraction():
    """Test that tags are extracted from database projects"""
    print("=" * 60)
    print("TEST 1: Tag Extraction from Database")
    print("=" * 60)

    reader = PlanHubDatabaseReader()
    projects = reader.get_all_leads(status_filter=['queued'])[:10]

    tags_found = 0
    for proj in projects:
        tags = proj.get('tags', [])
        if tags:
            tags_found += 1
            print(f"\n{proj['project_name']}")
            print(f"  Tags: {tags}")
            print(f"  Sub Bidding: {proj.get('is_sub_bidding')}")
            print(f"  GC Awarded: {proj.get('is_gc_awarded')}")
            print(f"  Type: {proj.get('project_type')}")
            print(f"  Sector: {proj.get('sector')}")

    assert tags_found > 0, "No tags found in any projects"
    print(f"\n✓ Found tags in {tags_found}/{len(projects)} projects")
    print()


def test_project_type_classification():
    """Test project type classification from tags"""
    print("=" * 60)
    print("TEST 2: Project Type Classification")
    print("=" * 60)

    reader = PlanHubDatabaseReader()

    # Test classification logic directly
    test_cases = [
        (["Sub Bidding", "Commercial", "Renovation"], "Renovation"),
        (["Sub Bidding", "Commercial", "New Construction"], "New Construction"),
        (["Sub Bidding", "Commercial"], "Unknown"),
        (["Tenant Build-Out", "Commercial"], "Tenant Build-Out"),
        ([], "Unknown")
    ]

    for tags, expected_type in test_cases:
        result = reader._extract_project_type(tags)
        print(f"\nTags: {tags}")
        print(f"Expected: {expected_type}, Got: {result}")
        assert result == expected_type, f"Expected {expected_type}, got {result}"

    print("\n✓ Project type classification works correctly")
    print()


def test_sector_classification():
    """Test sector classification from tags"""
    print("=" * 60)
    print("TEST 3: Sector Classification")
    print("=" * 60)

    reader = PlanHubDatabaseReader()

    test_cases = [
        (["Sub Bidding", "Commercial"], "Commercial"),
        (["Sub Bidding", "Retail"], "Retail"),
        (["Industrial", "Commercial"], "Industrial"),
        (["Education", "Public"], "Education"),
        ([], "Unknown")
    ]

    for tags, expected_sector in test_cases:
        result = reader._extract_sector(tags)
        print(f"\nTags: {tags}")
        print(f"Expected: {expected_sector}, Got: {result}")
        assert result == expected_sector, f"Expected {expected_sector}, got {result}"

    print("\n✓ Sector classification works correctly")
    print()


def test_filter_logic():
    """Test filtering logic on real database projects"""
    print("=" * 60)
    print("TEST 4: Filter Logic on Real Data")
    print("=" * 60)

    reader = PlanHubDatabaseReader()
    all_projects = reader.get_all_leads()

    print(f"\nTotal projects: {len(all_projects)}")

    # Test 1: Sub Bidding filter
    sub_bidding = [p for p in all_projects if p.get('is_sub_bidding')]
    print(f"\nSub Bidding projects: {len(sub_bidding)}")
    assert len(sub_bidding) > 0, "Should find Sub Bidding projects"

    # Test 2: GC Awarded filter
    gc_awarded = [p for p in all_projects if p.get('is_gc_awarded')]
    print(f"GC Awarded projects: {len(gc_awarded)}")

    # Test 3: Project type filter
    renovations = [p for p in all_projects if p.get('project_type') == 'Renovation']
    print(f"Renovation projects: {len(renovations)}")
    assert len(renovations) > 0, "Should find Renovation projects"

    # Test 4: Sector filter
    retail = [p for p in all_projects if p.get('sector') == 'Retail']
    print(f"Retail projects: {len(retail)}")
    assert len(retail) > 0, "Should find Retail projects"

    # Test 5: Combined filters (Sub Bidding + Retail + exclude GC Awarded)
    filtered = [
        p for p in all_projects
        if p.get('is_sub_bidding')
        and p.get('sector') == 'Retail'
        and not p.get('is_gc_awarded')
    ]
    print(f"\nFiltered (Sub Bidding + Retail - GC Awarded): {len(filtered)}")

    # Show sample
    if filtered:
        sample = filtered[0]
        print(f"\nSample filtered project:")
        print(f"  Name: {sample['project_name']}")
        print(f"  Location: {sample.get('city')}, {sample.get('state')}")
        print(f"  Tags: {sample.get('tags')}")
        print(f"  Type: {sample.get('project_type')}")

    print("\n✓ Filter logic works correctly")
    print()


def test_tag_statistics():
    """Generate statistics on tags across all projects"""
    print("=" * 60)
    print("TEST 5: Tag Statistics")
    print("=" * 60)

    reader = PlanHubDatabaseReader()
    all_projects = reader.get_all_leads()

    from collections import Counter

    # Count all tags
    all_tags = []
    for proj in all_projects:
        all_tags.extend(proj.get('tags', []))

    tag_counts = Counter(all_tags)

    print(f"\nTotal projects: {len(all_projects)}")
    print(f"Total tag instances: {len(all_tags)}")
    print(f"Unique tags: {len(tag_counts)}")

    print("\nMost common tags:")
    for tag, count in tag_counts.most_common(10):
        percentage = (count / len(all_projects)) * 100
        print(f"  {tag}: {count} ({percentage:.1f}%)")

    # Project type distribution
    project_types = Counter(p.get('project_type') for p in all_projects)
    print("\nProject type distribution:")
    for ptype, count in project_types.most_common():
        percentage = (count / len(all_projects)) * 100
        print(f"  {ptype}: {count} ({percentage:.1f}%)")

    # Sector distribution
    sectors = Counter(p.get('sector') for p in all_projects)
    print("\nSector distribution:")
    for sector, count in sectors.most_common():
        percentage = (count / len(all_projects)) * 100
        print(f"  {sector}: {count} ({percentage:.1f}%)")

    print("\n✓ Tag statistics generated successfully")
    print()


if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("Testing Tag Extraction and Filtering")
    print("=" * 60 + "\n")

    try:
        test_tag_extraction()
        test_project_type_classification()
        test_sector_classification()
        test_filter_logic()
        test_tag_statistics()

        print("=" * 60)
        print("ALL TESTS PASSED ✓")
        print("=" * 60)

    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
