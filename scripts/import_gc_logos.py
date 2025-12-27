#!/usr/bin/env python3
"""
GC Logo Import and Quality Analysis Script

Imports GC logos from Email Monitor folder, converts to PNG,
analyzes quality, and generates a report.
"""

import os
import json
import shutil
import re
from pathlib import Path
from PIL import Image
from datetime import datetime

# Load environment
from dotenv import load_dotenv
load_dotenv()

# Project tracker directory (this repo)
PROJECT_TRACKER_DIR = str(Path(__file__).parent.parent)

# Paths - use environment variables where available
EMAIL_MONITOR_PATH = os.getenv("EMAIL_MONITOR_PATH", "")
SOURCE_LOGOS_DIR = str(Path(EMAIL_MONITOR_PATH) / "logos") if EMAIL_MONITOR_PATH else ""
TARGET_LOGOS_DIR = str(Path(PROJECT_TRACKER_DIR) / "planhub" / "gc_logos")
MAPPING_FILE = os.path.join(TARGET_LOGOS_DIR, "gc_logo_mapping.json")
REPORT_FILE = str(Path(PROJECT_TRACKER_DIR) / "scripts" / "logo_quality_report.json")

# Project data paths
PLANHUB_PROJECTS_FILE = os.path.join(PROJECT_TRACKER_DIR, "planhub/planhub_projects.json")
BIDDING_FOLDER = os.getenv("BIDDING_FOLDER", "")

# Quality thresholds (for 300 DPI at 50px display)
LOW_RES_THRESHOLD = 150  # pixels
IDEAL_RES_THRESHOLD = 300  # pixels
OVERSIZED_THRESHOLD = 2000  # pixels (larger than needed)
OVERSIZED_SIZE_KB = 200  # KB


def normalize_company_name(name):
    """Normalize company name for matching."""
    name = name.lower()
    # Remove common suffixes
    suffixes = [
        r'\binc\.?\b', r'\bllc\.?\b', r'\bcorp\.?\b', r'\bcorporation\b',
        r'\bco\.?\b', r'\bcompany\b', r'\bgroup\b', r'\bservices\b',
        r'\bcontractors?\b', r'\bconstruction\b', r'\bbuilders?\b',
        r'\bgeneral\b', r'\bcommercial\b', r',', r'\.', r'&'
    ]
    for suffix in suffixes:
        name = re.sub(suffix, '', name)
    # Remove extra whitespace
    name = re.sub(r'\s+', ' ', name).strip()
    return name


def filename_to_company_name(filename):
    """Convert filename to likely company name."""
    # Remove extension
    name = os.path.splitext(filename)[0]
    # Replace underscores with spaces
    name = name.replace('_', ' ')
    # Clean up numbers at end (like _5 or _2)
    name = re.sub(r'\s+\d+$', '', name)
    return name


def get_image_info(filepath):
    """Get image dimensions, format, and file size."""
    try:
        file_size_kb = os.path.getsize(filepath) / 1024
        with Image.open(filepath) as img:
            width, height = img.size
            format_name = img.format
            mode = img.mode
            has_alpha = mode in ('RGBA', 'LA', 'PA') or 'transparency' in img.info
            return {
                'width': width,
                'height': height,
                'format': format_name,
                'mode': mode,
                'has_alpha': has_alpha,
                'file_size_kb': round(file_size_kb, 1)
            }
    except Exception as e:
        return {'error': str(e)}


def assess_quality(info):
    """Assess image quality based on dimensions."""
    if 'error' in info:
        return 'error'

    min_dim = min(info['width'], info['height'])

    if min_dim < LOW_RES_THRESHOLD:
        return 'low_res'
    elif min_dim < IDEAL_RES_THRESHOLD:
        return 'good'
    else:
        return 'ideal'


def is_oversized(info):
    """Check if image is unnecessarily large."""
    if 'error' in info:
        return False
    return (max(info['width'], info['height']) > OVERSIZED_THRESHOLD or
            info['file_size_kb'] > OVERSIZED_SIZE_KB)


def convert_to_png(src_path, dst_path):
    """Convert image to PNG format."""
    try:
        with Image.open(src_path) as img:
            # Convert to RGBA if not already
            if img.mode != 'RGBA':
                img = img.convert('RGBA')
            img.save(dst_path, 'PNG')
            return True
    except Exception as e:
        print(f"  Error converting {src_path}: {e}")
        return False


