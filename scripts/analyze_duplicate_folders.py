#!/usr/bin/env python3
"""
Analyze Duplicate Project Folders

Identifies project folder pairs/groups that appear to be duplicates and
recommends which to keep based on:
- File count and total size
- Most recent modifications
- Folder organization (subfolders vs flat)
- Presence of estimates, quotes, RAG analysis
"""

import os
import json
import os
from pathlib import Path
from datetime import datetime
from collections import defaultdict

from dotenv import load_dotenv
load_dotenv()

_bidding = os.getenv("BIDDING_FOLDER", "")
if not _bidding:
    print("Error: BIDDING_FOLDER environment variable not set")
    import sys
    sys.exit(1)
BIDDING_FOLDER = Path(_bidding)

# Known duplicate folder groups (from cross-project duplicate scan)
SUSPECTED_DUPLICATES = [
    ['Natick Building 2 Facade', 'DB Natick Building 2 Facade', 'Repair Exteriors, Building 2-2'],
    ['Warren Center Barn & Parking', 'MSCBA Warren Center Barn - Ashland MA'],
    ['City of Lowell - Cawley Training Center', 'Cawley Training'],
    ['REPAIR SQUADRON OPERATIONS BLDG 7087 (HANGAR 1) WESTOVER AIR RESERVE BASE, MASSACHUSETTS', 'Westover B7087'],
]


def analyze_folder(folder: Path) -> dict:
    """Analyze a project folder and return metrics."""
    if not folder.exists():
        return {'exists': False, 'name': folder.name}

    # Count files by type
    pdfs = list(folder.rglob('*.pdf'))
    xlsx = list(folder.rglob('*.xlsx'))
    docx = list(folder.rglob('*.docx'))
    all_files = list(folder.rglob('*'))
    all_files = [f for f in all_files if f.is_file() and not f.name.startswith('.')]

    # Calculate total size
    total_size = sum(f.stat().st_size for f in all_files if f.exists())

    # Find most recent modification
    most_recent = None
    for f in all_files:
        try:
            mtime = f.stat().st_mtime
            if most_recent is None or mtime > most_recent:
                most_recent = mtime
        except:
            pass

    # Count subfolders
    subfolders = [d for d in folder.iterdir() if d.is_dir() and not d.name.startswith('.')]

    # Check for important files
    has_rag = (folder / 'division8_rag_analysis.json').exists()
    has_extracted = (folder / 'extracted_project_data.json').exists()
    has_estimate = any('estimate' in f.name.lower() or 'takeoff' in f.name.lower()
                      for f in all_files)
    has_quote = any('quote' in f.name.lower() or 'proposal' in f.name.lower()
                   for f in all_files)

    # Standard folder structure
    standard_folders = {'plans', 'specs', 'addendum', 'quotes', 'estimates'}
    has_standard_structure = len(set(s.name.lower() for s in subfolders) & standard_folders) >= 2

    return {
        'exists': True,
        'name': folder.name,
        'path': str(folder),
        'total_files': len(all_files),
        'pdf_count': len(pdfs),
        'xlsx_count': len(xlsx),
        'docx_count': len(docx),
        'total_size_mb': round(total_size / (1024 * 1024), 2),
        'subfolder_count': len(subfolders),
        'subfolders': [s.name for s in subfolders],
        'has_standard_structure': has_standard_structure,
        'most_recent': datetime.fromtimestamp(most_recent).strftime('%Y-%m-%d') if most_recent else None,
        'has_rag_analysis': has_rag,
        'has_extracted_data': has_extracted,
        'has_estimates': has_estimate,
        'has_quotes': has_quote,
    }


def score_folder(analysis: dict) -> int:
    """Score a folder - higher is better to keep."""
    if not analysis.get('exists'):
        return -1

    score = 0

    # More files = better
    score += min(analysis['total_files'], 100)  # Cap at 100

    # Larger size = better (has more content)
    score += min(analysis['total_size_mb'] / 10, 50)  # Cap contribution

    # Standard structure = much better
    if analysis['has_standard_structure']:
        score += 50

    # Subfolders = better organized
    score += analysis['subfolder_count'] * 5

    # Has important files
    if analysis['has_rag_analysis']:
        score += 20
    if analysis['has_extracted_data']:
        score += 15
    if analysis['has_estimates']:
        score += 25
    if analysis['has_quotes']:
        score += 25

    # Recency bonus
    if analysis['most_recent']:
        try:
            recent = datetime.strptime(analysis['most_recent'], '%Y-%m-%d')
            days_old = (datetime.now() - recent).days
            if days_old < 30:
                score += 30
            elif days_old < 90:
                score += 15
        except:
            pass

    return int(score)


def find_unique_files(folder1: Path, folder2: Path) -> dict:
    """Find files that exist in one folder but not the other."""
    def get_file_hashes(folder):
        import hashlib
        hashes = {}
        for f in folder.rglob('*'):
            if f.is_file() and not f.name.startswith('.') and '.chroma' not in str(f):
                try:
                    with open(f, 'rb') as file:
                        data = file.read(1024 * 1024)  # First 1MB
                        h = hashlib.md5(data).hexdigest()
                        hashes[h] = f.name
                except:
                    pass
        return hashes

    hashes1 = get_file_hashes(folder1)
    hashes2 = get_file_hashes(folder2)

    only_in_1 = {h: n for h, n in hashes1.items() if h not in hashes2}
    only_in_2 = {h: n for h, n in hashes2.items() if h not in hashes1}
    common = {h: n for h, n in hashes1.items() if h in hashes2}

    return {
        'only_in_first': list(only_in_1.values()),
        'only_in_second': list(only_in_2.values()),
        'common_files': len(common)
    }


