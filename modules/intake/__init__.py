"""
Project Intake Module

Handles intelligent intake of new project folders:
- Email parsing (.eml files) with LLM extraction
- File classification (drawing sets, spec books, addenda)
- Project metadata extraction
"""

from .email_parser import EmailParser

# FileClassifier imported when available
try:
    from .file_classifier import FileClassifier
    __all__ = ['EmailParser', 'FileClassifier']
except ImportError:
    __all__ = ['EmailParser']
