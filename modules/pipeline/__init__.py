"""
Master Analysis Pipeline for Project Tracker

Orchestrates document processing, AI analysis, and file organization
for construction project bidding documents.

Pipeline Stages:
1. RENAME - AI extracts project name from cover sheet
2. ORGANIZE - Move files into structured folders
3. SPLIT_SPECS - Split spec book by CSI section
4. SPLIT_DRAWINGS - Split drawing set by page
5. AI_ANALYSIS - Vision + text parsing of schedules
6. SCHEDULE_PARSE - Extract door/window/storefront data
7. HIGHLIGHT - Apply highlights to floor plans + exterior elevations
8. QUOTE_ANALYSIS - Identify and parse vendor quotes
"""

from .master_pipeline import MasterPipeline
from .ai_providers import AIProviderManager, GPT5NanoProvider, DeepSeekProvider

__all__ = [
    'MasterPipeline',
    'AIProviderManager',
    'GPT5NanoProvider',
    'DeepSeekProvider',
]
