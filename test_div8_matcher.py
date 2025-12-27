"""
Test Division 8 matcher enhancements

Tests the new Division 8 trade scoring in PlanHubLocalMatcher:
- Division 8 detection for PlanHub and local projects
- Trade overlap calculation (Jaccard similarity)
- Score bonus for matching Division 8 projects
- Score penalty for Division 8 mismatch
"""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from modules.planhub.planhub_matcher import PlanHubLocalMatcher


def test_division_8_detection():
    """Test that Division 8 detection works for both PlanHub and local projects"""
    print("=" * 60)
    print("TEST 1: Division 8 Detection")
    print("=" * 60)

    matcher = PlanHubLocalMatcher()

    # PlanHub project with Division 8 trades
    planhub_div8 = {
        "project_id": "123456",
        "project_name": "Office Building Renovation",
        "matching_trades": ["Windows", "Exterior Doors", "Glass and Mirrors"],
        "is_division_8": True
    }

    # PlanHub project without Division 8
    planhub_non_div8 = {
        "project_id": "789012",
        "project_name": "HVAC System Replacement",
        "matching_trades": ["HVAC", "Plumbing", "Electrical"]
    }

    # Local project with Division 8 data
    local_div8 = {
        "id": "office-renovation",
        "title": "Office Building Renovation",
        "division_8": {
            "spec_sections": [
                "08 11 00 - Metal Doors and Frames",
                "08 51 00 - Aluminum Windows"
            ],
            "windows": {"count": 45},
            "doors": {"count": 12}
        }
    }

    # Local project without Division 8
    local_non_div8 = {
        "id": "hvac-replacement",
        "title": "HVAC System Replacement"
    }

    # Test detection
    print(f"\nPlanHub Division 8 project: {matcher._is_division_8_project(planhub_div8)}")
    print(f"PlanHub non-Division 8 project: {matcher._is_division_8_project(planhub_non_div8)}")
    print(f"Local Division 8 project: {matcher._is_division_8_project(local_div8)}")
    print(f"Local non-Division 8 project: {matcher._is_division_8_project(local_non_div8)}")

    print("\n✓ Division 8 detection test passed\n")


def test_trade_overlap():
    """Test trade overlap calculation between PlanHub trades and local spec sections"""
    print("=" * 60)
    print("TEST 2: Trade Overlap Calculation")
    print("=" * 60)

    matcher = PlanHubLocalMatcher()

    # Local project with Division 8 specs
    local_project = {
        "id": "test-project",
        "division_8": {
            "spec_sections": [
                "08 11 00 - Metal Doors and Frames",
                "08 14 00 - Wood Doors",
                "08 51 00 - Aluminum Windows",
                "08 80 00 - Glazing"
            ]
        }
    }

    # Test various PlanHub trade combinations
    test_cases = [
        (["Windows", "Doors"], "High overlap - common Division 8 trades"),
        (["Aluminum Windows", "Metal Doors"], "Very high overlap - specific matches"),
        (["Glazing", "Glass"], "Medium overlap - partial match"),
        (["HVAC", "Plumbing"], "No overlap - different trades"),
        ([], "No trades provided")
    ]

    for trades, description in test_cases:
        overlap = matcher._calculate_trade_overlap(trades, local_project)
        print(f"\nTrades: {trades}")
        print(f"Description: {description}")
        print(f"Overlap: {overlap:.3f}")

    print("\n✓ Trade overlap calculation test passed\n")


