"""
Project Folder Auditor

Uses AI to analyze project folder structure and identify organization issues,
duplicates, misplaced files, and consolidation opportunities.
"""

import os
import json
import hashlib
import time
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional
import requests
from dotenv import load_dotenv

load_dotenv()


def _get_required_env(var_name: str) -> str:
    """Fetch required secrets from the environment to avoid hard-coding keys."""
    value = os.getenv(var_name)
    if not value:
        raise RuntimeError(f"Environment variable {var_name} is required but not set.")
    return value

# Rate limiting for OpenRouter free tier (10 calls/min)
_last_api_call = 0
API_CALL_INTERVAL = 6.5  # seconds between calls (slightly over 6 to be safe)

# OpenRouter config
OPENROUTER_API_KEY = _get_required_env("OPENROUTER_API_KEY")
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
AUDIT_MODEL = "openai/gpt-oss-120b:free"

# Ideal folder structure for Division 8 projects
IDEAL_STRUCTURE = {
    "Plans": "Construction drawings, floor plans, elevations, details",
    "Specs": "Project specifications, Division 8 sections",
    "Addendum": "Addenda and ASIs",
    "Quotes": "Vendor quotes and proposals",
    "Estimates": "Takeoffs, pricing spreadsheets",
    "Submittals": "Product submittals and shop drawings",
    "RFIs": "Requests for information",
    "Photos": "Site photos",
}

# File type classifications
FILE_TYPES = {
    "drawings": [".pdf", ".dwg", ".dxf"],
    "specs": [".pdf", ".docx", ".doc"],
    "spreadsheets": [".xlsx", ".xls", ".csv"],
    "images": [".png", ".jpg", ".jpeg", ".tiff", ".tif", ".bmp"],
    "documents": [".docx", ".doc", ".txt", ".rtf"],
    "archives": [".zip", ".rar", ".7z"],
}

# Patterns that suggest file purpose
FILE_PATTERNS = {
    "drawings": ["A-", "A0", "A1", "A2", "S-", "M-", "E-", "P-", "plan", "elevation", "detail", "section"],
    "specs": ["spec", "division", "section 08", "08 "],
    "addendum": ["addendum", "add ", "add-", "add_", "asi", "bulletin"],
    "quote": ["quote", "proposal", "pricing", "bid"],
    "estimate": ["estimate", "takeoff", "qty", "quantity"],
    "schedule": ["schedule", "door schedule", "window schedule", "hardware"],
    "submittal": ["submittal", "shop drawing", "cut sheet"],
    "rfi": ["rfi", "request for"],
}


def get_file_hash(filepath: Path, chunk_size: int = 8192) -> str:
    """Get MD5 hash of first 1MB of file for duplicate detection."""
    hasher = hashlib.md5()
    try:
        with open(filepath, 'rb') as f:
            # Only hash first 1MB for speed
            data = f.read(1024 * 1024)
            hasher.update(data)
        return hasher.hexdigest()
    except:
        return ""


def scan_folder(folder: Path) -> Dict:
    """Scan a project folder and collect file information."""
    files = []
    subfolders = []

    for item in folder.iterdir():
        if item.name.startswith('.'):
            continue

        if item.is_dir():
            subfolders.append({
                "name": item.name,
                "file_count": len(list(item.glob("*"))),
                "has_subfolders": any(x.is_dir() for x in item.iterdir() if not x.name.startswith('.'))
            })
        elif item.is_file():
            stat = item.stat()
            files.append({
                "name": item.name,
                "ext": item.suffix.lower(),
                "size_mb": round(stat.st_size / (1024 * 1024), 2),
                "modified": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d"),
                "hash": get_file_hash(item) if stat.st_size < 50 * 1024 * 1024 else None  # Skip large files
            })

    return {
        "folder_name": folder.name,
        "total_files": len(files),
        "total_subfolders": len(subfolders),
        "files": files,
        "subfolders": subfolders
    }


