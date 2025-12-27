"""
Pipeline Stages

Each stage is independently runnable and trackable.

Two pipeline modes available:
1. STAGE_ORDER - Legacy 9-stage pipeline (for backwards compatibility)
2. UNIFIED_STAGE_ORDER - New 4-stage unified pipeline (recommended)
"""

# Legacy stages
from .stage_rename import RenameStage
from .stage_organize import OrganizeStage
from .stage_split_specs import SplitSpecsStage
from .stage_split_drawings import SplitDrawingsStage
from .stage_rag_analysis import RAGAnalysisStage
from .stage_ai_analysis import AIAnalysisStage
from .stage_schedule_parse import ScheduleParseStage
from .stage_highlight import HighlightStage
from .stage_quotes import QuoteAnalysisStage

# New unified stages
from .stage_unified_id_split import UnifiedIDSplitStage
from .stage_unified_ai_query import UnifiedAIQueryStage, UnifiedAIQueryStageWithRAG


# Legacy stage execution order (8 stages)
# Kept for backwards compatibility with existing API routes
# NOTE: 'rename' stage removed to prevent folder renaming which breaks source links
STAGE_ORDER = [
    ('organize', OrganizeStage),
    ('split_specs', SplitSpecsStage),
    ('split_drawings', SplitDrawingsStage),
    ('rag_analysis', RAGAnalysisStage),
    ('ai_analysis', AIAnalysisStage),
    ('schedule_parse', ScheduleParseStage),
    ('highlight', HighlightStage),
    ('quotes', QuoteAnalysisStage),
]


# New unified stage execution order (4 stages)
# Simplified pipeline with DeepSeek V3.2 for Division 8 extraction
#
# Stage 1: ID & Split
#   - Identify spec book vs drawing set
#   - Split spec book into CSI section PDFs (Div 00, 01, 08)
#   - Split drawing set into individual sheets by discipline
#
# Stage 2: Organize
#   - Move ALL files to proper folders (Specs/, Drawings/, Quotes/, Addenda/)
#   - Auto-rename files with standardized names
#
# Stage 3: RAG Build
#   - Build vector index from Division 8 specs ONLY
#   - Index architectural drawings (A-* prefix)
#   - Store in project-local ChromaDB
#
# Stage 4: AI Query (DeepSeek V3.2)
#   - Query for Division 8 scopes using deepseek/deepseek-v3.2
#   - Extract: windows, doors, storefront, curtain wall, hardware, glazing
#   - Include quantities where available from schedules
#
UNIFIED_STAGE_ORDER = [
    ('id_split', UnifiedIDSplitStage),
    ('organize', OrganizeStage),
    ('rag_build', RAGAnalysisStage),
    ('ai_query', UnifiedAIQueryStage),
]


__all__ = [
    # Legacy stages
    'RenameStage',
    'OrganizeStage',
    'SplitSpecsStage',
    'SplitDrawingsStage',
    'RAGAnalysisStage',
    'AIAnalysisStage',
    'ScheduleParseStage',
    'HighlightStage',
    'QuoteAnalysisStage',
    # Unified stages
    'UnifiedIDSplitStage',
    'UnifiedAIQueryStage',
    'UnifiedAIQueryStageWithRAG',
    # Stage orders
    'STAGE_ORDER',
    'UNIFIED_STAGE_ORDER',
]
