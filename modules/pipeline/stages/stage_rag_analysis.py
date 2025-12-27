"""
Stage 5: RAG Analysis

Runs Division 8 RAG (Retrieval Augmented Generation) analysis AFTER
spec book and drawing splitting has completed.

Uses selective indexing to only process:
- Division 8 specs from Specs/Division-08-Openings/
- Architectural drawings (A-*, G-*) from Drawings/

This dramatically reduces processing time and improves relevance.
"""

import os
from pathlib import Path
from typing import Dict, Optional
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)


@dataclass
class StageResult:
    """Result from a pipeline stage"""
    success: bool
    data: Dict
    error: Optional[str] = None


class RAGAnalysisStage:
    """
    Stage 5: RAG Analysis (runs after split stages)

    Performs Division 8 scope extraction using RAG with selective indexing.
    Only indexes relevant documents (Div 8 specs + architectural drawings)
    for faster processing and better results.
    """

    def __init__(self, project_folder: Path):
        self.project_folder = Path(project_folder)
        self.project_name = self.project_folder.name
        self.output_file = self.project_folder / 'division8_rag_analysis.json'

    def check_prerequisites(self) -> tuple[bool, str]:
        """
        Check if split stages have run.

        Returns (ready, message).
        """
        # Check for split spec book
        div8_specs = self.project_folder / 'Specs' / 'Division-08-Openings'
        has_specs = div8_specs.exists() and any(div8_specs.glob('*.pdf'))

        # Check for split drawings
        drawings_folder = self.project_folder / 'Drawings'
        has_drawings = drawings_folder.exists() and any(drawings_folder.glob('*.pdf'))

        # Also check alternative locations
        if not has_specs:
            alt_specs = self.project_folder / 'Extracted-Data' / 'Organized' / 'Specs' / 'Division-08-Openings'
            has_specs = alt_specs.exists() and any(alt_specs.glob('*.pdf'))

        if not has_drawings:
            alt_drawings = self.project_folder / 'Extracted-Data' / 'Organized' / 'Drawings'
            has_drawings = alt_drawings.exists() and any(alt_drawings.glob('*.pdf'))

        if has_specs or has_drawings:
            return True, f"Found split documents (specs: {has_specs}, drawings: {has_drawings})"
        else:
            return False, "No split documents found. Run split_specs and split_drawings first."

    async def run(self) -> StageResult:
        """Run RAG analysis stage."""
        logger.info(f"[RAG Stage] Starting for: {self.project_name}")

        # Check prerequisites
        ready, message = self.check_prerequisites()
        if not ready:
            logger.warning(f"[RAG Stage] {message}")
            # Don't fail - just warn and skip
            return StageResult(
                success=True,
                data={
                    'skipped': True,
                    'reason': message,
                    'action': 'Run split_specs and split_drawings stages first'
                }
            )

        # Check for existing analysis
        if self.output_file.exists():
            logger.info(f"[RAG Stage] Analysis already exists, will overwrite")

        # Check for OpenAI API key
        openai_key = os.getenv('OPENAI_API_KEY')
        if not openai_key:
            return StageResult(
                success=False,
                data={},
                error="OPENAI_API_KEY not set"
            )

        # Try to run RAG analysis
        try:
            from modules.rag.division8_rag_local import analyze_project_selective

            logger.info(f"[RAG Stage] Running selective RAG analysis...")
            results = analyze_project_selective(self.project_folder, openai_key)

            if 'error' in results:
                return StageResult(
                    success=False,
                    data=results,
                    error=results['error']
                )

            # Extract summary stats
            metadata = results.get('_rag_metadata', {})

            logger.info(f"[RAG Stage] Complete - {metadata.get('chunks_analyzed', 0)} chunks analyzed")

            return StageResult(
                success=True,
                data={
                    'output_file': str(self.output_file),
                    'chunks_analyzed': metadata.get('chunks_analyzed', 0),
                    'chunks_retrieved': metadata.get('chunks_retrieved', 0),
                    'indexing_mode': metadata.get('indexing_mode', 'unknown'),
                    'analyzed_at': metadata.get('analyzed_at'),
                    'scope_summary': results.get('scope_summary', '')[:200]
                }
            )

        except ImportError as e:
            return StageResult(
                success=False,
                data={},
                error=f"RAG module not available: {e}"
            )
        except Exception as e:
            logger.exception(f"[RAG Stage] Error: {e}")
            return StageResult(
                success=False,
                data={},
                error=str(e)
            )


def create_stage(project_folder: Path) -> RAGAnalysisStage:
    """Factory function to create stage instance."""
    return RAGAnalysisStage(project_folder)