def analyze_duplicate_group(folder_names: list) -> dict:
    """Analyze a group of suspected duplicate folders."""
    folders = [BIDDING_FOLDER / name for name in folder_names]
    analyses = [analyze_folder(f) for f in folders]
    scores = [score_folder(a) for a in analyses]

    # Find the best folder
    best_idx = scores.index(max(scores))

    # Analyze file overlap between pairs
    file_analysis = []
    for i, f1 in enumerate(folders):
        for j, f2 in enumerate(folders):
            if i < j and f1.exists() and f2.exists():
                overlap = find_unique_files(f1, f2)
                file_analysis.append({
                    'folder1': folder_names[i],
                    'folder2': folder_names[j],
                    'unique_to_first': len(overlap['only_in_first']),
                    'unique_to_second': len(overlap['only_in_second']),
                    'common_files': overlap['common_files'],
                    'unique_files_first': overlap['only_in_first'][:10],
                    'unique_files_second': overlap['only_in_second'][:10],
                })

    return {
        'folders': analyses,
        'scores': scores,
        'recommendation': {
            'keep': folder_names[best_idx],
            'keep_score': scores[best_idx],
            'merge_from': [n for i, n in enumerate(folder_names) if i != best_idx and analyses[i].get('exists')],
            'delete_after_merge': [n for i, n in enumerate(folder_names) if i != best_idx and analyses[i].get('exists')],
        },
        'file_overlap': file_analysis
    }


def main():
    print("=" * 70)
    print("DUPLICATE PROJECT FOLDER ANALYSIS")
    print("=" * 70)

    results = []

    for group in SUSPECTED_DUPLICATES:
        print(f"\n\nAnalyzing: {group[0][:50]}...")
        analysis = analyze_duplicate_group(group)
        results.append(analysis)

        print("\n" + "-" * 60)
        print(f"GROUP: {len(group)} folders")
        print("-" * 60)

        for i, folder in enumerate(analysis['folders']):
            if not folder.get('exists'):
                print(f"\n  [{i+1}] {folder['name']}")
                print(f"      STATUS: Does not exist")
                continue

            marker = " ** KEEP **" if folder['name'] == analysis['recommendation']['keep'] else ""
            print(f"\n  [{i+1}] {folder['name']}{marker}")
            print(f"      Score: {analysis['scores'][i]}")
            print(f"      Files: {folder['total_files']} ({folder['total_size_mb']} MB)")
            print(f"      PDFs: {folder['pdf_count']}, XLSX: {folder['xlsx_count']}")
            print(f"      Subfolders: {folder['subfolder_count']} - {folder['subfolders'][:5]}")
            print(f"      Structure: {'Organized' if folder['has_standard_structure'] else 'Flat'}")
            print(f"      Has RAG: {folder['has_rag_analysis']}, Estimates: {folder['has_estimates']}, Quotes: {folder['has_quotes']}")
            print(f"      Last Modified: {folder['most_recent']}")

        print(f"\n  FILE OVERLAP:")
        for overlap in analysis['file_overlap']:
            print(f"    {overlap['folder1'][:30]} vs {overlap['folder2'][:30]}")
            print(f"      Common: {overlap['common_files']}, Unique to first: {overlap['unique_to_first']}, Unique to second: {overlap['unique_to_second']}")
            if overlap['unique_to_first'] > 0:
                print(f"      Files only in first: {overlap['unique_files_first'][:5]}")
            if overlap['unique_to_second'] > 0:
                print(f"      Files only in second: {overlap['unique_files_second'][:5]}")

        rec = analysis['recommendation']
        print(f"\n  RECOMMENDATION:")
        print(f"    KEEP: {rec['keep']} (score: {rec['keep_score']})")
        if rec['merge_from']:
            print(f"    MERGE FILES FROM: {rec['merge_from']}")
            print(f"    THEN DELETE: {rec['delete_after_merge']}")

    # Save results
    output_file = BIDDING_FOLDER / 'duplicate_folder_analysis.json'
    with open(output_file, 'w') as f:
        json.dump(results, f, indent=2)
    print(f"\n\nFull analysis saved to: {output_file}")

    # Print summary
    print("\n" + "=" * 70)
    print("SUMMARY - ACTION ITEMS")
    print("=" * 70)

    for analysis in results:
        rec = analysis['recommendation']
        if rec['merge_from']:
            print(f"\n  KEEP: {rec['keep']}")
            for merge in rec['merge_from']:
                # Find unique files to copy
                for overlap in analysis['file_overlap']:
                    if overlap['folder2'] == merge or overlap['folder1'] == merge:
                        unique = overlap['unique_to_second'] if overlap['folder2'] == merge else overlap['unique_to_first']
                        if unique > 0:
                            print(f"    COPY {unique} unique files from: {merge}")
                        else:
                            print(f"    DELETE (no unique files): {merge}")


if __name__ == '__main__':
    main()
