"""
Duplicate File Detector

Detects duplicate files within a project folder using SHA256 hashing.
Handles common duplicate naming patterns:
- file.pdf, file_1.pdf, file_2.pdf
- file.pdf, file (1).pdf, file (2).pdf
- file.pdf, file - Copy.pdf, file - Copy (2).pdf
"""

import os
import re
import hashlib
import shutil
from pathlib import Path
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


@dataclass
class DuplicateGroup:
    """A group of duplicate files"""
    hash: str
    files: List[Path]
    original: Path  # Best candidate to keep
    duplicates: List[Path]  # Files to move
    total_size: int


@dataclass
class DuplicateReport:
    """Results of duplicate detection"""
    project_path: Path
    groups: List[DuplicateGroup]
    total_duplicates: int
    total_wasted_bytes: int
    scan_time: float


def compute_file_hash(file_path: Path, chunk_size: int = 8192) -> str:
    """Compute SHA256 hash of a file"""
    sha256 = hashlib.sha256()
    try:
        with open(file_path, 'rb') as f:
            while chunk := f.read(chunk_size):
                sha256.update(chunk)
        return sha256.hexdigest()
    except (IOError, OSError) as e:
        logger.error(f"Error hashing {file_path}: {e}")
        return ""


def get_clean_name_score(filename: str) -> int:
    """
    Score a filename for "cleanliness" - lower is better (cleaner name).

    Files without duplicate indicators score lower (better).
    """
    score = 0
    name_lower = filename.lower()

    # Penalize common duplicate patterns
    if re.search(r'_\d+\.', filename):  # file_1.pdf
        score += 10
    if re.search(r'\s*\(\d+\)', filename):  # file (1).pdf
        score += 10
    if ' - copy' in name_lower:  # file - Copy.pdf
        score += 20
    if 'copy of' in name_lower:  # Copy of file.pdf
        score += 20
    if re.search(r'\s+\d+\.', filename):  # file 1.pdf
        score += 5

    # Prefer shorter names
    score += len(filename) // 10

    return score


def find_original(files: List[Path]) -> Tuple[Path, List[Path]]:
    """
    Given a list of duplicate files, determine which is the "original"
    and which are duplicates to move.

    Strategy:
    1. Prefer files with cleaner names (no _1, (1), etc.)
    2. If tie, prefer older modification time
    3. If tie, prefer shorter path
    """
    if len(files) == 1:
        return files[0], []

    # Score each file
    scored = []
    for f in files:
        clean_score = get_clean_name_score(f.name)
        mtime = f.stat().st_mtime
        path_len = len(str(f))
        scored.append((f, clean_score, mtime, path_len))

    # Sort by: clean_score (low=better), mtime (older=better), path_len (shorter=better)
    scored.sort(key=lambda x: (x[1], x[2], x[3]))

    original = scored[0][0]
    duplicates = [s[0] for s in scored[1:]]

    return original, duplicates


def detect_duplicates(
    folder_path: Path,
    extensions: Optional[List[str]] = None,
    min_size: int = 1024,  # Skip files smaller than 1KB
    skip_folders: Optional[List[str]] = None
) -> DuplicateReport:
    """
    Detect duplicate files within a folder.

    Args:
        folder_path: Path to scan
        extensions: List of extensions to check (e.g., ['.pdf', '.jpg']). None = all files
        min_size: Minimum file size to consider (skip tiny files)
        skip_folders: Folder names to skip (e.g., ['Duplicates', 'Extracted-Data'])

    Returns:
        DuplicateReport with detected duplicates
    """
    folder_path = Path(folder_path)
    if not folder_path.exists():
        raise ValueError(f"Folder not found: {folder_path}")

    skip_folders = skip_folders or ['Duplicates', 'Extracted-Data', '.chroma_local', '__pycache__']

    start_time = datetime.now()

    # Hash -> list of files with that hash
    hash_map: Dict[str, List[Path]] = {}

    # Scan all files
    for root, dirs, files in os.walk(folder_path):
        # Skip certain directories
        dirs[:] = [d for d in dirs if d not in skip_folders]

        for filename in files:
            file_path = Path(root) / filename

            # Skip by extension
            if extensions and file_path.suffix.lower() not in extensions:
                continue

            # Skip small files
            try:
                size = file_path.stat().st_size
                if size < min_size:
                    continue
            except (IOError, OSError):
                continue

            # Compute hash
            file_hash = compute_file_hash(file_path)
            if not file_hash:
                continue

            if file_hash not in hash_map:
                hash_map[file_hash] = []
            hash_map[file_hash].append(file_path)

    # Build duplicate groups
    groups = []
    total_duplicates = 0
    total_wasted = 0

    for file_hash, files in hash_map.items():
        if len(files) > 1:
            original, duplicates = find_original(files)

            # Calculate wasted space (size of all duplicates)
            dup_size = sum(f.stat().st_size for f in duplicates)
            total_size = sum(f.stat().st_size for f in files)

            groups.append(DuplicateGroup(
                hash=file_hash,
                files=files,
                original=original,
                duplicates=duplicates,
                total_size=total_size
            ))

            total_duplicates += len(duplicates)
            total_wasted += dup_size

    scan_time = (datetime.now() - start_time).total_seconds()

    return DuplicateReport(
        project_path=folder_path,
        groups=groups,
        total_duplicates=total_duplicates,
        total_wasted_bytes=total_wasted,
        scan_time=scan_time
    )


