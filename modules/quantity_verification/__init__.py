"""
Quantity Verification Module

Provides tools for verifying quantities between schedules and drawings:
1. PatternLearner - AI extracts tag patterns from schedule PDFs
2. DrawingScanner - Scans floor plans + elevations for tag shapes
3. Highlighter - Generates highlighted PDFs showing counted items

Workflow:
1. Run PatternLearner on schedule PDFs to detect tag patterns (A, W1, etc.)
2. User confirms/edits detected patterns via UI
3. DrawingScanner scans floor plans + exterior elevations only
4. Highlighter generates PDFs with counted items marked
5. Compare schedule quantities vs drawing counts

Restrictions:
- Only scans floor plans (A1xx) and exterior elevations (A2xx, A3xx)
- Handles inconsistent tag formats (A, W1, WIN-A, Type 1, T-1, HM-1, etc.)
- Shape detection uses hexagon, circle, etc. patterns
"""

__version__ = "1.0.0"

from .pattern_learner import PatternLearner, TagPattern
from .drawing_scanner import DrawingScanner, ScanResult
from .highlighter import QuantityHighlighter

__all__ = [
    'PatternLearner',
    'TagPattern',
    'DrawingScanner',
    'ScanResult',
    'QuantityHighlighter',
]
