"""
Schema Module

Unified data schemas for cross-source project management.
"""

from .unified_project import (
    UnifiedProject,
    Location,
    Document,
    Division8Scope,
    LinkedSource,
    InternalStatus,
    normalize_date,
    normalize_project_value,
    merge_division_8_scopes,
)

__all__ = [
    'UnifiedProject',
    'Location',
    'Document',
    'Division8Scope',
    'LinkedSource',
    'InternalStatus',
    'normalize_date',
    'normalize_project_value',
    'merge_division_8_scopes',
]
