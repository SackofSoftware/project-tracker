#!/usr/bin/env python3
"""
Batch Embeddings Only - Using Local Ollama

Phase 1: Chunk all docs and embed with Ollama nomic-embed-text (FAST)
Phase 2: Later run GPT-5 nano generation on embedded projects

This script ONLY does embeddings - no GPT calls.
"""

import os
import sys
import json
import logging
from pathlib import Path
from datetime import datetime
import time
import signal
from contextlib import contextmanager

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(message)s'
)
logger = logging.getLogger(__name__)

from dotenv import load_dotenv
load_dotenv()

_bidding_folder = os.getenv('BIDDING_FOLDER', '')
if not _bidding_folder:
    raise RuntimeError("BIDDING_FOLDER environment variable not set. Copy .env.example to .env and configure.")
BIDDING_FOLDER = Path(_bidding_folder)

SKIP_FOLDERS = {
    'div8_analyzer', 'tmp_xlsx', 'tmp_bridgeman',
    'tmp_bridgeman_glass', 'Files', 'BIDS FALL WINTER 2025',
    '.chroma', '.chroma_local'
}

# Timeout for PDF operations (per file)
PDF_TIMEOUT_SECONDS = 60  # 1 minute per PDF (was 120)
MAX_PDFS_PER_PROJECT = 50  # Skip huge projects (was 200)


class PDFTimeoutError(Exception):
    """Raised when PDF processing times out"""
    pass


@contextmanager
def timeout_context(seconds, error_message="Operation timed out"):
    """Context manager for timeout with signal alarm"""
    def timeout_handler(signum, frame):
        raise PDFTimeoutError(error_message)

    # Set the signal handler
    old_handler = signal.signal(signal.SIGALRM, timeout_handler)
    signal.alarm(seconds)
    try:
        yield
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, old_handler)


def has_documents(folder: Path) -> bool:
    """Check if folder has any REAL PDFs or Word docs (not cloud placeholders)"""
    # Only count files with actual content (size > 0)
    pdfs = [f for f in folder.rglob("*.pdf") if f.stat().st_size > 1000]  # At least 1KB
    docx = [f for f in folder.rglob("*.docx") if not f.name.startswith('~$') and f.stat().st_size > 1000]
    return len(pdfs) > 0 or len(docx) > 0


def is_already_embedded(folder: Path) -> bool:
    """Check if folder has ChromaDB embeddings"""
    chroma_dir = folder / ".chroma_local"
    return chroma_dir.exists() and any(chroma_dir.iterdir())