def find_potential_duplicates(files: List[Dict]) -> List[Dict]:
    """Find files that might be duplicates based on name similarity or hash."""
    duplicates = []
    hash_groups = {}
    name_groups = {}

    for f in files:
        # Group by hash
        if f.get("hash"):
            if f["hash"] not in hash_groups:
                hash_groups[f["hash"]] = []
            hash_groups[f["hash"]].append(f["name"])

        # Group by base name (ignoring version numbers, dates)
        import re
        base_name = re.sub(r'[-_\s]*(v\d+|rev\d*|copy|\d{2}[-_.]\d{2}[-_.]\d{2,4}|\(\d+\))[-_\s]*', '',
                          f["name"].lower(), flags=re.IGNORECASE)
        base_name = re.sub(r'\.[^.]+$', '', base_name)  # Remove extension

        if base_name not in name_groups:
            name_groups[base_name] = []
        name_groups[base_name].append(f["name"])

    # Report hash duplicates
    for hash_val, names in hash_groups.items():
        if len(names) > 1:
            duplicates.append({
                "type": "exact_duplicate",
                "files": names,
                "reason": "Identical file content"
            })

    # Report name-based potential duplicates
    for base, names in name_groups.items():
        if len(names) > 1 and len(base) > 5:  # Ignore very short names
            # Check if already reported as exact duplicate
            if not any(set(names) == set(d["files"]) for d in duplicates):
                duplicates.append({
                    "type": "potential_duplicate",
                    "files": names,
                    "reason": "Similar file names (may be versions)"
                })

    return duplicates


def classify_file(filename: str) -> str:
    """Classify a file based on its name patterns."""
    lower_name = filename.lower()

    for category, patterns in FILE_PATTERNS.items():
        for pattern in patterns:
            if pattern.lower() in lower_name:
                return category

    # Fallback to extension-based classification
    ext = Path(filename).suffix.lower()
    if ext in [".xlsx", ".xls", ".csv"]:
        return "spreadsheet"
    elif ext in [".png", ".jpg", ".jpeg", ".tiff", ".tif"]:
        return "image"
    elif ext == ".pdf":
        return "document"

    return "unknown"


def analyze_organization(scan_data: Dict) -> Dict:
    """Analyze folder organization and identify issues."""
    issues = []
    suggestions = []

    files = scan_data["files"]
    subfolders = {sf["name"].lower(): sf for sf in scan_data["subfolders"]}

    # Check for standard folders
    standard_folders = ["plans", "specs", "addendum", "quotes", "estimates"]
    missing_folders = []
    for folder in standard_folders:
        if folder not in subfolders:
            # Check if there are files that should go there
            relevant_files = [f for f in files if classify_file(f["name"]) == folder.rstrip('s')]
            if relevant_files:
                missing_folders.append(folder)

    if missing_folders:
        issues.append({
            "type": "missing_folders",
            "severity": "medium",
            "details": f"Missing standard folders: {', '.join(missing_folders)}"
        })

    # Check for files at root that should be in subfolders
    root_files_by_type = {}
    for f in files:
        if f["name"].endswith(".json") or f["name"].endswith(".txt"):
            continue  # Skip metadata files
        ftype = classify_file(f["name"])
        if ftype not in root_files_by_type:
            root_files_by_type[ftype] = []
        root_files_by_type[ftype].append(f["name"])

    for ftype, fnames in root_files_by_type.items():
        if ftype != "unknown" and len(fnames) > 2:
            issues.append({
                "type": "disorganized_files",
                "severity": "low",
                "details": f"{len(fnames)} {ftype} files at root level should be in subfolder"
            })

    # Check for very large files
    large_files = [f for f in files if f["size_mb"] > 100]
    if large_files:
        issues.append({
            "type": "large_files",
            "severity": "info",
            "details": f"{len(large_files)} files over 100MB: {', '.join(f['name'] for f in large_files[:3])}"
        })

    # Find duplicates
    duplicates = find_potential_duplicates(files)
    if duplicates:
        exact = [d for d in duplicates if d["type"] == "exact_duplicate"]
        potential = [d for d in duplicates if d["type"] == "potential_duplicate"]

        if exact:
            issues.append({
                "type": "duplicates",
                "severity": "high",
                "details": f"{len(exact)} sets of exact duplicate files found"
            })
        if potential:
            issues.append({
                "type": "potential_duplicates",
                "severity": "medium",
                "details": f"{len(potential)} sets of potentially duplicate files (versions?)"
            })

    return {
        "issues": issues,
        "duplicates": duplicates,
        "file_classification": root_files_by_type,
        "organization_score": calculate_org_score(issues, scan_data)
    }


