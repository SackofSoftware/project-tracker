#!/usr/bin/env python3
"""
Fast Batch RAG Analysis using Local Ollama Embeddings

MUCH faster than OpenAI API:
- No network latency for embeddings
- No rate limits
- Embeddings: Ollama nomic-embed-text (local)
- Generation: GPT-5 nano (fast, cheap API)

Usage:
    python3 batch_rag_local.py                    # Process all unanalyzed
    python3 batch_rag_local.py --force            # Re-process all
    python3 batch_rag_local.py --limit 10         # Process only 10 projects
"""

import os
import sys
import json
import argparse
import logging
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - [%(threadName)s] %(message)s'
)
logger = logging.getLogger(__name__)

# Load environment
from dotenv import load_dotenv
load_dotenv()


def _get_required_env(var_name: str) -> str:
    """Fetch required secrets from the environment to avoid hard-coding keys."""
    value = os.getenv(var_name)
    if not value:
        raise RuntimeError(f"Environment variable {var_name} is required but not set.")
    return value


OPENAI_API_KEY = _get_required_env('OPENAI_API_KEY')
_bidding_folder = os.getenv('BIDDING_FOLDER', '')
if not _bidding_folder:
    raise RuntimeError("BIDDING_FOLDER environment variable not set. Copy .env.example to .env and configure.")
BIDDING_FOLDER = Path(_bidding_folder)

# Track progress
progress_lock = threading.Lock()
completed_count = 0
failed_count = 0
skipped_count = 0

# Folders to skip
SKIP_FOLDERS = {
    'div8_analyzer', 'tmp_xlsx', 'tmp_bridgeman',
    'tmp_bridgeman_glass', 'Files', 'BIDS FALL WINTER 2025',
    '.chroma', '.chroma_local'
}


def has_documents(folder: Path) -> bool:
    """Check if folder has any PDFs or Word docs"""
    pdfs = list(folder.rglob("*.pdf"))
    docx = [f for f in folder.rglob("*.docx") if not f.name.startswith('~$')]
    return len(pdfs) > 0 or len(docx) > 0


def is_already_analyzed(folder: Path) -> bool:
    """Check if folder has recent RAG analysis"""
    rag_file = folder / "division8_rag_analysis.json"
    return rag_file.exists()


def analyze_project(folder: Path) -> dict:
    """Analyze a single project using local RAG"""
    global completed_count, failed_count, skipped_count

    try:
        from modules.rag.division8_rag_local import Division8RAGLocal

        rag = Division8RAGLocal(folder, OPENAI_API_KEY)
        results = rag.analyze_project()
        rag.save_results(results)

        with progress_lock:
            completed_count += 1
            logger.info(f"[COMPLETE] {folder.name} ({completed_count} done)")

        return {
            'folder': folder.name,
            'status': 'success',
            'chunks': results.get('_rag_metadata', {}).get('chunks_analyzed', 0),
            'stats': results.get('_rag_metadata', {}).get('stats', {})
        }

    except Exception as e:
        with progress_lock:
            failed_count += 1
            logger.error(f"[FAILED] {folder.name}: {e}")

        return {
            'folder': folder.name,
            'status': 'error',
            'error': str(e)
        }


def main():
    global completed_count, failed_count, skipped_count

    parser = argparse.ArgumentParser(description='Batch RAG analysis with local embeddings')
    parser.add_argument('--force', action='store_true', help='Re-analyze all projects')
    parser.add_argument('--limit', type=int, help='Max projects to process')
    parser.add_argument('--workers', type=int, default=2, help='Parallel workers (default: 2)')
    args = parser.parse_args()

    # Note: Using fewer workers for local - Ollama handles one at a time anyway
    # More workers helps with parallel GPT generation calls

    # Find project folders
    all_folders = []
    for item in BIDDING_FOLDER.iterdir():
        if item.is_dir() and not item.name.startswith('.'):
            if item.name in SKIP_FOLDERS:
                continue
            all_folders.append(item)

    logger.info(f"Found {len(all_folders)} project folders")

    # Filter to those with documents
    with_docs = [f for f in all_folders if has_documents(f)]
    logger.info(f"Found {len(with_docs)} projects with documents")

    # Filter already analyzed (unless --force)
    if args.force:
        to_process = with_docs
        logger.info(f"Force mode: will re-analyze all {len(to_process)} projects")
    else:
        to_process = [f for f in with_docs if not is_already_analyzed(f)]
        skipped = len(with_docs) - len(to_process)
        logger.info(f"Skipping {skipped} already analyzed")

    # Apply limit
    if args.limit:
        to_process = to_process[:args.limit]

    logger.info(f"Will analyze {len(to_process)} projects with {args.workers} workers")
    logger.info("="*60)

    start_time = datetime.now()
    results = []

    # Process projects
    with ThreadPoolExecutor(max_workers=args.workers, thread_name_prefix='RAG') as executor:
        futures = {executor.submit(analyze_project, folder): folder for folder in to_process}

        for future in as_completed(futures):
            result = future.result()
            results.append(result)

            # Progress update
            total_done = completed_count + failed_count
            elapsed = (datetime.now() - start_time).total_seconds()
            rate = total_done / elapsed if elapsed > 0 else 0

            if total_done % 5 == 0:
                remaining = len(to_process) - total_done
                eta_seconds = remaining / rate if rate > 0 else 0
                eta_minutes = eta_seconds / 60
                logger.info(f"Progress: {total_done}/{len(to_process)} ({rate:.1f}/min, ETA: {eta_minutes:.0f}min)")

    # Final summary
    elapsed = (datetime.now() - start_time).total_seconds()
    logger.info("="*60)
    logger.info(f"BATCH COMPLETE")
    logger.info(f"  Completed: {completed_count}")
    logger.info(f"  Failed: {failed_count}")
    logger.info(f"  Time: {elapsed/60:.1f} minutes")
    logger.info(f"  Rate: {len(to_process)/elapsed*60:.1f} projects/min")

    # Save results log
    log_file = BIDDING_FOLDER / 'batch_rag_local_log.json'
    with open(log_file, 'w') as f:
        json.dump({
            'run_at': datetime.now().isoformat(),
            'total_processed': len(to_process),
            'completed': completed_count,
            'failed': failed_count,
            'elapsed_seconds': elapsed,
            'results': results
        }, f, indent=2)

    logger.info(f"Log saved to: {log_file}")


if __name__ == '__main__':
    main()