def embed_project(folder: Path) -> dict:
    """Chunk and embed a single project (no GPT generation)"""
    try:
        # Import here to avoid startup delay
        from modules.rag.ollama_embeddings import OllamaEmbedder
        import chromadb
        import pdfplumber
        import hashlib

        project_id = folder.name
        chroma_dir = folder / ".chroma_local"
        chroma_dir.mkdir(exist_ok=True)

        # Sanitize collection name
        collection_name = ''.join(c if c.isalnum() else '_' for c in project_id.lower())
        collection_name = collection_name.strip('_')[:63]
        if len(collection_name) < 3:
            collection_name = collection_name + '_col'

        # Find documents
        pdf_files = list(folder.rglob("*.pdf"))
        docx_files = [f for f in folder.rglob("*.docx") if not f.name.startswith('~$')]

        logger.info(f"  Found {len(pdf_files)} PDFs, {len(docx_files)} docs")

        # Skip very large projects
        if len(pdf_files) > MAX_PDFS_PER_PROJECT:
            logger.warning(f"  SKIPPED: Too many PDFs ({len(pdf_files)} > {MAX_PDFS_PER_PROJECT})")
            return {
                'folder': folder.name,
                'status': 'skipped_too_large',
                'pdf_count': len(pdf_files)
            }

        # Chunk documents
        chunks = []
        files_processed = 0
        files_skipped = 0

        for pdf_path in pdf_files:
            # Skip cloud-only files (size 0)
            try:
                if pdf_path.stat().st_size == 0:
                    files_skipped += 1
                    continue
            except:
                files_skipped += 1
                continue

            try:
                # Use timeout to prevent hanging on large/slow files
                with timeout_context(PDF_TIMEOUT_SECONDS, f"Timeout reading {pdf_path.name}"):
                    with pdfplumber.open(str(pdf_path)) as pdf:
                        for page_num, page in enumerate(pdf.pages):
                            text = page.extract_text() or ""
                            if not text.strip():
                                continue

                            # Simple chunking - 1000 chars with 200 overlap
                            chunk_size = 1000
                            overlap = 200

                            if len(text) <= chunk_size:
                                chunk_id = hashlib.md5(f"{pdf_path.name}:{page_num}:0".encode()).hexdigest()[:12]
                                chunks.append({
                                    'id': chunk_id,
                                    'text': text,
                                    'source': pdf_path.name,
                                    'page': page_num
                                })
                            else:
                                start = 0
                                chunk_num = 0
                                while start < len(text):
                                    chunk_text = text[start:start+chunk_size]
                                    chunk_id = hashlib.md5(f"{pdf_path.name}:{page_num}:{chunk_num}".encode()).hexdigest()[:12]
                                    chunks.append({
                                        'id': chunk_id,
                                        'text': chunk_text,
                                        'source': pdf_path.name,
                                        'page': page_num
                                    })
                                    start += chunk_size - overlap
                                    chunk_num += 1

                files_processed += 1

            except PDFTimeoutError as e:
                logger.warning(f"  TIMEOUT: {pdf_path.name} (>{PDF_TIMEOUT_SECONDS}s) - skipping")
                files_skipped += 1
            except Exception as e:
                logger.warning(f"  Error processing {pdf_path.name}: {e}")
                files_skipped += 1

        if not chunks:
            return {
                'folder': folder.name,
                'status': 'no_chunks',
                'files_processed': files_processed,
                'files_skipped': files_skipped
            }

        logger.info(f"  Created {len(chunks)} chunks from {files_processed} files")

        # Embed with Ollama
        embedder = OllamaEmbedder("nomic-embed-text")

        # ChromaDB
        client = chromadb.PersistentClient(path=str(chroma_dir))

        # Delete existing collection if present
        try:
            client.delete_collection(collection_name)
        except:
            pass

        collection = client.create_collection(
            name=collection_name,
            metadata={"project_id": project_id, "embedder": "ollama-nomic"}
        )

        # Embed in batches
        batch_size = 50
        for i in range(0, len(chunks), batch_size):
            batch = chunks[i:i+batch_size]

            texts = [c['text'] for c in batch]
            ids = [c['id'] for c in batch]
            metadatas = [{'source': c['source'], 'page': c['page']} for c in batch]

            embeddings = embedder.embed(texts)

            # Filter empty embeddings
            valid = [(ids[j], embeddings[j], texts[j], metadatas[j])
                     for j in range(len(embeddings)) if embeddings[j]]

            if valid:
                collection.add(
                    ids=[v[0] for v in valid],
                    embeddings=[v[1] for v in valid],
                    documents=[v[2] for v in valid],
                    metadatas=[v[3] for v in valid]
                )

            if (i + batch_size) % 200 == 0:
                logger.info(f"  Embedded {min(i+batch_size, len(chunks))}/{len(chunks)}")

        # Save embedding metadata
        meta_file = folder / ".chroma_local" / "embed_meta.json"
        with open(meta_file, 'w') as f:
            json.dump({
                'project_id': project_id,
                'embedded_at': datetime.now().isoformat(),
                'chunks': len(chunks),
                'files_processed': files_processed,
                'files_skipped': files_skipped,
                'embedder': 'ollama-nomic-embed-text'
            }, f, indent=2)

        return {
            'folder': folder.name,
            'status': 'success',
            'chunks': len(chunks),
            'files_processed': files_processed,
            'files_skipped': files_skipped
        }

    except Exception as e:
        logger.error(f"  FAILED: {e}")
        return {
            'folder': folder.name,
            'status': 'error',
            'error': str(e)
        }


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--force', action='store_true', help='Re-embed all')
    parser.add_argument('--limit', type=int, help='Max projects')
    args = parser.parse_args()

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

    # Filter already embedded
    if args.force:
        to_process = with_docs
    else:
        to_process = [f for f in with_docs if not is_already_embedded(f)]
        skipped = len(with_docs) - len(to_process)
        if skipped > 0:
            logger.info(f"Skipping {skipped} already embedded")

    if args.limit:
        to_process = to_process[:args.limit]

    logger.info(f"Will embed {len(to_process)} projects")
    logger.info("="*60)

    start_time = time.time()
    results = []
    completed = 0
    failed = 0

    for i, folder in enumerate(to_process):
        logger.info(f"[{i+1}/{len(to_process)}] {folder.name}")

        result = embed_project(folder)
        results.append(result)

        if result['status'] == 'success':
            completed += 1
        elif result['status'] == 'error':
            failed += 1

        # Progress
        elapsed = time.time() - start_time
        rate = (i+1) / elapsed * 60 if elapsed > 0 else 0
        remaining = len(to_process) - (i+1)
        eta = remaining / (rate/60) if rate > 0 else 0

        if (i+1) % 5 == 0:
            logger.info(f"Progress: {i+1}/{len(to_process)} ({rate:.1f}/min, ETA: {eta/60:.0f}min)")

    elapsed = time.time() - start_time
    logger.info("="*60)
    logger.info(f"EMBEDDING COMPLETE")
    logger.info(f"  Completed: {completed}")
    logger.info(f"  Failed: {failed}")
    logger.info(f"  Time: {elapsed/60:.1f} minutes")

    # Save log
    log_file = BIDDING_FOLDER / 'batch_embed_log.json'
    with open(log_file, 'w') as f:
        json.dump({
            'run_at': datetime.now().isoformat(),
            'total': len(to_process),
            'completed': completed,
            'failed': failed,
            'elapsed_seconds': elapsed,
            'results': results
        }, f, indent=2)

    logger.info(f"Log: {log_file}")


if __name__ == '__main__':
    main()