def calculate_org_score(issues: List[Dict], scan_data: Dict) -> int:
    """Calculate organization score 0-100."""
    score = 100

    # Deduct for issues
    for issue in issues:
        if issue["severity"] == "high":
            score -= 20
        elif issue["severity"] == "medium":
            score -= 10
        elif issue["severity"] == "low":
            score -= 5

    # Bonus for having standard folders
    standard_folders = ["plans", "specs"]
    subfolders = [sf["name"].lower() for sf in scan_data["subfolders"]]
    for folder in standard_folders:
        if folder in subfolders:
            score += 5

    return max(0, min(100, score))


def get_ai_analysis(scan_data: Dict, analysis: Dict) -> Dict:
    """Get AI-powered analysis and recommendations using gpt-oss-120b."""
    global _last_api_call

    # Rate limiting
    elapsed = time.time() - _last_api_call
    if elapsed < API_CALL_INTERVAL:
        wait_time = API_CALL_INTERVAL - elapsed
        print(f"  Rate limiting: waiting {wait_time:.1f}s...")
        time.sleep(wait_time)

    _last_api_call = time.time()

    # Build context for AI
    file_summary = []
    for f in scan_data["files"][:30]:  # Limit for context
        file_summary.append(f"{f['name']} ({f['size_mb']}MB, {f['modified']})")

    subfolder_summary = [sf["name"] for sf in scan_data["subfolders"]]

    prompt = f"""Analyze this construction project folder and provide recommendations.

PROJECT: {scan_data['folder_name']}

SUBFOLDERS: {', '.join(subfolder_summary) if subfolder_summary else 'None'}

FILES AT ROOT ({len(scan_data['files'])} total, showing first 30):
{chr(10).join(file_summary)}

DETECTED ISSUES:
{json.dumps(analysis['issues'], indent=2)}

POTENTIAL DUPLICATES:
{json.dumps(analysis['duplicates'][:5], indent=2) if analysis['duplicates'] else 'None'}

Based on this, provide:
1. A brief assessment (2-3 sentences) of the folder organization
2. Top 3 specific recommendations to improve organization
3. Files that should be moved to subfolders (if any)
4. Files that appear to be duplicates or old versions that could be archived

Respond in JSON format:
{{
    "assessment": "string",
    "recommendations": ["string", "string", "string"],
    "files_to_move": [{{"file": "name", "destination": "folder"}}],
    "files_to_archive": ["filename1", "filename2"]
}}"""

    try:
        response = requests.post(
            f"{OPENROUTER_BASE_URL}/chat/completions",
            headers={
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "Content-Type": "application/json",
                "HTTP-Referer": "http://localhost:5003",
            },
            json={
                "model": AUDIT_MODEL,
                "messages": [
                    {"role": "system", "content": "You are a construction project organization expert. Analyze folder structures and provide actionable recommendations. Always respond in valid JSON."},
                    {"role": "user", "content": prompt}
                ],
                "max_tokens": 1500,
                "temperature": 0.3
            },
            timeout=60
        )

        if response.status_code == 200:
            content = response.json()["choices"][0]["message"]["content"]
            # Try to parse JSON from response
            try:
                # Handle markdown code blocks
                if "```json" in content:
                    content = content.split("```json")[1].split("```")[0]
                elif "```" in content:
                    content = content.split("```")[1].split("```")[0]

                # Clean up potential truncation - find last complete JSON object
                content = content.strip()
                if not content.endswith("}"):
                    # Try to find last complete structure
                    last_brace = content.rfind("}")
                    if last_brace > 0:
                        content = content[:last_brace + 1]

                return json.loads(content)
            except json.JSONDecodeError as e:
                # Return raw content if JSON parsing fails
                return {
                    "assessment": content[:500] if len(content) > 500 else content,
                    "recommendations": [],
                    "files_to_move": [],
                    "files_to_archive": [],
                    "parse_error": str(e)
                }
        else:
            return {"error": f"API error: {response.status_code}", "raw": response.text[:500]}

    except Exception as e:
        return {"error": str(e)}


