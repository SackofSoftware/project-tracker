#!/usr/bin/env python3
"""
Batch GPT-5 nano Generation - Phase 2

For projects that already have embeddings (from batch_embed_only.py),
generate Division 8 scope summaries using GPT-5 nano.

This script:
1. Finds all projects with .chroma_local/embed_meta.json (embeddings done)
2. Filters out projects with existing division8_rag_analysis.json
3. Queries embeddings with Division 8 keywords
4. Sends to GPT-5 nano for scope summary generation
5. Saves results to division8_rag_analysis.json

Usage:
    python3 batch_generate_summaries.py                # Process all embedded
    python3 batch_generate_summaries.py --force        # Re-generate all
    python3 batch_generate_summaries.py --limit 10     # Process only 10
    python3 batch_generate_summaries.py --workers 6    # Parallel workers
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
import time

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - [%(threadName)s] %(message)s'
)
logger = logging.getLogger(__name__)

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
total_tokens = 0

# Division 8 query keywords
DIV8_QUERIES = [
    "windows door hardware storefront curtain wall glazing",
    "hollow metal doors frames aluminum entrance",
    "glass specifications performance requirements",
    "door schedule window schedule hardware groups"
]


def has_embeddings(folder: Path) -> bool:
    """Check if project has embeddings"""
    embed_meta = folder / ".chroma_local" / "embed_meta.json"
    return embed_meta.exists()


def has_analysis(folder: Path) -> bool:
    """Check if project already has RAG analysis"""
    analysis_file = folder / "division8_rag_analysis.json"
    return analysis_file.exists()


def generate_summary(folder: Path) -> dict:
    """Generate GPT-5 nano summary for an embedded project"""
    global completed_count, failed_count, total_tokens

    try:
        import chromadb
        import openai
        from modules.rag.ollama_embeddings import OllamaEmbedder

        project_id = folder.name
        chroma_dir = folder / ".chroma_local"

        # Load embed metadata
        embed_meta_file = chroma_dir / "embed_meta.json"
        with open(embed_meta_file) as f:
            embed_meta = json.load(f)

        # Connect to ChromaDB
        client = chromadb.PersistentClient(path=str(chroma_dir))

        # Chroma v0.6.0+ uses list_collections() to get names, then get_collection()
        collection_names = client.list_collections()

        if not collection_names:
            raise ValueError("No collections found in ChromaDB")

        # Get first collection by name (Chroma 0.6+ returns name strings)
        first_name = collection_names[0] if isinstance(collection_names[0], str) else collection_names[0].name
        collection = client.get_collection(first_name)

        # Get embedder for queries
        embedder = OllamaEmbedder("nomic-embed-text")

        # Query with Division 8 keywords
        all_chunks = []
        seen_ids = set()

        for query in DIV8_QUERIES:
            query_embedding = embedder.embed_query(query)

            results = collection.query(
                query_embeddings=[query_embedding],
                n_results=15
            )

            if results and results['documents']:
                for i, doc in enumerate(results['documents'][0]):
                    chunk_id = results['ids'][0][i] if results['ids'] else str(i)
                    if chunk_id not in seen_ids:
                        seen_ids.add(chunk_id)
                        metadata = results['metadatas'][0][i] if results['metadatas'] else {}
                        all_chunks.append({
                            'text': doc,
                            'source': metadata.get('source', 'unknown'),
                            'page': metadata.get('page', 0)
                        })

        if not all_chunks:
            return {
                'folder': folder.name,
                'status': 'no_relevant_chunks',
                'message': 'No Division 8 content found in embeddings'
            }

        # Prepare context for GPT
        context_text = ""
        for chunk in all_chunks[:50]:  # Limit context size
            context_text += f"\n[{chunk['source']} p{chunk['page']}]\n{chunk['text']}\n"

        # Call GPT-5 nano
        openai_client = openai.OpenAI(api_key=OPENAI_API_KEY)

        response = openai_client.chat.completions.create(
            model="gpt-5-nano",
            messages=[
                {
                    "role": "system",
                    "content": """You are analyzing construction project documents for Division 8 scope.

Extract and summarize:
1. Windows: types, quantities, sizes, manufacturers
2. Doors: hollow metal, aluminum, wood (wood = exclude from scope)
3. Storefront/Curtain Wall: systems, sizes, locations
4. Hardware: groups, manufacturers, access control
5. Glass: performance specs, thicknesses, coatings