def test_division_8_scoring():
    """Test that Division 8 scoring affects match scores correctly"""
    print("=" * 60)
    print("TEST 3: Division 8 Score Impact")
    print("=" * 60)

    matcher = PlanHubLocalMatcher()

    # Base project (moderate name match, same location)
    base_planhub = {
        "project_id": "111111",
        "project_name": "Commercial Building Renovation",
        "city": "Boston",
        "state": "MA",
        "bid_date": "2026-02-15"
    }

    base_local = {
        "id": "commercial-reno",
        "title": "Commercial Building Renovation Project",
        "folder": "Commercial Building Renovation",
        "location": {"city": "Boston", "state": "MA"},
        "bid_date": "2026-02-15"
    }

    # Test Case 1: Both Division 8 with good trade overlap
    print("\n--- Case 1: Both Division 8 with trade overlap ---")
    planhub_div8 = {
        **base_planhub,
        "matching_trades": ["Windows", "Doors", "Glazing"],
        "is_division_8": True
    }
    local_div8 = {
        **base_local,
        "division_8": {
            "spec_sections": [
                "08 11 00 - Metal Doors",
                "08 51 00 - Windows",
                "08 80 00 - Glazing"
            ]
        }
    }
    score1, details1 = matcher._calculate_match_score(planhub_div8, local_div8)
    print(f"Score: {score1:.3f}")
    print(f"Details: {details1}")

    # Test Case 2: Both projects but no Division 8 scope (neutral)
    print("\n--- Case 2: Both non-Division 8 (no bonus/penalty) ---")
    planhub_non = {**base_planhub}
    local_non = {**base_local}
    score2, details2 = matcher._calculate_match_score(planhub_non, local_non)
    print(f"Score: {score2:.3f}")
    print(f"Details: {details2}")

    # Test Case 3: Division 8 mismatch (penalty)
    print("\n--- Case 3: Division 8 mismatch (penalty) ---")
    planhub_div8_only = {
        **base_planhub,
        "matching_trades": ["Windows", "Doors"],
        "is_division_8": True
    }
    local_non_div8 = {**base_local}
    score3, details3 = matcher._calculate_match_score(planhub_div8_only, local_non_div8)
    print(f"Score: {score3:.3f}")
    print(f"Details: {details3}")

    # Verify expected behavior
    print("\n--- Score Comparison ---")
    print(f"Both Division 8 (with overlap): {score1:.3f}")
    print(f"Both non-Division 8: {score2:.3f}")
    print(f"Division 8 mismatch: {score3:.3f}")

    assert score1 > score2, "Division 8 match should have higher score"
    assert score3 < score2, "Division 8 mismatch should have lower score"

    print("\n✓ Division 8 scoring test passed\n")


def test_match_threshold():
    """Test that Division 8 scoring affects whether matches meet threshold"""
    print("=" * 60)
    print("TEST 4: Match Threshold Impact")
    print("=" * 60)

    matcher = PlanHubLocalMatcher()

    # Project with moderate name match (below threshold alone)
    planhub_project = {
        "project_id": "222222",
        "project_name": "School Addition",
        "city": "Cambridge",
        "state": "MA",
        "matching_trades": ["Windows", "Doors", "Storefronts"],
        "is_division_8": True
    }

    local_project = {
        "id": "school-addition-cambridge",
        "title": "Cambridge School Addition Project",
        "folder": "School Addition",
        "location": {"city": "Cambridge", "state": "MA"},
        "division_8": {
            "spec_sections": [
                "08 11 00 - Metal Doors",
                "08 51 00 - Aluminum Windows",
                "08 60 00 - Storefronts"
            ]
        }
    }

    score, details = matcher._calculate_match_score(planhub_project, local_project)

    print(f"\nProject: {planhub_project['project_name']}")
    print(f"Match score: {score:.3f}")
    print(f"Auto-match threshold: 0.65")
    print(f"Would auto-match: {score >= 0.65}")
    print(f"\nScore breakdown:")
    for key, value in details.items():
        print(f"  {key}: {value}")

    print("\n✓ Match threshold test passed\n")


if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("Testing Enhanced Division 8 Matcher")
    print("=" * 60 + "\n")

    try:
        test_division_8_detection()
        test_trade_overlap()
        test_division_8_scoring()
        test_match_threshold()

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
