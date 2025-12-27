"""
MCP Server for Project Tracker

Enables Claude Code to manage projects programmatically with RESTRICTED access.

RESTRICTIONS:
- Model: ONLY callable by Claude Haiku 4.5
- Scope: Project data ONLY - NO GUI/template/route modifications
- Operations: Read/write project records, link emails, query data

Available Tools:
- project.list - List projects with filtering
- project.get - Get single project details
- project.create - Create new project record
- project.update - Update project fields
- project.archive - Archive a project
- project.transition - Change project lifecycle (B->A, L->B, etc.)
- email.list - List emails from Email Monitor
- email.link - Link email to project
- email.unlink - Unlink email from project
- govlead.list - List government leads
- govlead.convert - Convert lead to project
- query.search - Search across all data sources

Project Sandbox & File Handling:
- sandbox.py - ProjectSandbox for path validation and file organization
- file_handler.py - SmartFileHandler with duplicate detection
- openrouter_delegate.py - OpenRouter delegation for bulk analysis
"""

__version__ = "1.0.0"

from .sandbox import ProjectSandbox
from .file_handler import SmartFileHandler, create_file_handler
from .openrouter_delegate import OpenRouterDelegate, get_delegate, quick_analyze

__all__ = [
    'ProjectSandbox',
    'SmartFileHandler',
    'create_file_handler',
    'OpenRouterDelegate',
    'get_delegate',
    'quick_analyze'
]
