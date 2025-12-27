#!/usr/bin/env python3
"""
Batch PDF Splitting Runner

Processes all projects in the Bidding folder that need spec/drawing splitting.
Uses LLM-assisted TOC parsing via DeepSeek V3.2 Speciale.

Usage:
    python3 scripts/batch_split_pdfs.py [--dry-run] [--specs-only] [--drawings-only]
"""

import asyncio
import argparse
import logging
import sys
from pathlib import Path
from datetime import datetime
from typing import List, Tuple

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from modules.pipeline.ai_providers import AIProviderManager
from modules.pipeline.stages.stage_split_specs import SplitSpecsStage
from modules.pipeline.stages.stage_split_drawings import SplitDrawingsStage

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)

from dotenv import load_dotenv
load_dotenv()

# Bidding folder path
_bidding = os.getenv("BIDDING_FOLDER", "")
if not _bidding:
    logger.error("BIDDING_FOLDER environment variable not set")
    import sys
    sys.exit(1)
BIDDING_FOLDER = Path(_bidding)


def find_projects_needing_processing() -> List[Tuple[Path, bool, bool]]:
    """
    Find projects that need spec or drawing splitting.

    Returns list of (project_path, needs_specs, needs_drawings)
    """
    projects = []

    for project_dir in sorted(BIDDING_FOLDER.iterdir()):
        if not project_dir.is_dir():
            continue
        if project_dir.name.startswith('.'):
            continue

        needs_specs = False
        needs_drawings = False

        # Check specs
        specs_folder = project_dir / 'Specs'
        if specs_folder.exists():
            # Has source PDF?
            spec_pdfs = list(specs_folder.glob("*.pdf"))
            has_spec_pdf = any(
                p.stat().st_size > 500_000  # > 500KB
                for p in spec_pdfs
                if not p.name.startswith('0')  # Not already split
            )
            # Has split output?
            has_split = (
                (specs_folder / 'Division-08-Openings').exists() or
                (specs_folder / 'Division-01-General').exists()
            )
            needs_specs = has_spec_pdf and not has_split

        # Check drawings
        drawings_folder = project_dir / 'Drawings'
        if drawings_folder.exists():
            # Has source PDF?
            drawing_pdfs = list(drawings_folder.glob("*.pdf"))
            has_drawing_pdf = any(
                p.stat().st_size > 500_000  # > 500KB
                for p in drawing_pdfs
            )
            # Has split output (discipline subfolders)?
            subdirs = [d for d in drawings_folder.iterdir() if d.is_dir() and not d.name.startswith('.')]
            has_split = len(subdirs) > 0
            needs_drawings = has_drawing_pdf and not has_split

        if needs_specs or needs_drawings:
            projects.append((project_dir, needs_specs, needs_drawings))

    return projects


async def process_project(
    project_path: Path,
    ai: AIProviderManager,
    do_specs: bool,
    do_drawings: bool,
    dry_run: bool = False
) -> dict:
    """Process a single project"""
    result = {
        'project': project_path.name,
        'specs_sections': 0,
        'drawings_sheets': 0,
        'errors': []
    }

    if dry_run:
        logger.info(f"[DRY-RUN] Would process: {project_path.name}")
        return result

    # Process specs
    if do_specs:
        try:
            logger.info(f"[SPECS] Processing: {project_path.name}")
            stage = SplitSpecsStage(project_path, ai)
            stage_result = await stage.run()

            if stage_result.success:
                result['specs_sections'] = stage_result.data.get('total_sections', 0)
                logger.info(f"[SPECS] Extracted {result['specs_sections']} sections")
            else:
                result['errors'].append(f"Specs: {stage_result.error}")
                logger.error(f"[SPECS] Failed: {stage_result.error}")
        except Exception as e:
            result['errors'].append(f"Specs: {str(e)}")
            logger.error(f"[SPECS] Error: {e}")

    # Process drawings
    if do_drawings:
        try:
            logger.info(f"[DRAWINGS] Processing: {project_path.name}")
            stage = SplitDrawingsStage(project_path, ai)
            stage_result = await stage.run()

            if stage_result.success:
                result['drawings_sheets'] = stage_result.data.get('sheets_extracted', 0)
                logger.info(f"[DRAWINGS] Extracted {result['drawings_sheets']} sheets")
            else:
                result['errors'].append(f"Drawings: {stage_result.error}")
                logger.error(f"[DRAWINGS] Failed: {stage_result.error}")
        except Exception as e:
            result['errors'].append(f"Drawings: {str(e)}")
            logger.error(f"[DRAWINGS] Error: {e}")

    return result