def load_all_gc_names():
    """Load GC names from all project sources."""
    gc_names = set()

    # Load from PlanHub projects
    if os.path.exists(PLANHUB_PROJECTS_FILE):
        try:
            with open(PLANHUB_PROJECTS_FILE) as f:
                data = json.load(f)
                # Handle both dict with 'projects' key and list formats
                if isinstance(data, dict) and 'projects' in data:
                    projects = data['projects'].values() if isinstance(data['projects'], dict) else data['projects']
                elif isinstance(data, list):
                    projects = data
                else:
                    projects = []

                for project in projects:
                    if isinstance(project, dict):
                        for gc in project.get('general_contractors', []):
                            if isinstance(gc, dict) and gc.get('name'):
                                gc_names.add(gc['name'])
        except Exception as e:
            print(f"Warning: Could not load PlanHub projects: {e}")

    # Load from local bidding folders
    if os.path.exists(BIDDING_FOLDER):
        for project_dir in os.listdir(BIDDING_FOLDER):
            project_path = os.path.join(BIDDING_FOLDER, project_dir)
            if os.path.isdir(project_path):
                # Check for extracted_project_data.json
                extracted_file = os.path.join(project_path, 'extracted_project_data.json')
                if os.path.exists(extracted_file):
                    try:
                        with open(extracted_file) as f:
                            data = json.load(f)
                            # Look for GC names in various fields
                            for key in ['general_contractor', 'gc', 'contractor', 'general_contractors']:
                                if key in data:
                                    val = data[key]
                                    if isinstance(val, str):
                                        gc_names.add(val)
                                    elif isinstance(val, list):
                                        for item in val:
                                            if isinstance(item, str):
                                                gc_names.add(item)
                                            elif isinstance(item, dict) and 'name' in item:
                                                gc_names.add(item['name'])
                    except:
                        pass

    return gc_names


def match_logo_to_gc(logo_company_name, gc_names):
    """Try to match a logo to a known GC name."""
    normalized_logo = normalize_company_name(logo_company_name)

    matches = []
    for gc_name in gc_names:
        normalized_gc = normalize_company_name(gc_name)

        # Exact match after normalization
        if normalized_logo == normalized_gc:
            return gc_name

        # Check if one contains the other
        if normalized_logo in normalized_gc or normalized_gc in normalized_logo:
            matches.append(gc_name)

    # Return best match if any
    if matches:
        # Return shortest match (likely most specific)
        return min(matches, key=len)

    return None