def audit_project_folder(folder_path: str | Path, use_ai: bool = True) -> Dict:
    """Run a complete audit on a project folder."""
    folder = Path(folder_path)

    if not folder.exists():
        return {"error": f"Folder not found: {folder_path}"}

    # Scan folder
    scan_data = scan_folder(folder)

    # Analyze organization
    analysis = analyze_organization(scan_data)

    # Get AI recommendations if requested
    ai_analysis = {}
    if use_ai:
        ai_analysis = get_ai_analysis(scan_data, analysis)

    return {
        "folder": str(folder),
        "folder_name": folder.name,
        "scanned_at": datetime.now().isoformat(),
        "summary": {
            "total_files": scan_data["total_files"],
            "total_subfolders": scan_data["total_subfolders"],
            "organization_score": analysis["organization_score"]
        },
        "scan_data": scan_data,
        "analysis": analysis,
        "ai_recommendations": ai_analysis
    }


def batch_audit_projects(bidding_folder: str | Path, limit: int = None) -> List[Dict]:
    """Audit multiple project folders."""
    bidding = Path(bidding_folder)
    results = []

    skip_folders = {'.claude', 'div8_analyzer', 'tmp_xlsx', 'tmp_bridgeman',
                    'tmp_bridgeman_glass', 'Files', 'BIDS FALL WINTER 2025'}

    folders = sorted([f for f in bidding.iterdir()
                     if f.is_dir() and not f.name.startswith('.') and f.name not in skip_folders])

    if limit:
        folders = folders[:limit]

    for folder in folders:
        print(f"Auditing: {folder.name}")
        result = audit_project_folder(folder, use_ai=True)
        results.append(result)

    return results


