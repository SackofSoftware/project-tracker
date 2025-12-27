#!/usr/bin/env python3
"""
Batch RAG Analysis - Run Division 8 analysis on all bidding projects
Saves results to division8_rag_analysis.json in each project folder
"""

import os
import sys
import json
import logging
import warnings
from pathlib import Path
from datetime import datetime

from dotenv import load_dotenv

load_dotenv()


def _get_required_env(var_name: str) -> str:
    """Fetch required secrets from the environment to avoid hard-coding keys."""
    value = os.getenv(var_name)
    if not value:
        raise RuntimeError(f"Environment variable {var_name} is required but not set.")
    return value

# Suppress chromadb warnings
warnings.filterwarnings('ignore')
logging.getLogger('chromadb').setLevel(logging.ERROR)

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Set API key from environment (required)
os.environ["OPENAI_API_KEY"] = _get_required_env("OPENAI_API_KEY")

from modules.rag.division8_rag import Division8RAG

_bidding_folder = os.getenv('BIDDING_FOLDER', '')
if not _bidding_folder:
    raise RuntimeError("BIDDING_FOLDER environment variable not set. Copy .env.example to .env and configure.")
BIDDING_FOLDER = Path(_bidding_folder)

# Skip these folders (not actual projects)
SKIP_FOLDERS = {
    '.claude', '.DS_Store', 'AGENTS.md', 'div8_analyzer',
    'BIDS FALL WINTER 2025', 'templates', '__pycache__'
}


def has_documents(folder: Path) -> bool:
    """Check if folder has any PDFs or Word docs to analyze."""
    pdfs = list(folder.glob('**/*.pdf'))
    docx = list(folder.glob('**/*.docx'))
    return len(pdfs) > 0 or len(docx) > 0


def already_analyzed(folder: Path) -> bool:
    """Check if project already has RAG analysis."""
    analysis_file = folder / 'division8_rag_analysis.json'
    if not analysis_file.exists():
        return False

    # Check if analysis is recent (within 7 days)
    try:
        with open(analysis_file, 'r') as f:
            data = json.load(f)
        analyzed_at = data.get('_rag_metadata', {}).get('analyzed_at', '')
        if analyzed_at:
            analyzed_date = datetime.fromisoformat(analyzed_at.replace('Z', '+00:00'))
            age_days = (datetime.now(analyzed_date.tzinfo) - analyzed_date).days
            return age_days < 7
    except:
        pass
    return False


def run_batch_analysis(skip_existing: bool = True, limit: int = None):
    """Run RAG analysis on all projects."""

    # Get all project folders
    all_folders = sorted([
        f for f in BIDDING_FOLDER.iterdir()
        if f.is_dir() and f.name not in SKIP_FOLDERS
    ])

    logger.info(f"Found {len(all_folders)} project folders")

    # Filter to those with documents
    projects_with_docs = [f for f in all_folders if has_documents(f)]
    logger.info(f"Found {len(projects_with_docs)} projects with documents")

    # Filter out already analyzed if requested
    if skip_existing:
        projects_to_analyze = [f for f in projects_with_docs if not already_analyzed(f)]
        logger.info(f"Skipping {len(projects_with_docs) - len(projects_to_analyze)} already analyzed")
    else:
        projects_to_analyze = projects_with_docs

    # Apply limit
    if limit:
        projects_to_analyze = projects_to_analyze[:limit]

    logger.info(f"Will analyze {len(projects_to_analyze)} projects")
    print(f"\n{'='*60}")
    print(f"BATCH RAG ANALYSIS")
    print(f"Projects to analyze: {len(projects_to_analyze)}")
    print(f"{'='*60}\n")

    results_summary = {
        'total_projects': len(projects_to_analyze),
        'successful': 0,
        'failed': 0,
        'projects': []
    }

    for i, folder in enumerate(projects_to_analyze, 1):
        print(f"\n[{i}/{len(projects_to_analyze)}] {folder.name}")
        print("-" * 50)

        try:
            rag = Division8RAG(folder)
            result = rag.analyze_project()

            # Add timestamp
            result['_rag_metadata']['analyzed_at'] = datetime.utcnow().isoformat() + 'Z'

            # Save to project folder
            output_file = folder / 'division8_rag_analysis.json'
            with open(output_file, 'w') as f:
                json.dump(result, f, indent=2)

            # Summary info
            windows_specified = result.get('windows', {}).get('specified', False)
            doors_specified = result.get('doors', {}).get('metal_doors', {}).get('specified', False)

            print(f"  Windows: {'Yes' if windows_specified else 'No'}")
            print(f"  Metal Doors: {'Yes' if doors_specified else 'No'}")
            print(f"  Saved to: {output_file.name}")

            results_summary['successful'] += 1
            results_summary['projects'].append({
                'name': folder.name,
                'status': 'success',
                'windows': windows_specified,
                'doors': doors_specified,
                'chunks': result.get('_rag_metadata', {}).get('chunks_analyzed', 0)
            })

        except Exception as e:
            logger.error(f"Failed to analyze {folder.name}: {e}")
            results_summary['failed'] += 1
            results_summary['projects'].append({
                'name': folder.name,
                'status': 'failed',
                'error': str(e)
            })

    # Save summary
    summary_file = BIDDING_FOLDER / 'rag_analysis_summary.json'
    results_summary['completed_at'] = datetime.utcnow().isoformat() + 'Z'
    with open(summary_file, 'w') as f:
        json.dump(results_summary, f, indent=2)

    print(f"\n{'='*60}")
    print(f"BATCH COMPLETE")
    print(f"Successful: {results_summary['successful']}")
    print(f"Failed: {results_summary['failed']}")
    print(f"Summary saved to: {summary_file}")
    print(f"{'='*60}\n")

    return results_summary


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Batch RAG analysis for Division 8 projects')
    parser.add_argument('--all', action='store_true', help='Re-analyze all projects (skip none)')
    parser.add_argument('--limit', type=int, help='Limit number of projects to analyze')
    args = parser.parse_args()

    run_batch_analysis(skip_existing=not args.all, limit=args.limit)
