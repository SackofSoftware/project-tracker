"""
Smart File Handler for MCP Server

Handles file uploads with:
- Duplicate detection via content hashing
- Smart file naming (suffix on collision with different content)
- Integration with ProjectSandbox for path validation
- Timeline event logging
"""

import os
import hashlib
import base64
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional, Tuple

from .sandbox import ProjectSandbox


class SmartFileHandler:
    """
    Handles file operations with smart duplicate detection and organization.

    Features:
    - Hash-based duplicate detection
    - Automatic suffix on content collision
    - Sandbox validation for all paths
    - No delete operations (read/write only)
    """

    def __init__(self, sandbox: ProjectSandbox, timeline_callback=None):
        """
        Initialize file handler with a project sandbox.

        Args:
            sandbox: ProjectSandbox instance for path validation
            timeline_callback: Optional callback for logging timeline events
                              Signature: callback(event_type, title, description, **kwargs)
        """
        self.sandbox = sandbox
        self.timeline_callback = timeline_callback

    def save_file(
        self,
        filename: str,
        content: bytes,
        content_type: str = None,
        force_overwrite: bool = False
    ) -> Dict:
        """
        Save a file with duplicate detection and smart naming.

        Args:
            filename: Name of the file to save
            content: File content as bytes
            content_type: Optional type hint (spec, drawing, quote, etc.)
            force_overwrite: If True, overwrite existing identical files

        Returns:
            Dict with status and details:
            {
                "status": "saved" | "duplicate" | "renamed" | "error",
                "message": "Human readable message",
                "saved_path": "Path where file was saved" (if saved/renamed),
                "existing_path": "Path of existing file" (if duplicate),
                "original_name": "Original filename" (if renamed),
                "new_name": "New filename" (if renamed)
            }
        """
        # Get target path from sandbox
        target_path = self.sandbox.get_target_path(filename, content_type)

        # Validate we can write here
        can_write, error = self.sandbox.can_write(target_path)
        if not can_write:
            return {
                "status": "error",
                "message": f"Cannot save file: {error}"
            }

        # Calculate hash of new content
        new_hash = self._hash_content(content)

        # Check for existing file
        if target_path.exists():
            existing_hash = self._hash_file(target_path)

            if existing_hash == new_hash:
                # Identical content
                if force_overwrite:
                    target_path.write_bytes(content)
                    return {
                        "status": "saved",
                        "message": f"File '{filename}' overwritten (identical content)",
                        "saved_path": str(target_path)
                    }
                else:
                    return {
                        "status": "duplicate",
                        "message": f"File '{filename}' is already present with identical content",
                        "existing_path": str(target_path)
                    }
            else:
                # Different content - add suffix
                new_filename = self._generate_unique_name(filename, target_path.parent)
                new_path = target_path.parent / new_filename

                # Ensure parent folder exists
                new_path.parent.mkdir(parents=True, exist_ok=True)
                new_path.write_bytes(content)

                # Log timeline event
                self._log_event(
                    "document_added",
                    f"File renamed and saved",
                    f"'{filename}' → '{new_filename}' (different content)",
                    related_file=str(new_path)
                )

                return {
                    "status": "renamed",
                    "message": f"File differs from existing. Saved as '{new_filename}'",
                    "saved_path": str(new_path),
                    "original_name": filename,
                    "new_name": new_filename
                }

        # New file - save directly
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_bytes(content)

        # Detect document type for logging
        doc_type = self._detect_doc_type(filename, content_type, target_path)

        # Log timeline event
        self._log_event(
            "document_added",
            f"{doc_type.title()} added",
            filename,
            related_file=str(target_path),
            tags=[doc_type]
        )

        return {
            "status": "saved",
            "message": f"File saved to {target_path.parent.name}/{filename}",
            "saved_path": str(target_path)
        }

    def save_file_base64(
        self,
        filename: str,
        content_base64: str,
        content_type: str = None
    ) -> Dict:
        """
        Save a file from base64-encoded content.

        Args:
            filename: Name of the file
            content_base64: Base64-encoded file content
            content_type: Optional type hint

        Returns:
            Same as save_file()
        """
        try:
            content = base64.b64decode(content_base64)
            return self.save_file(filename, content, content_type)
        except Exception as e:
            return {
                "status": "error",
                "message": f"Invalid base64 content: {str(e)}"
            }

    def check_file_exists(self, filename: str, content_type: str = None) -> Dict:
        """
        Check if a file already exists and get its status.

        Args:
            filename: Name of the file
            content_type: Optional type hint

        Returns:
            Dict with existence status and path
        """
        target_path = self.sandbox.get_target_path(filename, content_type)

        if target_path.exists():
            stat = target_path.stat()
            return {
                "exists": True,
                "path": str(target_path),
                "size": stat.st_size,
                "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                "hash": self._hash_file(target_path)
            }

        return {
            "exists": False,
            "suggested_path": str(target_path)
        }

    def compare_with_existing(
        self,
        filename: str,
        content: bytes,
        content_type: str = None
    ) -> Dict:
        """
        Compare new content with existing file.

        Args:
            filename: Name of the file
            content: New file content
            content_type: Optional type hint

        Returns:
            Dict with comparison result
        """
        target_path = self.sandbox.get_target_path(filename, content_type)

        if not target_path.exists():
            return {
                "exists": False,
                "message": "File does not exist yet"
            }

        existing_hash = self._hash_file(target_path)
        new_hash = self._hash_content(content)

        if existing_hash == new_hash:
            return {
                "exists": True,
                "identical": True,
                "message": "Content is identical to existing file",
                "path": str(target_path)
            }

        return {
            "exists": True,
            "identical": False,
            "message": "Content differs from existing file",
            "path": str(target_path),
            "existing_size": target_path.stat().st_size,
            "new_size": len(content)
        }

    def read_file(self, filepath: str) -> Tuple[Optional[bytes], str]:
        """
        Read a file from within the sandbox.

        Args:
            filepath: Path to the file (relative or absolute)

        Returns:
            Tuple of (content, error_message)
        """
        path = Path(filepath)
        if not path.is_absolute():
            path = self.sandbox.project_path / filepath

        # Validate path
        is_valid, error = self.sandbox.validate_path(path)
        if not is_valid:
            return None, error

        if not path.exists():
            return None, f"File not found: {filepath}"

        if not path.is_file():
            return None, f"Not a file: {filepath}"

        try:
            return path.read_bytes(), ""
        except Exception as e:
            return None, f"Error reading file: {str(e)}"

    def _hash_content(self, content: bytes) -> str:
        """Calculate MD5 hash of content."""
        return hashlib.md5(content).hexdigest()

    def _hash_file(self, filepath: Path) -> str:
        """Calculate MD5 hash of a file."""
        hasher = hashlib.md5()
        with open(filepath, 'rb') as f:
            for chunk in iter(lambda: f.read(65536), b''):
                hasher.update(chunk)
        return hasher.hexdigest()

    def _generate_unique_name(self, filename: str, folder: Path) -> str:
        """Generate a unique filename by adding timestamp suffix."""
        base, ext = os.path.splitext(filename)
        suffix = datetime.now().strftime("_%Y%m%d_%H%M%S")
        new_name = f"{base}{suffix}{ext}"

        # Ensure uniqueness (unlikely but possible)
        counter = 1
        while (folder / new_name).exists():
            new_name = f"{base}{suffix}_{counter}{ext}"
            counter += 1

        return new_name

    def _detect_doc_type(self, filename: str, content_type: str, path: Path) -> str:
        """Detect document type for logging."""
        if content_type:
            return content_type

        folder_name = path.parent.name.lower()
        type_map = {
            "specs": "spec",
            "drawings": "drawing",
            "addenda": "addendum",
            "quotes": "quote",
            "spreadsheets": "spreadsheet",
            "schedules": "schedule",
            "submittals": "submittal",
            "rfis": "rfi",
            "photos": "photo"
        }
        return type_map.get(folder_name, "document")

    def _log_event(self, event_type: str, title: str, description: str, **kwargs):
        """Log a timeline event if callback is configured."""
        if self.timeline_callback:
            try:
                self.timeline_callback(event_type, title, description, **kwargs)
            except Exception as e:
                print(f"Warning: Failed to log timeline event: {e}")


# Convenience function for creating handler with project context
def create_file_handler(project_id: str, project_path: str, timeline_callback=None) -> SmartFileHandler:
    """
    Create a SmartFileHandler for a project.

    Args:
        project_id: Project identifier
        project_path: Path to project folder
        timeline_callback: Optional timeline event callback

    Returns:
        Configured SmartFileHandler instance
    """
    sandbox = ProjectSandbox(project_id, Path(project_path))
    return SmartFileHandler(sandbox, timeline_callback)