def scan_all_projects_for_duplicates(bidding_folder: str | Path) -> Dict:
    """Scan all project folders to find duplicate files across projects.

    This helps identify files that exist in multiple project folders
    (e.g., from consolidating duplicate project folders).
    """
    bidding = Path(bidding_folder)
    skip_folders = {'.claude', 'div8_analyzer', 'tmp_xlsx', 'tmp_bridgeman',
                    'tmp_bridgeman_glass', 'Files', 'BIDS FALL WINTER 2025'}

    # Hash -> list of (project, filename, size, modified)
    hash_index = {}
    # Name -> list of (project, filename, size, hash)
    name_index = {}

    total_files = 0
    total_size_mb = 0

    print("Scanning all projects for duplicates...")

    for project_folder in bidding.iterdir():
        if not project_folder.is_dir():
            continue
        if project_folder.name.startswith('.') or project_folder.name in skip_folders:
            continue

        project_name = project_folder.name

        # Scan all files recursively
        for filepath in project_folder.rglob('*'):
            if not filepath.is_file():
                continue
            if filepath.name.startswith('.'):
                continue
            # Skip metadata files
            if filepath.suffix.lower() in ['.json', '.db', '.sqlite']:
                continue
            # Skip chroma folders
            if '.chroma' in str(filepath):
                continue

            try:
                stat = filepath.stat()
                size_mb = stat.st_size / (1024 * 1024)
                modified = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d")

                total_files += 1
                total_size_mb += size_mb

                # Only hash files under 100MB for performance
                file_hash = None
                if size_mb < 100:
                    file_hash = get_file_hash(filepath)

                # Get relative path within project
                rel_path = str(filepath.relative_to(project_folder))

                # Index by hash
                if file_hash:
                    if file_hash not in hash_index:
                        hash_index[file_hash] = []
                    hash_index[file_hash].append({
                        'project': project_name,
                        'path': rel_path,
                        'size_mb': round(size_mb, 2),
                        'modified': modified
                    })

                # Index by filename (for similar name detection)
                base_name = filepath.name.lower()
                if base_name not in name_index:
                    name_index[base_name] = []
                name_index[base_name].append({
                    'project': project_name,
                    'path': rel_path,
                    'size_mb': round(size_mb, 2),
                    'hash': file_hash
                })

            except Exception as e:
                continue

    # Find exact duplicates (same hash, different projects)
    cross_project_duplicates = []
    wasted_space_mb = 0

    for file_hash, locations in hash_index.items():
        if len(locations) < 2:
            continue

        # Check if files are in different projects
        projects = set(loc['project'] for loc in locations)
        if len(projects) > 1:
            # This is a cross-project duplicate
            total_size = sum(loc['size_mb'] for loc in locations)
            # Wasted space is total - one copy
            wasted = total_size - locations[0]['size_mb']
            wasted_space_mb += wasted

            cross_project_duplicates.append({
                'hash': file_hash,
                'locations': locations,
                'file_count': len(locations),
                'project_count': len(projects),
                'total_size_mb': round(total_size, 2),
                'wasted_mb': round(wasted, 2)
            })

    # Find same-name files across projects (potential duplicates even if hash differs)
    same_name_across_projects = []
    for name, locations in name_index.items():
        if len(locations) < 2:
            continue
        projects = set(loc['project'] for loc in locations)
        if len(projects) > 1:
            # Group by hash to see if they're truly duplicates or different versions
            hash_groups = {}
            for loc in locations:
                h = loc.get('hash') or 'no_hash'
                if h not in hash_groups:
                    hash_groups[h] = []
                hash_groups[h].append(loc)

            same_name_across_projects.append({
                'filename': name,
                'locations': locations,
                'project_count': len(projects),
                'unique_versions': len(hash_groups),
                'is_exact_duplicate': len(hash_groups) == 1
            })

    # Sort by wasted space
    cross_project_duplicates.sort(key=lambda x: x['wasted_mb'], reverse=True)
    same_name_across_projects.sort(key=lambda x: x['project_count'], reverse=True)

    return {
        'scanned_at': datetime.now().isoformat(),
        'total_files_scanned': total_files,
        'total_size_mb': round(total_size_mb, 2),
        'cross_project_duplicates': {
            'count': len(cross_project_duplicates),
            'wasted_space_mb': round(wasted_space_mb, 2),
            'files': cross_project_duplicates[:100]  # Top 100
        },
        'same_name_files': {
            'count': len(same_name_across_projects),
            'files': same_name_across_projects[:50]  # Top 50
        }
    }


