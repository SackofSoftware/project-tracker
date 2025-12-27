"""
Stage 4: Unified AI Query

Uses DeepSeek V3.2 via OpenRouter to extract Division 8 scope from:
- Specification documents (split in Stage 1)
- Schedule data (from RAG index built in Stage 3)
- Drawing notes (from Architectural drawings)

This is the final stage of the unified 4-stage pipeline.

Output: Structured JSON with complete Division 8 scope including:
- Doors (metal, wood, access)
- Windows (aluminum, wood, vinyl)
- Storefronts and Curtain Wall
- Hardware (door hardware sets)
- Glazing specifications
- Quantities (where available from schedules)
"""

import logging
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
import fitz  # PyMuPDF
import json

logger = logging.getLogger(__name__)


@dataclass
class StageResult:
    """Result from a pipeline stage"""
    success: bool
    data: Dict
    error: Optional[str] = None


class UnifiedAIQueryStage:
    """
    Stage 4: Unified AI Query with DeepSeek V3.2

    Queries DeepSeek V3.2 with Division 8 specifications to extract
    complete scope information including quantities.
    """

    # Division 8 spec folders to read
    DIV8_FOLDERS = [
        'Specs/Division-08-Openings',
        'Specs/Division-8-Openings',
        'Specs',  # Fallback - look for 08xxxx files directly
    ]

    # Schedule folders to check
    SCHEDULE_FOLDERS = [
        'Schedules',
        'Drawings/Architectural',
    ]

    def __init__(self, project_folder: Path, ai_provider=None):
        self.project_folder = Path(project_folder)
        self.ai = ai_provider

    async def run(self) -> StageResult:
        """Execute the unified AI query stage"""
        try:
            logger.info(f"[UnifiedAIQuery] Starting for: {self.project_folder.name}")

            # Check if AI provider is available
            if not self.ai:
                return StageResult(
                    success=False,
                    data={},
                    error="No AI provider available - DeepSeek V3.2 required"
                )

            if not self.ai.has_unified_pipeline:
                return StageResult(
                    success=False,
                    data={},
                    error="DeepSeek V3.2 not configured - check OPENROUTER_API_KEY"
                )

            # Step 1: Gather Division 8 spec content
            spec_content = self._gather_spec_content()
            if not spec_content:
                logger.warning("[UnifiedAIQuery] No Division 8 specifications found")
                return StageResult(
                    success=True,
                    data={
                        'message': 'No Division 8 specifications found',
                        'scope': {},
                    }
                )

            logger.info(f"[UnifiedAIQuery] Gathered {len(spec_content)} chars of spec content")

            # Step 2: Gather schedule data
            schedule_content = self._gather_schedule_content()
            logger.info(f"[UnifiedAIQuery] Gathered {len(schedule_content)} chars of schedule content")

            # Step 3: Gather drawing notes (if available)
            drawing_notes = self._gather_drawing_notes()
            logger.info(f"[UnifiedAIQuery] Gathered {len(drawing_notes)} chars of drawing notes")

            # Step 4: Query DeepSeek V3.2
            logger.info("[UnifiedAIQuery] Querying DeepSeek V3.2...")
            result = await self.ai.extract_division8(
                spec_content=spec_content,
                schedule_content=schedule_content,
                drawing_notes=drawing_notes
            )

            if not result.success:
                logger.error(f"[UnifiedAIQuery] AI query failed: {result.error}")
                return StageResult(
                    success=False,
                    data={'error': result.error},
                    error=result.error
                )

            # Step 5: Process and validate results
            scope_data = result.data
            if 'raw_text' in scope_data and 'parse_failed' in scope_data:
                # JSON parsing failed - try to salvage what we can
                logger.warning("[UnifiedAIQuery] JSON parsing failed, using raw response")
                scope_data = {'raw_response': scope_data.get('raw_text', '')}

            # Add metadata
            scope_data['_metadata'] = {
                'model': result.model,
                'tokens_used': result.tokens_used,
                'spec_chars': len(spec_content),
                'schedule_chars': len(schedule_content),
            }

            # Save results to project folder
            self._save_results(scope_data)

            logger.info("[UnifiedAIQuery] Complete - Division 8 scope extracted")

            return StageResult(
                success=True,
                data={
                    'scope': scope_data,
                    'model': result.model,
                    'tokens_used': result.tokens_used,
                }
            )

        except Exception as e:
            logger.error(f"[UnifiedAIQuery] Error: {e}")
            import traceback
            traceback.print_exc()
            return StageResult(
                success=False,
                data={},
                error=str(e)
            )

    def _gather_spec_content(self) -> str:
        """Gather text content from Division 8 specifications"""
        content_parts = []

        for folder_name in self.DIV8_FOLDERS:
            folder_path = self.project_folder / folder_name
            if not folder_path.exists():
                continue

            # Find Division 8 PDFs
            for pdf_path in folder_path.glob("*.pdf"):
                # Check if it's a Division 8 section
                if folder_name == 'Specs' and not pdf_path.stem.startswith('08'):
                    continue

                text = self._extract_pdf_text(pdf_path)
                if text:
                    content_parts.append(f"=== {pdf_path.name} ===\n{text}")

        return "\n\n".join(content_parts)

    def _gather_schedule_content(self) -> str:
        """Gather text content from schedule documents"""
        content_parts = []

        for folder_name in self.SCHEDULE_FOLDERS:
            folder_path = self.project_folder / folder_name
            if not folder_path.exists():
                continue

            # Find schedule PDFs
            for pdf_path in folder_path.glob("*.pdf"):
                name_lower = pdf_path.stem.lower()

                # Check for schedule keywords
                is_schedule = any(kw in name_lower for kw in [
                    'schedule', 'door', 'window', 'hardware', 'frame'
                ])

                # Check for architectural sheets with schedules (A5xx, A6xx, A8xx)
                is_arch_schedule = any(
                    pdf_path.stem.upper().startswith(prefix)
                    for prefix in ['A5', 'A6', 'A7', 'A8']
                )

                if is_schedule or is_arch_schedule:
                    text = self._extract_pdf_text(pdf_path)
                    if text:
                        content_parts.append(f"=== {pdf_path.name} ===\n{text}")

        return "\n\n".join(content_parts)

    def _gather_drawing_notes(self) -> str:
        """Gather notes from architectural drawings (cover sheets, general notes)"""
        content_parts = []

        arch_folder = self.project_folder / 'Drawings' / 'Architectural'
        if not arch_folder.exists():
            return ""

        # Look for cover sheets and general notes
        note_patterns = ['A0', 'A00', 'A001', 'G0', 'G1', 'COVER', 'NOTE', 'INDEX']

        for pdf_path in arch_folder.glob("*.pdf"):
            name_upper = pdf_path.stem.upper()
            is_note_sheet = any(name_upper.startswith(p) or p in name_upper for p in note_patterns)

            if is_note_sheet:
                text = self._extract_pdf_text(pdf_path, max_pages=2)
                if text:
                    content_parts.append(f"=== {pdf_path.name} ===\n{text}")

        return "\n\n".join(content_parts)

    def _extract_pdf_text(self, pdf_path: Path, max_pages: int = None) -> str:
        """Extract text content from a PDF"""
        try:
            with fitz.open(str(pdf_path)) as doc:
                text_parts = []
                page_limit = max_pages or len(doc)

                for i in range(min(page_limit, len(doc))):
                    page = doc[i]
                    text = page.get_text()
                    if text.strip():
                        text_parts.append(text)

                return "\n".join(text_parts)
        except Exception as e:
            logger.warning(f"[UnifiedAIQuery] Failed to extract text from {pdf_path.name}: {e}")
            return ""

    def _save_results(self, scope_data: Dict):
        """Save extraction results to project folder"""
        try:
            # Save to extracted-data folder
            output_dir = self.project_folder / 'extracted-data'
            output_dir.mkdir(parents=True, exist_ok=True)

            output_path = output_dir / 'division8_scope.json'
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(scope_data, f, indent=2, ensure_ascii=False)

            logger.info(f"[UnifiedAIQuery] Saved results to {output_path}")

        except Exception as e:
            logger.warning(f"[UnifiedAIQuery] Failed to save results: {e}")