Format your response as JSON with these keys:
- scope_summary: 2-3 sentence overview
- windows: {count, types, notes}
- doors: {metal_count, wood_count_excluded, notes}
- storefront: {description, sf_estimate}
- hardware: {groups, manufacturers, notes}
- glass: {specs, notes}
- exclusions: list of items NOT in Division 8 scope
- confidence: low/medium/high based on document clarity"""
                },
                {
                    "role": "user",
                    "content": f"Project: {project_id}\n\nDocument excerpts:\n{context_text}\n\nProvide Division 8 scope analysis as JSON:"
                }
            ]
        )

        # Parse response
        gpt_response = response.choices[0].message.content
        tokens_used = response.usage.total_tokens if response.usage else 0

        # Try to parse as JSON
        try:
            # Handle markdown code blocks
            if "```json" in gpt_response:
                gpt_response = gpt_response.split("```json")[1].split("```")[0]
            elif "```" in gpt_response:
                gpt_response = gpt_response.split("```")[1].split("```")[0]

            analysis = json.loads(gpt_response)
        except json.JSONDecodeError:
            # If not valid JSON, wrap the text response
            analysis = {
                "scope_summary": gpt_response[:500],
                "raw_response": gpt_response,
                "parse_error": True
            }

        # Add metadata
        analysis['_rag_metadata'] = {
            'embedder': embed_meta.get('embedder', 'ollama-nomic'),
            'generator': 'gpt-5-nano',
            'chunks_analyzed': len(all_chunks),
            'total_chunks_in_db': embed_meta.get('chunks', 0),
            'tokens_used': tokens_used,
            'generated_at': datetime.now().isoformat()
        }

        # Save results
        output_file = folder / "division8_rag_analysis.json"
        with open(output_file, 'w') as f:
            json.dump(analysis, f, indent=2)

        with progress_lock:
            completed_count += 1
            total_tokens += tokens_used
            logger.info(f"[DONE] {project_id} ({completed_count} done, {tokens_used} tokens)")

        return {
            'folder': folder.name,
            'status': 'success',
            'chunks_analyzed': len(all_chunks),
            'tokens_used': tokens_used
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
    global completed_count, failed_count, total_tokens

    parser = argparse.ArgumentParser(description='Generate GPT summaries for embedded projects')
    parser.add_argument('--force', action='store_true', help='Re-generate all')
    parser.add_argument('--limit', type=int, help='Max projects')
    parser.add_argument('--workers', type=int, default=4, help='Parallel workers (default: 4)')
    args = parser.parse_args()

    # Find all project folders with embeddings
    embedded_folders = []
    for item in BIDDING_FOLDER.iterdir():
        if item.is_dir() and not item.name.startswith('.'):
            if has_embeddings(item):
                embedded_folders.append(item)

    logger.info(f"Found {len(embedded_folders)} projects with embeddings")

    # Filter already analyzed
    if args.force:
        to_process = embedded_folders
        logger.info(f"Force mode: will re-generate all {len(to_process)}")
    else:
        to_process = [f for f in embedded_folders if not has_analysis(f)]
        skipped = len(embedded_folders) - len(to_process)
        if skipped > 0:
            logger.info(f"Skipping {skipped} already analyzed")

    if args.limit:
        to_process = to_process[:args.limit]

    if not to_process:
        logger.info("No projects to process!")
        return

    logger.info(f"Will generate summaries for {len(to_process)} projects with {args.workers} workers")
    logger.info("="*60)

    start_time = time.time()
    results = []

    with ThreadPoolExecutor(max_workers=args.workers, thread_name_prefix='GPT') as executor:
        futures = {executor.submit(generate_summary, folder): folder for folder in to_process}

        for future in as_completed(futures):
            result = future.result()
            results.append(result)

            # Progress update
            total_done = completed_count + failed_count
            elapsed = time.time() - start_time
            rate = total_done / elapsed if elapsed > 0 else 0

            if total_done % 5 == 0:
                remaining = len(to_process) - total_done
                eta_seconds = remaining / rate if rate > 0 else 0
                logger.info(f"Progress: {total_done}/{len(to_process)} ({rate*60:.1f}/min, ETA: {eta_seconds/60:.0f}min)")

    # Summary
    elapsed = time.time() - start_time
    logger.info("="*60)
    logger.info("GENERATION COMPLETE")
    logger.info(f"  Completed: {completed_count}")
    logger.info(f"  Failed: {failed_count}")
    logger.info(f"  Time: {elapsed/60:.1f} minutes")
    logger.info(f"  Total tokens: {total_tokens:,}")
    logger.info(f"  Estimated cost: ${total_tokens * 0.0001:.2f}")  # Rough estimate

    # Save log
    log_file = BIDDING_FOLDER / 'batch_generate_log.json'
    with open(log_file, 'w') as f:
        json.dump({
            'run_at': datetime.now().isoformat(),
            'total_processed': len(to_process),
            'completed': completed_count,
            'failed': failed_count,
            'elapsed_seconds': elapsed,
            'total_tokens': total_tokens,
            'results': results
        }, f, indent=2)

    logger.info(f"Log: {log_file}")


if __name__ == '__main__':
    main()