def main():
    print("=" * 60)
    print("GC Logo Import and Quality Analysis")
    print("=" * 60)

    # Ensure target directory exists
    os.makedirs(TARGET_LOGOS_DIR, exist_ok=True)

    # Load existing mapping
    if os.path.exists(MAPPING_FILE):
        with open(MAPPING_FILE) as f:
            mapping = json.load(f)
    else:
        mapping = {}

    # Load all known GC names
    print("\nLoading GC names from projects...")
    gc_names = load_all_gc_names()
    print(f"Found {len(gc_names)} unique GC names")

    # Stats
    stats = {
        'total_scanned': 0,
        'imported': 0,
        'converted_to_png': 0,
        'skipped_unknown': 0,
        'skipped_existing': 0,
        'low_res_count': 0,
        'matched_to_gcs': 0
    }

    # Report data
    report = {
        'generated_at': datetime.now().isoformat(),
        'summary': {},
        'low_res_logos': [],
        'converted_files': [],
        'matched_gcs': [],
        'unmatched_logos': [],
        'oversized_logos': [],
        'all_logos': []
    }

    # Get list of logo files (exclude Unknown* and csv)
    logo_files = [f for f in os.listdir(SOURCE_LOGOS_DIR)
                  if not f.startswith('Unknown')
                  and not f.endswith('.csv')
                  and os.path.isfile(os.path.join(SOURCE_LOGOS_DIR, f))]

    print(f"\nProcessing {len(logo_files)} logo files...")
    print("-" * 60)

    for filename in sorted(logo_files):
        stats['total_scanned'] += 1
        src_path = os.path.join(SOURCE_LOGOS_DIR, filename)

        # Get image info
        info = get_image_info(src_path)

        if 'error' in info:
            print(f"  Skipping {filename}: {info['error']}")
            continue

        # Determine company name from filename
        company_name = filename_to_company_name(filename)

        # Check quality
        quality = assess_quality(info)
        is_large = is_oversized(info)

        # Determine output filename (always PNG)
        base_name = os.path.splitext(filename)[0]
        # Normalize to lowercase .png extension
        output_filename = f"{base_name}.png"
        output_path = os.path.join(TARGET_LOGOS_DIR, output_filename)

        # Track logo info
        logo_entry = {
            'original_file': filename,
            'output_file': output_filename,
            'company_name': company_name,
            'dimensions': f"{info['width']}x{info['height']}",
            'original_format': info['format'],
            'file_size_kb': info['file_size_kb'],
            'quality': quality,
            'has_transparency': info['has_alpha']
        }

        # Check if low res
        if quality == 'low_res':
            stats['low_res_count'] += 1
            report['low_res_logos'].append({
                'file': output_filename,
                'dimensions': f"{info['width']}x{info['height']}",
                'needs_replacement': True
            })
            print(f"  LOW RES: {filename} ({info['width']}x{info['height']})")

        # Check if oversized
        if is_large:
            report['oversized_logos'].append({
                'file': output_filename,
                'dimensions': f"{info['width']}x{info['height']}",
                'size_kb': info['file_size_kb']
            })

        # Convert and copy
        needs_conversion = info['format'] not in ('PNG',)

        if os.path.exists(output_path):
            # Check if source is newer
            src_mtime = os.path.getmtime(src_path)
            dst_mtime = os.path.getmtime(output_path)
            if src_mtime <= dst_mtime:
                stats['skipped_existing'] += 1
                # Still update mapping if needed
            else:
                # Re-import newer version
                if needs_conversion:
                    convert_to_png(src_path, output_path)
                    stats['converted_to_png'] += 1
                    report['converted_files'].append({
                        'original': filename,
                        'new': output_filename
                    })
                else:
                    shutil.copy2(src_path, output_path)
                stats['imported'] += 1
        else:
            # New file
            if needs_conversion:
                if convert_to_png(src_path, output_path):
                    stats['converted_to_png'] += 1
                    report['converted_files'].append({
                        'original': filename,
                        'new': output_filename
                    })
                    stats['imported'] += 1
            else:
                shutil.copy2(src_path, output_path)
                stats['imported'] += 1

        # Try to match to known GC
        matched_gc = match_logo_to_gc(company_name, gc_names)

        if matched_gc:
            stats['matched_to_gcs'] += 1
            logo_entry['matched_gc'] = matched_gc

            # Add to mapping
            mapping[matched_gc] = {
                'original_file': filename,
                'renamed_file': output_filename
            }

            report['matched_gcs'].append({
                'gc_name': matched_gc,
                'logo': output_filename,
                'company_from_filename': company_name
            })
        else:
            # Add mapping based on filename
            mapping[company_name] = {
                'original_file': filename,
                'renamed_file': output_filename
            }
            report['unmatched_logos'].append({
                'file': output_filename,
                'company_guess': company_name
            })

        report['all_logos'].append(logo_entry)

    # Update summary
    report['summary'] = {
        'total_logos': stats['total_scanned'],
        'imported': stats['imported'],
        'converted_to_png': stats['converted_to_png'],
        'skipped_existing': stats['skipped_existing'],
        'low_res_count': stats['low_res_count'],
        'matched_to_gcs': stats['matched_to_gcs'],
        'unmatched_count': len(report['unmatched_logos']),
        'oversized_count': len(report['oversized_logos'])
    }

    # Save updated mapping
    with open(MAPPING_FILE, 'w') as f:
        json.dump(mapping, f, indent=2)
    print(f"\nUpdated mapping file: {MAPPING_FILE}")
    print(f"Total GC mappings: {len(mapping)}")

    # Save report
    with open(REPORT_FILE, 'w') as f:
        json.dump(report, f, indent=2)
    print(f"Generated report: {REPORT_FILE}")

    # Print summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Total logos scanned:    {stats['total_scanned']}")
    print(f"Imported/updated:       {stats['imported']}")
    print(f"Converted to PNG:       {stats['converted_to_png']}")
    print(f"Skipped (existing):     {stats['skipped_existing']}")
    print(f"Matched to GCs:         {stats['matched_to_gcs']}")
    print(f"Unmatched:              {len(report['unmatched_logos'])}")
    print(f"LOW RES (< 150px):      {stats['low_res_count']}")
    print(f"Oversized:              {len(report['oversized_logos'])}")

    if report['low_res_logos']:
        print("\n" + "-" * 40)
        print("LOW RES LOGOS (need replacement):")
        for logo in report['low_res_logos']:
            print(f"  - {logo['file']} ({logo['dimensions']})")

    if report['oversized_logos'][:5]:
        print("\n" + "-" * 40)
        print("OVERSIZED LOGOS (top 5):")
        for logo in sorted(report['oversized_logos'], key=lambda x: x['size_kb'], reverse=True)[:5]:
            print(f"  - {logo['file']} ({logo['dimensions']}, {logo['size_kb']}KB)")

    print("\nDone!")
    return report


if __name__ == '__main__':
    main()
