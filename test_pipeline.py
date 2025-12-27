#!/usr/bin/env python3
"""
Test Pipeline Runner - Runs the full analysis pipeline on one project with verbose output.
"""

import asyncio
import sys
import os
import logging
from pathlib import Path
from datetime import datetime

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

# Configure logging - suppress noisy libraries
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)-8s | %(name)-30s | %(message)s',
    datefmt='%H:%M:%S'
)

# Suppress extremely verbose PDF parsing logs
for noisy_module in ['pdfminer', 'pdfplumber', 'PIL', 'urllib3', 'fitz']:
    logging.getLogger(noisy_module).setLevel(logging.WARNING)

# Make our modules verbose
for module in ['modules.pipeline', 'modules.pipeline.stages', 'modules.pipeline.ai_providers']:
    logging.getLogger(module).setLevel(logging.INFO)

print("=" * 80)
print("MASTER ANALYSIS PIPELINE - TEST RUN")
print("=" * 80)
print()

# Find a test project
_bidding = os.getenv('BIDDING_FOLDER', '')
if not _bidding:
    print("Error: BIDDING_FOLDER environment variable not set")
    import sys
    sys.exit(1)
BIDDING_FOLDER = Path(_bidding)

print(f"Scanning bidding folder: {BIDDING_FOLDER}")
print()

# List available projects
projects = []
for folder in BIDDING_FOLDER.iterdir():
    if folder.is_dir() and not folder.name.startswith('.'):
        pdf_count = len(list(folder.rglob('*.pdf')))
        if pdf_count > 0:
            projects.append((folder, pdf_count))

projects.sort(key=lambda x: x[1], reverse=True)

print(f"Found {len(projects)} projects with PDFs:")
print("-" * 60)
for i, (folder, pdf_count) in enumerate(projects[:20]):
    print(f"  {i+1:2}. {folder.name[:45]:<45} ({pdf_count} PDFs)")
print()

# Let user select or pick a smaller project for testing
# For testing, pick a project with PDFs directly in it (not just subfolders)
# Also prefer projects with 20-100 PDFs for good testing
test_project = None
for folder, pdf_count in projects:
    # Check if project has PDFs directly in root (not just in subfolders)
    root_pdfs = list(folder.glob('*.pdf'))
    if len(root_pdfs) >= 2 and 20 <= pdf_count <= 100:
        test_project = folder
        print(f"Selected project with {len(root_pdfs)} root PDFs and {pdf_count} total")
        break

# Fallback: try any project with root PDFs
if not test_project:
    for folder, pdf_count in projects:
        root_pdfs = list(folder.glob('*.pdf'))
        if len(root_pdfs) >= 2:
            test_project = folder
            print(f"Fallback: project with {len(root_pdfs)} root PDFs")
            break

if not test_project:
    test_project = projects[0][0] if projects else None

if not test_project:
    print("ERROR: No suitable test project found!")
    sys.exit(1)

print(f"Selected test project: {test_project.name}")
print(f"Path: {test_project}")
print()

# List contents of the project
print("Project contents:")
print("-" * 60)
for item in test_project.iterdir():
    if item.is_dir():
        pdf_count = len(list(item.rglob('*.pdf')))
        print(f"  [DIR] {item.name}/ ({pdf_count} PDFs)")
    elif item.suffix.lower() == '.pdf':
        size_mb = item.stat().st_size / (1024 * 1024)
        print(f"  [PDF] {item.name} ({size_mb:.1f} MB)")
print()

# Confirm before running
response = input(f"Run pipeline on '{test_project.name}'? [y/N]: ").strip().lower()
if response != 'y':
    print("Cancelled.")
    sys.exit(0)

print()
print("=" * 80)
print("STARTING PIPELINE")
print("=" * 80)
print()

# Import and run pipeline
from modules.pipeline import MasterPipeline

async def run_test():
    start = datetime.now()

    print(f"[{start.strftime('%H:%M:%S')}] Initializing pipeline...")
    print()

    openai_key = os.getenv('OPENAI_API_KEY')
    if not openai_key:
        print("ERROR: Please set OPENAI_API_KEY in your environment before running.")
        sys.exit(1)

    pipeline = MasterPipeline(
        project_folder=test_project,
        openai_key=openai_key,
        openrouter_key=os.getenv('OPENROUTER_API_KEY')
    )

    print("=" * 80)
    print("PIPELINE STAGES:")
    print("  1. RENAME      - Extract project name from cover sheet using GPT-5 nano vision")
    print("  2. ORGANIZE    - Move files into Specs/, Drawings/, Quotes/ folders")
    print("  3. SPLIT_SPECS - Split spec book into individual CSI section PDFs")
    print("  4. SPLIT_DRAW  - Split drawing set into individual page PDFs")
    print("  5. AI_ANALYSIS - Analyze schedules with DeepSeek + GPT-5 nano")
    print("  6. PARSE       - Parse AI results into structured JSON")
    print("  7. HIGHLIGHT   - Highlight Division 8 scope on floor plans & elevations")
    print("  8. QUOTES      - Identify and extract vendor quote information")
    print("=" * 80)
    print()

    # Run the pipeline
    result = await pipeline.run_full_pipeline(mode='test', stop_on_error=False)

    end = datetime.now()
    duration = (end - start).total_seconds()

    print()
    print("=" * 80)
    print("PIPELINE RESULTS")
    print("=" * 80)
    print()
    print(f"Success: {result['success']}")
    print(f"Duration: {duration:.1f} seconds")
    print()
    print(f"Completed stages ({len(result['completed_stages'])}/8):")
    for stage in result['completed_stages']:
        print(f"  ✓ {stage}")
    print()
    if result['failed_stages']:
        print(f"Failed stages ({len(result['failed_stages'])}):")
        for stage in result['failed_stages']:
            print(f"  ✗ {stage}")
        print()
    if result['errors']:
        print("Errors:")
        for error in result['errors']:
            print(f"  - {error}")
        print()

    # AI usage
    ai_usage = result.get('ai_usage', {})
    if ai_usage:
        print("AI Usage:")
        print(f"  Total tokens: {ai_usage.get('total_tokens', 0):,}")
        print(f"  Estimated cost: ${ai_usage.get('total_estimated_cost', 0):.4f}")
        print()

    print("=" * 80)
    print(f"Pipeline finished at {end.strftime('%H:%M:%S')}")
    print("=" * 80)

    return result

# Run it
if __name__ == "__main__":
    result = asyncio.run(run_test())
    sys.exit(0 if result['success'] else 1)
