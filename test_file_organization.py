#!/usr/bin/env python3
"""
Test script for file organization feature in scope takeoff pipeline.

This script demonstrates the file organization functionality:
1. Organizes documents into Specs/, Drawings/, Schedules/, Addenda/ folders
2. Splits multi-page drawing PDFs into individual sheets
3. Tracks organized files in the database
4. Updates the takeoff result with organized file paths

Usage:
    python3 test_file_organization.py <project_folder>

Example:
    python3 test_file_organization.py "Bidding/Project-Name"
"""

import sys
import json
from pathlib import Path
from modules.scope_takeoff.file_organizer import FileOrganizer, organize_project_files
from modules.database import get_organized_files


def test_file_organizer(project_folder):
    """Test the file organizer module directly"""
    print(f"\n{'='*60}")
    print(f"Testing File Organizer")
    print(f"Project: {project_folder}")
    print(f"{'='*60}\n")

    project_path = Path(project_folder)
    if not project_path.exists():
        print(f"Error: Project folder not found: {project_folder}")
        return

    # Create organizer
    organizer = FileOrganizer(project_path)
    print(f"Created organizer with root: {organizer.organized_root}")

    # Scan for PDF files
    pdf_files = list(project_path.rglob('*.pdf'))
    print(f"\nFound {len(pdf_files)} PDF files:")
    for pdf in pdf_files[:5]:  # Show first 5
        print(f"  - {pdf.name}")
    if len(pdf_files) > 5:
        print(f"  ... and {len(pdf_files) - 5} more")

    # Simulate document identification
    # In real usage, this comes from phase_identify()
    documents = []
    for pdf_path in pdf_files:
        # Simple heuristic classification for demo
        name_lower = pdf_path.name.lower()
        if 'spec' in name_lower:
            doc_type = 'spec'
        elif 'plan' in name_lower or 'drawing' in name_lower or 'sheet' in name_lower:
            doc_type = 'drawing'
        elif 'addend' in name_lower:
            doc_type = 'addendum'
        elif 'schedule' in name_lower:
            doc_type = 'schedule'
        else:
            doc_type = 'unknown'

        documents.append({
            'path': str(pdf_path),
            'filename': pdf_path.name,
            'doc_type': doc_type,
            'page_count': 0,
            'avg_dpi': 0.0,
            'has_text_layer': True,
            'detected_sheets': []
        })

    print(f"\nDocument types detected:")
    type_counts = {}
    for doc in documents:
        doc_type = doc['doc_type']
        type_counts[doc_type] = type_counts.get(doc_type, 0) + 1
    for doc_type, count in sorted(type_counts.items()):
        print(f"  {doc_type}: {count}")

    # Organize files
    print(f"\n{'='*60}")
    print("Organizing files...")
    print(f"{'='*60}\n")

    result = organize_project_files(str(project_path), documents)

    # Display results
    stats = result['stats']
    print(f"\nOrganization complete!")
    print(f"  Specs: {stats['specs']}")
    print(f"  Drawings: {stats['drawings']} files")
    print(f"  Drawing sheets extracted: {stats['total_sheets']}")
    print(f"  Schedules: {stats['schedules']}")
    print(f"  Addenda: {stats['addenda']}")

    print(f"\nOrganized root: {result['organized_root']}")

    # Show sample organized files
    organized_files = result['organized_files']
    if organized_files:
        print(f"\nSample organized files (first 10):")
        for file_record in organized_files[:10]:
            print(f"  [{file_record['doc_type']}] {Path(file_record['organized_path']).name}")
            if file_record.get('sheet_number'):
                print(f"      Sheet: {file_record['sheet_number']} - {file_record.get('sheet_title', 'N/A')}")

    # Check database
    project_id = project_path.name
    print(f"\n{'='*60}")
    print(f"Checking database (project_id: {project_id})")
    print(f"{'='*60}\n")

    try:
        db_files = get_organized_files(project_id)
        print(f"Files tracked in database: {len(db_files)}")

        # Show breakdown by type
        db_type_counts = {}
        for file_record in db_files:
            doc_type = file_record['doc_type']
            db_type_counts[doc_type] = db_type_counts.get(doc_type, 0) + 1

        print("\nDatabase records by type:")
        for doc_type, count in sorted(db_type_counts.items()):
            print(f"  {doc_type}: {count}")

    except Exception as e:
        print(f"Error reading database: {e}")

    # Save result to JSON for inspection
    output_file = project_path / 'Extracted-Data' / 'file_organization_test.json'
    output_file.parent.mkdir(parents=True, exist_ok=True)
    with open(output_file, 'w') as f:
        json.dump(result, f, indent=2)
    print(f"\nFull result saved to: {output_file}")


def test_full_pipeline(project_folder):
    """Test file organization through the full takeoff pipeline"""
    print(f"\n{'='*60}")
    print(f"Testing Full Takeoff Pipeline with File Organization")
    print(f"Project: {project_folder}")
    print(f"{'='*60}\n")

    from modules.scope_takeoff import run_scope_takeoff

    def progress_callback(data):
        phase = data.get('phase_name', data.get('phase', ''))
        msg = data.get('message', '')
        pct = data.get('progress', 0) * 100
        print(f"[{phase}] {msg} ({pct:.0f}%)")

    result = run_scope_takeoff(project_folder, progress_callback)

    print(f"\n{'='*60}")
    print("Pipeline Results")
    print(f"{'='*60}\n")

    print(f"Success: {result['success']}")
    print(f"Errors: {len(result.get('errors', []))}")
    if result.get('errors'):
        for error in result['errors']:
            print(f"  - {error}")

    # File organization stats
    org_stats = result.get('organization_stats', {})
    if org_stats:
        print(f"\nFile Organization:")
        print(f"  Specs: {org_stats.get('specs', 0)}")
        print(f"  Drawings: {org_stats.get('drawings', 0)}")
        print(f"  Drawing sheets: {org_stats.get('total_sheets', 0)}")
        print(f"  Schedules: {org_stats.get('schedules', 0)}")
        print(f"  Addenda: {org_stats.get('addenda', 0)}")

    # Other pipeline results
    print(f"\nDivision 8 Sections: {len(result.get('division_8_sections', []))}")
    print(f"Door Schedule Entries: {len(result.get('door_schedule', []))}")
    print(f"Window Schedule Entries: {len(result.get('window_schedule', []))}")
    print(f"Type Counts: {len(result.get('type_counts', []))}")

    organized_files = result.get('organized_files', [])
    if organized_files:
        print(f"\nOrganized Files: {len(organized_files)}")
        print("Sample files:")
        for file_record in organized_files[:5]:
            print(f"  [{file_record['doc_type']}] {Path(file_record['organized_path']).name}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    project_folder = sys.argv[1]

    # Determine test mode
    test_mode = sys.argv[2] if len(sys.argv) > 2 else 'full'

    if test_mode == 'organizer':
        test_file_organizer(project_folder)
    else:
        test_full_pipeline(project_folder)
