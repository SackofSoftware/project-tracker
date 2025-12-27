"""
Project Sandbox for MCP Server

Provides path validation and file organization suggestions
to ensure the MCP server can only operate within the current project folder.
"""

import os
from pathlib import Path
from typing import Optional, List, Tuple


class ProjectSandbox:
    """
    Enforces project-level sandboxing for MCP operations.

    The sandbox ensures:
    - All file operations are within the project folder
    - Files are organized into appropriate subfolders
    - No operations outside the project boundary
    """

    # Standard subfolders for project organization
    STANDARD_FOLDERS = [
        "Specs",
        "Drawings",
        "Addenda",
        "Quotes",
        "Spreadsheets",
        "Schedules",
        "Submittals",
        "RFIs",
        "Photos",
        "Other"
    ]

    # File type to folder mapping
    FILE_TYPE_MAPPING = {
        # By extension
        ".xlsx": "Spreadsheets",
        ".xls": "Spreadsheets",
        ".csv": "Spreadsheets",
        ".pdf": None,  # Determined by content/name
        ".dwg": "Drawings",
        ".dxf": "Drawings",
        ".rvt": "Drawings",
        ".jpg": "Photos",
        ".jpeg": "Photos",
        ".png": "Photos",
        ".heic": "Photos",
    }

    # Filename patterns for classification
    FILENAME_PATTERNS = {
        "addendum": "Addenda",
        "addenda": "Addenda",
        "add_": "Addenda",
        "quote": "Quotes",
        "proposal": "Quotes",
        "bid": "Quotes",
        "schedule": "Schedules",
        "submittal": "Submittals",
        "rfi": "RFIs",
        "08 ": "Specs",  # CSI section prefix
        "08_": "Specs",
    }

    # Sheet number patterns for drawings
    DRAWING_PREFIXES = ["A", "S", "M", "E", "P", "L", "C", "G", "T", "D"]

    def __init__(self, project_id: str, project_path: Path):
        """
        Initialize sandbox for a specific project.

        Args:
            project_id: Project identifier
            project_path: Path to the project folder
        """
        self.project_id = project_id
        self.project_path = Path(project_path).resolve()

        # Build allowed paths list
        self.allowed_paths = [self.project_path]
        for folder in self.STANDARD_FOLDERS:
            self.allowed_paths.append(self.project_path / folder)

    def validate_path(self, path: Path) -> Tuple[bool, str]:
        """
        Validate that a path is within the project sandbox.

        Args:
            path: Path to validate

        Returns:
            Tuple of (is_valid, error_message)
        """
        try:
            resolved = Path(path).resolve()

            # Check if path is within project folder
            if not self._is_within_project(resolved):
                return False, f"Path '{path}' is outside project sandbox"

            return True, ""

        except Exception as e:
            return False, f"Invalid path: {str(e)}"

    def _is_within_project(self, path: Path) -> bool:
        """Check if a path is within the project folder."""
        try:
            path.relative_to(self.project_path)
            return True
        except ValueError:
            return False

    def suggest_organization(self, filename: str, content_type: str = None) -> Path:
        """
        Suggest the appropriate folder for a file based on its name and type.

        Args:
            filename: Name of the file
            content_type: Optional content type hint (spec, drawing, quote, etc.)

        Returns:
            Suggested folder path within the project
        """
        filename_lower = filename.lower()
        ext = Path(filename).suffix.lower()

        # 1. Check explicit content type
        if content_type:
            type_mapping = {
                "spec": "Specs",
                "specification": "Specs",
                "drawing": "Drawings",
                "addendum": "Addenda",
                "quote": "Quotes",
                "proposal": "Quotes",
                "spreadsheet": "Spreadsheets",
                "schedule": "Schedules",
                "submittal": "Submittals",
                "rfi": "RFIs",
                "photo": "Photos",
            }
            folder = type_mapping.get(content_type.lower())
            if folder:
                return self.project_path / folder

        # 2. Check extension mapping
        folder = self.FILE_TYPE_MAPPING.get(ext)
        if folder:
            return self.project_path / folder

        # 3. Check filename patterns
        for pattern, folder in self.FILENAME_PATTERNS.items():
            if pattern in filename_lower:
                return self.project_path / folder

        # 4. Check if looks like a spec section (e.g., "08 51 13.pdf")
        if filename[:2].isdigit() and ext == ".pdf":
            return self.project_path / "Specs"

        # 5. Check if looks like a drawing sheet (e.g., "A101.pdf", "S201.pdf")
        if filename[0].upper() in self.DRAWING_PREFIXES and ext == ".pdf":
            # Further check: second char is digit
            if len(filename) > 1 and filename[1].isdigit():
                return self.project_path / "Drawings"

        # 6. Default to Other
        return self.project_path / "Other"

    def ensure_folder_exists(self, folder: Path) -> bool:
        """
        Ensure a folder exists within the sandbox.

        Args:
            folder: Folder path to create

        Returns:
            True if folder exists or was created
        """
        is_valid, error = self.validate_path(folder)
        if not is_valid:
            return False

        try:
            folder.mkdir(parents=True, exist_ok=True)
            return True
        except Exception:
            return False

    def list_files(self, folder: str = None, pattern: str = "*.pdf") -> List[Path]:
        """
        List files in the project folder.

        Args:
            folder: Optional subfolder to list
            pattern: Glob pattern for files

        Returns:
            List of file paths
        """
        base = self.project_path
        if folder:
            base = self.project_path / folder
            is_valid, _ = self.validate_path(base)
            if not is_valid:
                return []

        if not base.exists():
            return []

        return list(base.glob(pattern))

    def get_folder_structure(self) -> dict:
        """
        Get the current folder structure of the project.

        Returns:
            Dict with folder names and file counts
        """
        structure = {}

        for folder_name in self.STANDARD_FOLDERS:
            folder_path = self.project_path / folder_name
            if folder_path.exists():
                files = list(folder_path.glob("*"))
                structure[folder_name] = {
                    "exists": True,
                    "file_count": len([f for f in files if f.is_file()]),
                    "path": str(folder_path)
                }
            else:
                structure[folder_name] = {
                    "exists": False,
                    "file_count": 0,
                    "path": str(folder_path)
                }

        # Also count files in root
        root_files = [f for f in self.project_path.glob("*") if f.is_file()]
        structure["_root"] = {
            "exists": True,
            "file_count": len(root_files),
            "path": str(self.project_path)
        }

        return structure

    def get_target_path(self, filename: str, content_type: str = None) -> Path:
        """
        Get the full target path for saving a file.

        Args:
            filename: Name of the file
            content_type: Optional content type hint

        Returns:
            Full path where file should be saved
        """
        folder = self.suggest_organization(filename, content_type)
        return folder / filename

    def can_write(self, path: Path) -> Tuple[bool, str]:
        """
        Check if we can write to a path (validation + permissions).

        Args:
            path: Path to check

        Returns:
            Tuple of (can_write, reason)
        """
        is_valid, error = self.validate_path(path)
        if not is_valid:
            return False, error

        # Check parent folder exists or can be created
        parent = path.parent
        if not parent.exists():
            try:
                parent.mkdir(parents=True, exist_ok=True)
            except Exception as e:
                return False, f"Cannot create folder: {str(e)}"

        # Check write permissions on parent
        if not os.access(parent, os.W_OK):
            return False, f"No write permission for folder: {parent}"

        return True, ""

    def __repr__(self):
        return f"ProjectSandbox(project_id='{self.project_id}', path='{self.project_path}')"
