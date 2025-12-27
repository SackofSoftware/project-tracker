#!/usr/bin/env python3
"""
Parallel Batch RAG Analysis - Run Division 8 analysis on all bidding projects
Uses ThreadPoolExecutor for concurrent processing
"""

import os
import sys
import json
import logging
import warnings
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

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

# Setup logging with thread info
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - [%(threadName)s] %(message)s'
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

# Thread-safe counter
counter_lock = threading.Lock()
completed_count = 0
success_count = 0
fail_count = 0


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


def analyze_project(folder: Path, total: int) -> dict:
    """Analyze a single project - runs in thread."""
    global completed_count, success_count, fail_count

    try:
        rag = Division8RAG(folder)
        result = rag.analyze_project()

        # Add timestamp
        result['_rag_metadata']['analyzed_at'] = datetime.utcnow().isoformat() + 'Z'

        # Save to project folder
        output_file = folder / 'division8_rag_analysis.json'
        with open(output_file, 'w') as f:
            json.dump(result, f, indent=2)

        windows = result.get('windows', {}).get('specified', False)
        doors = result.get('doors', {}).get('metal_doors', {}).get('specified', False)

        with counter_lock:
            completed_count += 1
            success_count += 1
            current = completed_count

        print(f"[{current}/{total}] {folder.name} - Windows: {'Y' if windows else 'N'}, Doors: {'Y' if doors else 'N'}")

        return {
            'name': folder.name,
            'status': 'success',
            'windows': windows,
            'doors': doors,
            'chunks': result.get('_rag_metadata', {}).get('chunks_analyzed', 0)
        }

    except Exception as e:
        with counter_lock:
            completed_count += 1
            fail_count += 1
            current = completed_count

        print(f"[{current}/{total}] {folder.name} - FAILED: {str(e)[:50]}")

        return {
            'name': folder.name,
            'status': 'failed',
            'error': str(e)
        }


def run_parallel_analysis(workers: int = 4, skip_existing: bool = True, limit: int = None):
    """Run RAG analysis on all projects in parallel."""
    global completed_count, success_count, fail_count

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

    total = len(projects_to_analyze)
    logger.info(f"Will analyze {total} projects with {workers} workers")

    print(f"\n{'='*60}")
    print(f"PARALLEL RAG ANALYSIS")
    print(f"Projects: {total} | Workers: {workers}")
    print(f"{'='*60}\n")

    results = []

    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix='RAG') as executor:
        futures = {
            executor.submit(analyze_project, folder, total): folder
            for folder in projects_to_analyze
        }

        for future in as_completed(futures):
            result = future.result()
            results.append(result)

    # Save summary
    summary = {
        'total_projects': total,
        'successful': success_count,
        'failed': fail_count,
        'workers': workers,
        'completed_at': datetime.utcnow().isoformat() + 'Z',
        'projects': results
    }

    summary_file = BIDDING_FOLDER / 'rag_analysis_summary.json'
    with open(summary_file, 'w') as f:
        json.dump(summary, f, indent=2)

    print(f"\n{'='*60}")
    print(f"BATCH COMPLETE")
    print(f"Successful: {success_count}")
    print(f"Failed: {fail_count}")
    print(f"Summary: {summary_file}")
    print(f"{'='*60}\n")

    return summary


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Parallel RAG analysis for Division 8 projects')
    parser.add_argument('--workers', '-w', type=int, default=4, help='Number of parallel workers (default: 4)')
    parser.add_argument('--all', action='store_true', help='Re-analyze all projects (skip none)')
    parser.add_argument('--limit', type=int, help='Limit number of projects to analyze')
    args = parser.parse_args()

    run_parallel_analysis(
        workers=args.workers,
        skip_existing=not args.all,
        limit=args.limit
    )