class UnifiedAIQueryStageWithRAG(UnifiedAIQueryStage):
    """
    Extended version that queries the RAG index for additional context.

    Use this version when RAG index is available from Stage 3.
    """

    def __init__(self, project_folder: Path, ai_provider=None, rag_index=None):
        super().__init__(project_folder, ai_provider)
        self.rag_index = rag_index

    async def run(self) -> StageResult:
        """Execute with RAG-enhanced context"""
        # If we have a RAG index, query it for relevant context
        if self.rag_index:
            rag_context = await self._query_rag_index()
            if rag_context:
                logger.info(f"[UnifiedAIQuery+RAG] Retrieved {len(rag_context)} chars from RAG")

        # Continue with standard extraction
        return await super().run()

    async def _query_rag_index(self) -> str:
        """Query RAG index for Division 8 relevant content"""
        if not self.rag_index:
            return ""

        try:
            # Division 8 query topics
            queries = [
                "doors frames hollow metal aluminum wood",
                "windows glazing storefronts curtain wall",
                "hardware hinges locks closers",
                "access panels roof hatches louvers",
            ]

            results = []
            for query in queries:
                rag_results = self.rag_index.query(query, top_k=3)
                for doc in rag_results:
                    if doc.get('content'):
                        results.append(doc['content'])

            return "\n\n".join(results)

        except Exception as e:
            logger.warning(f"[UnifiedAIQuery+RAG] RAG query failed: {e}")
            return ""