def check_rag_analysis_status(bidding_folder: str | Path) -> Dict:
    """Check RAG analysis status across all projects.

    Identifies:
    - Projects without RAG analysis
    - Projects with old/stale analysis
    - Projects with parse errors or low confidence
    - Projects where file count has changed significantly
    """
    bidding = Path(bidding_folder)
    skip_folders = {'.claude', 'div8_analyzer', 'tmp_xlsx', 'tmp_bridgeman',
                    'tmp_bridgeman_glass', 'Files', 'BIDS FALL WINTER 2025'}

    results = {
        'no_analysis': [],
        'stale_analysis': [],
        'low_confidence': [],
        'parse_errors': [],
        'needs_reindex': [],
        'healthy': []
    }

    for project_folder in bidding.iterdir():
        if not project_folder.is_dir():
            continue
        if project_folder.name.startswith('.') or project_folder.name in skip_folders:
            continue

        project_name = project_folder.name
        rag_file = project_folder / 'division8_rag_analysis.json'

        # Count current PDFs
        current_pdf_count = len(list(project_folder.glob('**/*.pdf')))

        if not rag_file.exists():
            if current_pdf_count > 0:
                results['no_analysis'].append({
                    'project': project_name,
                    'pdf_count': current_pdf_count,
                    'reason': 'No RAG analysis file'
                })
            continue

        try:
            with open(rag_file, 'r') as f:
                data = json.load(f)

            metadata = data.get('_rag_metadata', {})

            # Check for parse errors
            if data.get('parse_error') or 'raw_response' in data:
                results['parse_errors'].append({
                    'project': project_name,
                    'reason': 'JSON parse error in analysis'
                })
                continue

            # Check confidence
            confidence = data.get('confidence', 'unknown')
            if confidence == 'low':
                results['low_confidence'].append({
                    'project': project_name,
                    'confidence': confidence,
                    'chunks_analyzed': metadata.get('chunks_analyzed', 0)
                })

            # Check age
            analyzed_at = metadata.get('generated_at') or metadata.get('analyzed_at')
            if analyzed_at:
                try:
                    if analyzed_at.endswith('Z'):
                        analyzed_at = analyzed_at[:-1] + '+00:00'
                    analyzed_date = datetime.fromisoformat(analyzed_at)
                    if analyzed_date.tzinfo is None:
                        from datetime import timezone
                        analyzed_date = analyzed_date.replace(tzinfo=timezone.utc)

                    age_days = (datetime.now(analyzed_date.tzinfo) - analyzed_date).days

                    if age_days > 30:
                        results['stale_analysis'].append({
                            'project': project_name,
                            'analyzed_at': analyzed_at[:10],
                            'age_days': age_days
                        })
                except:
                    pass

            # Check if file count changed significantly
            indexed_chunks = metadata.get('total_chunks_in_db', 0)
            # Rough estimate: 2 chunks per page, 10 pages per PDF
            expected_chunks = current_pdf_count * 20

            if indexed_chunks > 0 and abs(expected_chunks - indexed_chunks) / indexed_chunks > 0.5:
                results['needs_reindex'].append({
                    'project': project_name,
                    'indexed_chunks': indexed_chunks,
                    'current_pdf_count': current_pdf_count,
                    'reason': 'File count may have changed significantly'
                })
            elif confidence != 'low' and not data.get('parse_error'):
                results['healthy'].append({
                    'project': project_name,
                    'confidence': confidence,
                    'chunks': metadata.get('chunks_analyzed', 0)
                })

        except Exception as e:
            results['parse_errors'].append({
                'project': project_name,
                'reason': f'Error reading file: {str(e)}'
            })

    return {
        'scanned_at': datetime.now().isoformat(),
        'summary': {
            'total_projects': sum(len(v) for v in results.values()),
            'healthy': len(results['healthy']),
            'needs_attention': len(results['no_analysis']) + len(results['parse_errors']) + len(results['low_confidence']),
            'no_analysis': len(results['no_analysis']),
            'stale': len(results['stale_analysis']),
            'low_confidence': len(results['low_confidence']),
            'parse_errors': len(results['parse_errors']),
            'needs_reindex': len(results['needs_reindex'])
        },
        'details': results
    }


if __name__ == "__main__":
    import sys
    from dotenv import load_dotenv
    load_dotenv()

    if len(sys.argv) > 1:
        folder = sys.argv[1]
    else:
        bidding_folder = os.getenv("BIDDING_FOLDER", "")
        if not bidding_folder:
            print("Error: Provide folder path as argument or set BIDDING_FOLDER in .env")
            sys.exit(1)
        # Default to first project in bidding folder
        from pathlib import Path
        folder = str(next(Path(bidding_folder).iterdir()))

    result = audit_project_folder(folder)
    print(json.dumps(result, indent=2))
