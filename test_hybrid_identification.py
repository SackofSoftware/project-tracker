#!/usr/bin/env python3
"""
Test script demonstrating the hybrid sheet identification approach.

This shows how the system now verifies NCS-based sheet numbering against actual content.
"""

from modules.doc_classification.drawing_discipline_identifier import (
    detect_sheet_type_from_content,
    identify_sheet_hybrid,
    SheetIdentification
)


def test_case(sheet_id: str, text_sample: str, description: str):
    """Run a test case and display results."""
    print(f"\n{'='*80}")
    print(f"TEST: {description}")
    print(f"{'='*80}")
    print(f"Sheet ID: {sheet_id}")
    print(f"Text Sample: {text_sample[:100]}...")

    # Run hybrid identification
    result = identify_sheet_hybrid(sheet_id, text_sample)

    print(f"\nRESULTS:")
    print(f"  Sheet Type (from number): {result.sheet_type}")
    print(f"  Content Prediction: {result.content_prediction}")
    print(f"  Confidence: {result.confidence:.0%}")
    print(f"  Needs Review: {result.needs_review}")

    if result.needs_review:
        print(f"\n  WARNING: Sheet number suggests '{result.sheet_type}' but content suggests '{result.content_prediction}'")
        print(f"           This sheet should be manually reviewed!")


def main():
    print("Hybrid Sheet Identification Test Suite")
    print("Testing content-based verification of NCS sheet numbering")

    # Test Case 1: Agreement - A2.1 actually contains elevations
    test_case(
        sheet_id="A-201",
        text_sample="""
        EXTERIOR ELEVATIONS
        North Elevation
        South Elevation
        East Elevation
        West Elevation
        Scale: 1/4" = 1'-0"
        """,
        description="Agreement: A-201 (Elevations) with elevation content"
    )

    # Test Case 2: Disagreement - A2.1 actually contains floor plans
    test_case(
        sheet_id="A-201",
        text_sample="""
        FIRST FLOOR PLAN
        Level 1 - Main Entry
        Second Floor Plan
        Roof Plan
        Scale: 1/8" = 1'-0"
        """,
        description="Disagreement: A-201 (Elevations) with plan content - NEEDS REVIEW"
    )

    # Test Case 3: Agreement - A1.1 contains floor plans
    test_case(
        sheet_id="A-101",
        text_sample="""
        FLOOR PLANS
        First Floor Plan
        Ground Floor Layout
        Level 2 - Office Space
        Scale: 1/8" = 1'-0"
        """,
        description="Agreement: A-101 (Plans) with plan content"
    )

    # Test Case 4: Section sheet correctly identified
    test_case(
        sheet_id="A-301",
        text_sample="""
        BUILDING SECTIONS
        Longitudinal Section
        Cross Section A-A
        Wall Section Detail
        Section Cut 1/A-301
        """,
        description="Agreement: A-301 (Sections) with section content"
    )

    # Test Case 5: Detail sheet
    test_case(
        sheet_id="A-501",
        text_sample="""
        CONSTRUCTION DETAILS
        Typical Detail - Window Head
        Enlarged Section - Wall Assembly
        Detail 1/A-501
        Construction Detail - Door Frame
        """,
        description="Agreement: A-501 (Details) with detail content"
    )

    # Test Case 6: Schedule sheet
    test_case(
        sheet_id="A-601",
        text_sample="""
        DOOR SCHEDULE
        Window Schedule
        Finish Schedule
        Hardware Schedule
        Room Schedule - Level 1
        """,
        description="Agreement: A-601 (Schedules) with schedule content"
    )

    # Test Case 7: Disagreement - M2.1 with plan content (mechanical plans, not elevations)
    test_case(
        sheet_id="M-201",
        text_sample="""
        MECHANICAL PLANS
        First Floor HVAC Plan
        Second Floor Ductwork Layout
        Roof Plan - Equipment Locations
        """,
        description="Disagreement: M-201 (Elevations) with plan content - NEEDS REVIEW"
    )

    print(f"\n{'='*80}")
    print("Test suite complete!")
    print("\nKEY INSIGHTS:")
    print("- When sheet number and content agree: confidence = 95%")
    print("- When they disagree: confidence = 50%, needs_review = True")
    print("- This helps catch projects that don't follow NCS standards strictly")
    print("='*80}")


if __name__ == "__main__":
    main()