async def main():
    parser = argparse.ArgumentParser(description='Batch PDF splitting for construction projects')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be processed without doing it')
    parser.add_argument('--specs-only', action='store_true', help='Only process spec books')
    parser.add_argument('--drawings-only', action='store_true', help='Only process drawing sets')
    parser.add_argument('--project', type=str, help='Process only this project (partial name match)')
    args = parser.parse_args()

    # Find projects
    projects = find_projects_needing_processing()

    # Filter by type
    if args.specs_only:
        projects = [(p, True, False) for p, s, d in projects if s]
    elif args.drawings_only:
        projects = [(p, False, True) for p, s, d in projects if d]

    # Filter by name
    if args.project:
        projects = [(p, s, d) for p, s, d in projects if args.project.lower() in p.name.lower()]

    if not projects:
        logger.info("No projects need processing!")
        return

    # Show summary
    print("\n" + "=" * 70)
    print("BATCH PDF SPLITTING")
    print("=" * 70)
    print(f"Projects to process: {len(projects)}")
    print(f"Mode: {'DRY RUN' if args.dry_run else 'LIVE'}")
    print("-" * 70)

    for project_path, needs_specs, needs_drawings in projects:
        tasks = []
        if needs_specs:
            tasks.append("SPECS")
        if needs_drawings:
            tasks.append("DRAWINGS")
        print(f"  {project_path.name}: {', '.join(tasks)}")

    print("-" * 70)

    if not args.dry_run:
        # Initialize AI provider
        ai = AIProviderManager()
        logger.info(f"AI Provider ready (DeepSeek V3.2 Speciale)")
    else:
        ai = None

    # Process each project
    start_time = datetime.now()
    results = []

    for i, (project_path, needs_specs, needs_drawings) in enumerate(projects, 1):
        print(f"\n[{i}/{len(projects)}] {project_path.name}")
        print("-" * 50)

        result = await process_project(
            project_path,
            ai,
            needs_specs,
            needs_drawings,
            args.dry_run
        )
        results.append(result)

    # Summary
    elapsed = (datetime.now() - start_time).total_seconds()
    total_specs = sum(r['specs_sections'] for r in results)
    total_drawings = sum(r['drawings_sheets'] for r in results)
    total_errors = sum(len(r['errors']) for r in results)

    print("\n" + "=" * 70)
    print("BATCH COMPLETE")
    print("=" * 70)
    print(f"Projects processed: {len(results)}")
    print(f"Spec sections extracted: {total_specs}")
    print(f"Drawing sheets extracted: {total_drawings}")
    print(f"Errors: {total_errors}")
    print(f"Time elapsed: {elapsed:.1f}s")

    if ai:
        print(f"\nAI Usage:")
        print(f"  DeepSeek calls: {ai.usage_stats.get('deepseek_calls', 0)}")
        print(f"  DeepSeek tokens: {ai.usage_stats.get('deepseek_tokens', 0):,}")
        estimated_cost = ai.usage_stats.get('deepseek_tokens', 0) * 0.0000002  # rough estimate
        print(f"  Estimated cost: ${estimated_cost:.4f}")

    if total_errors > 0:
        print("\nErrors:")
        for r in results:
            if r['errors']:
                print(f"  {r['project']}:")
                for err in r['errors']:
                    print(f"    - {err}")


if __name__ == '__main__':
    asyncio.run(main())