def move_duplicates(
    report: DuplicateReport,
    target_folder: str = "Duplicates",
    dry_run: bool = True
) -> Dict:
    """
    Move duplicate files to a Duplicates/ folder within the project.

    Args:
        report: DuplicateReport from detect_duplicates()
        target_folder: Name of folder to move duplicates to
        dry_run: If True, don't actually move files

    Returns:
        Dict with results (moved files, errors, etc.)
    """
    duplicates_dir = report.project_path / target_folder

    moved = []
    errors = []

    if not dry_run:
        duplicates_dir.mkdir(exist_ok=True)

    for group in report.groups:
        for dup in group.duplicates:
            # Preserve relative path structure in Duplicates folder
            rel_path = dup.relative_to(report.project_path)
            target_path = duplicates_dir / rel_path

            if dry_run:
                moved.append({
                    "from": str(dup),
                    "to": str(target_path),
                    "size": dup.stat().st_size,
                    "original": str(group.original)
                })
            else:
                try:
                    # Create parent directories
                    target_path.parent.mkdir(parents=True, exist_ok=True)

                    # Move file
                    shutil.move(str(dup), str(target_path))

                    moved.append({
                        "from": str(dup),
                        "to": str(target_path),
                        "size": target_path.stat().st_size,
                        "original": str(group.original)
                    })
                    logger.info(f"Moved duplicate: {dup} -> {target_path}")

                except Exception as e:
                    errors.append({
                        "file": str(dup),
                        "error": str(e)
                    })
                    logger.error(f"Failed to move {dup}: {e}")

    return {
        "dry_run": dry_run,
        "moved_count": len(moved),
        "moved": moved,
        "errors": errors,
        "target_folder": str(duplicates_dir),
        "space_recovered_bytes": sum(m["size"] for m in moved) if moved else 0
    }


def format_report(report: DuplicateReport) -> str:
    """Format a duplicate report as human-readable text"""
    lines = [
        f"Duplicate Detection Report",
        f"=" * 50,
        f"Project: {report.project_path.name}",
        f"Scan time: {report.scan_time:.2f}s",
        f"",
        f"Summary:",
        f"  Duplicate groups: {len(report.groups)}",
        f"  Total duplicates: {report.total_duplicates}",
        f"  Wasted space: {report.total_wasted_bytes / 1024 / 1024:.2f} MB",
        f"",
    ]

    if report.groups:
        lines.append("Duplicates found:")
        for i, group in enumerate(report.groups, 1):
            lines.append(f"")
            lines.append(f"  Group {i} ({len(group.files)} files, {group.total_size / 1024:.1f} KB):")
            lines.append(f"    KEEP: {group.original.name}")
            for dup in group.duplicates:
                lines.append(f"    MOVE: {dup.name}")
    else:
        lines.append("No duplicates found!")

    return "\n".join(lines)


# Convenience function for quick detection
def quick_detect(folder_path: str) -> Dict:
    """
    Quick duplicate detection for API use.

    Returns a dict suitable for JSON response.
    """
    report = detect_duplicates(Path(folder_path))

    return {
        "project": str(report.project_path),
        "duplicate_groups": len(report.groups),
        "total_duplicates": report.total_duplicates,
        "wasted_mb": round(report.total_wasted_bytes / 1024 / 1024, 2),
        "scan_seconds": round(report.scan_time, 2),
        "groups": [
            {
                "original": str(g.original),
                "duplicates": [str(d) for d in g.duplicates],
                "size_kb": round(g.total_size / 1024, 1)
            }
            for g in report.groups
        ]
    }
