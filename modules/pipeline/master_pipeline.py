"""
Master Pipeline Orchestrator

Two pipeline modes available:

LEGACY PIPELINE (9 stages):
1. RenameStage - Extract and rename using AI
2. OrganizeStage - Structure files into folders
3. SplitSpecsStage - Split spec book by CSI section
4. SplitDrawingsStage - Split drawings by page
5. RAGAnalysisStage - Build vector index
6. AIAnalysisStage - AI analysis of schedules
7. ScheduleParseStage - Parse AI results
8. HighlightStage - Highlight floor plans and elevations
9. QuoteAnalysisStage - Extract and parse vendor quotes

UNIFIED PIPELINE (4 stages) - RECOMMENDED:
1. UnifiedIDSplitStage - Identify and split specs + drawings
2. OrganizeStage - Structure files into folders
3. RAGAnalysisStage - Build vector index (Division 8 only)
4. UnifiedAIQueryStage - DeepSeek V3.2 scope extraction

Tracks progress via project_status.json for UI polling.
Handles errors gracefully and supports full/partial runs.
"""

from pathlib import Path
from typing import Dict, Optional, List, Tuple
import asyncio
import logging
from datetime import datetime

from .ai_providers import AIProviderManager
from .stages import (
    # Legacy stages
    RenameStage, OrganizeStage, SplitSpecsStage, SplitDrawingsStage,
    AIAnalysisStage, ScheduleParseStage, HighlightStage, QuoteAnalysisStage,
    RAGAnalysisStage,
    STAGE_ORDER,
    # Unified stages
    UnifiedIDSplitStage, UnifiedAIQueryStage,
    UNIFIED_STAGE_ORDER,
)
from ..tracking.project_status import ProjectStatusTracker

logger = logging.getLogger(__name__)


class PipelineError(Exception):
    """Pipeline execution error"""
    pass


class MasterPipeline:
    """
    Master pipeline orchestrator for construction project analysis.

    Manages execution of all 8 pipeline stages with progress tracking,
    error handling, and support for full or partial runs.
    """

    def __init__(
        self,
        project_folder: Path,
        status_tracker: ProjectStatusTracker = None,
        openai_key: str = None,
        openrouter_key: str = None
    ):
        """
        Initialize the master pipeline.

        Args:
            project_folder: Path to project folder to process
            status_tracker: Optional ProjectStatusTracker instance
            openai_key: Optional OpenAI API key (for GPT-5 nano vision)
            openrouter_key: Optional OpenRouter API key (for DeepSeek reasoning)
        """
        self.project_folder = Path(project_folder)
        self.project_id = self.project_folder.name

        # Initialize AI provider manager
        import os
        if openai_key:
            os.environ["OPENAI_API_KEY"] = openai_key
        if openrouter_key:
            os.environ["OPENROUTER_API_KEY"] = openrouter_key

        self.ai = AIProviderManager()

        # Initialize status tracker
        if status_tracker is None:
            # Default to static/data directory
            data_dir = Path(__file__).parent.parent.parent / "static" / "data"
            self.status_tracker = ProjectStatusTracker(str(data_dir))
        else:
            self.status_tracker = status_tracker

        # Current run state
        self.current_stage = None
        self.current_stage_index = 0
        self.errors = []
        self.start_time = None
        self.end_time = None

        # Progress callback for external status updates (used by routes/pipeline.py)
        self.progress_callback = None

        # Stage mappings
        self.stages = {name: cls for name, cls in STAGE_ORDER}
        self.unified_stages = {name: cls for name, cls in UNIFIED_STAGE_ORDER}

        logger.info(f"[MasterPipeline] Initialized for project: {self.project_id}")
        logger.info(f"  Vision available: {self.ai.has_vision}")
        logger.info(f"  Reasoning available: {self.ai.has_reasoning}")
        logger.info(f"  Unified pipeline available: {self.ai.has_unified_pipeline}")

    def set_progress_callback(self, callback):
        """
        Set a callback function for progress updates.

        The callback will be called with (stage_name, stage_status, message)
        to report progress to external systems (like the UI).

        Args:
            callback: Function taking (stage_name, stage_status_dict, message_str)
        """
        self.progress_callback = callback

    def _notify_progress(self, stage_name: str, stage_status: Dict, message: str = None):
        """Notify progress callback if set."""
        if self.progress_callback:
            try:
                self.progress_callback(stage_name, stage_status, message)
            except Exception as e:
                logger.warning(f"Progress callback error: {e}")

    async def run_full_pipeline(
        self,
        mode: str = 'manual',
        stop_on_error: bool = False
    ) -> Dict:
        """
        Run all 8 pipeline stages in sequence.

        Args:
            mode: 'manual' or 'auto' - how the pipeline was triggered
            stop_on_error: If True, stop pipeline on first error; if False, continue

        Returns:
            Dict with pipeline results:
            {
                'success': bool,
                'completed_stages': List[str],
                'failed_stages': List[str],
                'errors': List[Dict],
                'duration_seconds': float,
                'ai_usage': Dict
            }
        """
        self.start_time = datetime.now()
        logger.info(f"[MasterPipeline] Starting full pipeline run (mode={mode})")

        # Initialize pipeline run in status tracker
        self.status_tracker.start_pipeline_run(self.project_id, mode=mode)

        completed_stages = []
        failed_stages = []
        self.errors = []

        # Run each stage in order
        for idx, (stage_name, stage_class) in enumerate(STAGE_ORDER):
            self.current_stage = stage_name
            self.current_stage_index = idx

            logger.info(f"[MasterPipeline] Stage {idx+1}/8: {stage_name}")

            # Notify progress: stage starting
            self._notify_progress(stage_name, {'running': True}, f"Starting {stage_name}")

            try:
                result = await self._execute_stage(stage_name, stage_class)

                if result['success']:
                    completed_stages.append(stage_name)
                    logger.info(f"[MasterPipeline] ✓ Stage {stage_name} completed")
                    # Notify progress: stage completed
                    self._notify_progress(stage_name, {'completed': True, 'data': result.get('data', {})}, f"{stage_name} completed")
                else:
                    failed_stages.append(stage_name)
                    error_msg = result.get('error', 'Unknown error')
                    logger.error(f"[MasterPipeline] ✗ Stage {stage_name} failed: {error_msg}")
                    # Notify progress: stage failed
                    self._notify_progress(stage_name, {'completed': False, 'error': error_msg}, f"{stage_name} failed")

                    if stop_on_error:
                        logger.error(f"[MasterPipeline] Stopping pipeline due to error")
                        break

            except Exception as e:
                failed_stages.append(stage_name)
                error_msg = str(e)
                logger.error(f"[MasterPipeline] ✗ Stage {stage_name} exception: {error_msg}")

                # Notify progress: stage exception
                self._notify_progress(stage_name, {'completed': False, 'error': error_msg}, f"{stage_name} exception")

                # Update status tracker with error
                self.status_tracker.update_pipeline_stage(
                    self.project_id,
                    stage_name,
                    completed=False,
                    error=error_msg
                )

                if stop_on_error:
                    logger.error(f"[MasterPipeline] Stopping pipeline due to exception")
                    break

        self.end_time = datetime.now()
        duration = (self.end_time - self.start_time).total_seconds()

        # Get AI usage stats
        ai_usage = self.ai.get_usage_report()

        success = len(failed_stages) == 0

        logger.info(f"[MasterPipeline] Pipeline completed in {duration:.1f}s")
        logger.info(f"  Completed: {len(completed_stages)}/8")
        logger.info(f"  Failed: {len(failed_stages)}/8")
        logger.info(f"  AI cost estimate: ${ai_usage.get('total_estimated_cost', 0):.4f}")

        return {
            'success': success,
            'completed_stages': completed_stages,
            'failed_stages': failed_stages,
            'errors': self.errors,
            'duration_seconds': duration,
            'ai_usage': ai_usage,
            'project_id': self.project_id,
            'project_folder': str(self.project_folder),
            'completed_at': self.end_time.isoformat() if self.end_time else None
        }

    async def run_unified_pipeline(
        self,
        mode: str = 'manual',
        stop_on_error: bool = False
    ) -> Dict:
        """
        Run the unified 4-stage pipeline (RECOMMENDED).

        Stages:
        1. ID & Split - Identify and split spec book + drawing set
        2. Organize - Move files to proper folders
        3. RAG Build - Build vector index from Division 8 specs
        4. AI Query - DeepSeek V3.2 scope extraction

        Args:
            mode: 'manual' or 'auto' - how the pipeline was triggered
            stop_on_error: If True, stop pipeline on first error

        Returns:
            Dict with pipeline results
        """
        self.start_time = datetime.now()
        total_stages = len(UNIFIED_STAGE_ORDER)
        logger.info(f"[MasterPipeline] Starting unified pipeline ({total_stages} stages, mode={mode})")

        # Check if DeepSeek V3.2 is available
        if not self.ai.has_unified_pipeline:
            logger.warning("[MasterPipeline] DeepSeek V3.2 not available - unified pipeline may have limited functionality")

        # Initialize pipeline run in status tracker
        self.status_tracker.start_pipeline_run(self.project_id, mode=mode)

        completed_stages = []
        failed_stages = []
        self.errors = []

        # Run each unified stage in order
        for idx, (stage_name, stage_class) in enumerate(UNIFIED_STAGE_ORDER):
            self.current_stage = stage_name
            self.current_stage_index = idx

            logger.info(f"[MasterPipeline] Stage {idx+1}/{total_stages}: {stage_name}")

            # Notify progress: stage starting
            self._notify_progress(stage_name, {'running': True}, f"Starting {stage_name}")

            try:
                result = await self._execute_unified_stage(stage_name, stage_class)

                if result['success']:
                    completed_stages.append(stage_name)
                    logger.info(f"[MasterPipeline] ✓ Stage {stage_name} completed")
                    self._notify_progress(stage_name, {'completed': True, 'data': result.get('data', {})}, f"{stage_name} completed")
                else:
                    failed_stages.append(stage_name)
                    error_msg = result.get('error', 'Unknown error')
                    logger.error(f"[MasterPipeline] ✗ Stage {stage_name} failed: {error_msg}")
                    self._notify_progress(stage_name, {'completed': False, 'error': error_msg}, f"{stage_name} failed")

                    if stop_on_error:
                        logger.error(f"[MasterPipeline] Stopping unified pipeline due to error")
                        break

            except Exception as e:
                failed_stages.append(stage_name)
                error_msg = str(e)
                logger.error(f"[MasterPipeline] ✗ Stage {stage_name} exception: {error_msg}")

                self._notify_progress(stage_name, {'completed': False, 'error': error_msg}, f"{stage_name} exception")

                self.status_tracker.update_pipeline_stage(
                    self.project_id,
                    stage_name,
                    completed=False,
                    error=error_msg
                )

                if stop_on_error:
                    break

        self.end_time = datetime.now()
        duration = (self.end_time - self.start_time).total_seconds()

        # Get AI usage stats
        ai_usage = self.ai.get_usage_report()

        success = len(failed_stages) == 0

        logger.info(f"[MasterPipeline] Unified pipeline completed in {duration:.1f}s")
        logger.info(f"  Completed: {len(completed_stages)}/{total_stages}")
        logger.info(f"  Failed: {len(failed_stages)}/{total_stages}")
        logger.info(f"  AI cost estimate: ${ai_usage.get('total_estimated_cost', 0):.4f}")

        return {
            'success': success,
            'pipeline_type': 'unified',
            'completed_stages': completed_stages,
            'failed_stages': failed_stages,
            'errors': self.errors,
            'duration_seconds': duration,
            'ai_usage': ai_usage,
            'project_id': self.project_id,
            'project_folder': str(self.project_folder),
            'completed_at': self.end_time.isoformat() if self.end_time else None
        }

    async def _execute_unified_stage(self, stage_name: str, stage_class) -> Dict:
        """
        Execute a unified pipeline stage.

        Handles AI provider injection for stages that need it.
        """
        # Stages that need AI provider
        ai_stages = ['id_split', 'ai_query']

        if stage_name in ai_stages:
            stage = stage_class(self.project_folder, self.ai)
        else:
            # Check if stage accepts AI provider optionally
            try:
                stage = stage_class(self.project_folder, self.ai)
            except TypeError:
                stage = stage_class(self.project_folder)

        # Run the stage
        try:
            result = await stage.run()

            # Update status tracker
            stage_data = result.data.copy() if hasattr(result, 'data') else {}

            self.status_tracker.update_pipeline_stage(
                self.project_id,
                stage_name,
                completed=result.success if hasattr(result, 'success') else True,
                data=stage_data,
                error=result.error if hasattr(result, 'error') else None
            )

            # Track errors
            if hasattr(result, 'error') and result.error:
                self.errors.append({
                    'stage': stage_name,
                    'error': result.error,
                    'timestamp': datetime.now().isoformat()
                })

            return {
                'success': result.success if hasattr(result, 'success') else True,
                'data': result.data if hasattr(result, 'data') else {},
                'error': result.error if hasattr(result, 'error') else None
            }

        except Exception as e:
            logger.error(f"[MasterPipeline] Unified stage {stage_name} execution error: {e}")

            self.status_tracker.update_pipeline_stage(
                self.project_id,
                stage_name,
                completed=False,
                error=str(e)
            )

            self.errors.append({
                'stage': stage_name,
                'error': str(e),
                'timestamp': datetime.now().isoformat()
            })

            return {
                'success': False,
                'data': {},
                'error': str(e)
            }

    async def run_stage(self, stage_name: str) -> Dict:
        """
        Run a single pipeline stage.

        Args:
            stage_name: Name of stage to run (e.g., 'rename', 'organize')

        Returns:
            Dict with stage result:
            {
                'success': bool,
                'stage': str,
                'data': Dict,
                'error': Optional[str],
                'duration_seconds': float
            }
        """
        if stage_name not in self.stages:
            valid_stages = list(self.stages.keys())
            raise ValueError(f"Invalid stage '{stage_name}'. Valid stages: {valid_stages}")

        logger.info(f"[MasterPipeline] Running single stage: {stage_name}")

        stage_class = self.stages[stage_name]
        start_time = datetime.now()

        try:
            result = await self._execute_stage(stage_name, stage_class)

            end_time = datetime.now()
            duration = (end_time - start_time).total_seconds()

            result['duration_seconds'] = duration
            result['stage'] = stage_name

            return result

        except Exception as e:
            logger.error(f"[MasterPipeline] Stage {stage_name} exception: {e}")

            # Update status tracker with error
            self.status_tracker.update_pipeline_stage(
                self.project_id,
                stage_name,
                completed=False,
                error=str(e)
            )

            return {
                'success': False,
                'stage': stage_name,
                'data': {},
                'error': str(e),
                'duration_seconds': (datetime.now() - start_time).total_seconds()
            }

    async def run_stages(self, stage_names: List[str]) -> Dict:
        """
        Run multiple pipeline stages in sequence.

        Args:
            stage_names: List of stage names to run (e.g., ['organize', 'split_specs', 'rag_analysis'])

        Returns:
            Dict with results for all stages:
            {
                'success': bool,  # True if all stages succeeded
                'results': Dict[str, Dict],  # Results keyed by stage name
                'completed_stages': List[str],
                'failed_stages': List[str],
                'total_duration_seconds': float
            }
        """
        logger.info(f"[MasterPipeline] Running {len(stage_names)} stages: {stage_names}")

        start_time = datetime.now()
        results = {}
        completed_stages = []
        failed_stages = []

        for stage_name in stage_names:
            logger.info(f"[MasterPipeline] Running stage: {stage_name}")

            try:
                result = await self.run_stage(stage_name)
                results[stage_name] = result

                if result['success']:
                    completed_stages.append(stage_name)
                    logger.info(f"[MasterPipeline] ✓ Stage {stage_name} completed")
                else:
                    failed_stages.append(stage_name)
                    logger.error(f"[MasterPipeline] ✗ Stage {stage_name} failed: {result.get('error')}")

            except Exception as e:
                failed_stages.append(stage_name)
                error_msg = str(e)
                logger.error(f"[MasterPipeline] ✗ Stage {stage_name} exception: {error_msg}")

                results[stage_name] = {
                    'success': False,
                    'stage': stage_name,
                    'data': {},
                    'error': error_msg,
                    'duration_seconds': 0
                }

        end_time = datetime.now()
        total_duration = (end_time - start_time).total_seconds()

        success = len(failed_stages) == 0

        logger.info(f"[MasterPipeline] Completed {len(stage_names)} stages in {total_duration:.1f}s")
        logger.info(f"  Completed: {len(completed_stages)}/{len(stage_names)}")
        logger.info(f"  Failed: {len(failed_stages)}/{len(stage_names)}")

        return {
            'success': success,
            'results': results,
            'completed_stages': completed_stages,
            'failed_stages': failed_stages,
            'total_duration_seconds': total_duration
        }

    async def _execute_stage(self, stage_name: str, stage_class) -> Dict:
        """
        Execute a single stage and update status tracker.

        Args:
            stage_name: Stage identifier
            stage_class: Stage class to instantiate

        Returns:
            Dict with execution result
        """
        # Instantiate stage with appropriate parameters
        # Handle special cases for different stage constructors
        if stage_name in ['rename', 'ai_analysis']:
            # These stages need AI provider
            stage = stage_class(self.project_folder, self.ai)
        else:
            # Other stages just need project folder
            stage = stage_class(self.project_folder)

        # Run the stage
        try:
            result = await stage.run()

            # CRITICAL: If rename stage changed folder path, update our reference
            if stage_name == 'rename' and hasattr(result, 'success') and result.success:
                new_path = result.data.get('new_path') if hasattr(result, 'data') else None
                if new_path:
                    old_path = self.project_folder
                    self.project_folder = Path(new_path)
                    self.project_id = self.project_folder.name
                    logger.info(f"[MasterPipeline] Folder path updated: {old_path.name} -> {self.project_folder.name}")

            # Update status tracker
            stage_data = result.data.copy() if hasattr(result, 'data') else {}

            self.status_tracker.update_pipeline_stage(
                self.project_id,
                stage_name,
                completed=result.success if hasattr(result, 'success') else True,
                data=stage_data,
                error=result.error if hasattr(result, 'error') else None
            )

            # Track errors
            if hasattr(result, 'error') and result.error:
                self.errors.append({
                    'stage': stage_name,
                    'error': result.error,
                    'timestamp': datetime.now().isoformat()
                })

            return {
                'success': result.success if hasattr(result, 'success') else True,
                'data': result.data if hasattr(result, 'data') else {},
                'error': result.error if hasattr(result, 'error') else None
            }

        except Exception as e:
            logger.error(f"[MasterPipeline] Stage {stage_name} execution error: {e}")

            self.status_tracker.update_pipeline_stage(
                self.project_id,
                stage_name,
                completed=False,
                error=str(e)
            )

            self.errors.append({
                'stage': stage_name,
                'error': str(e),
                'timestamp': datetime.now().isoformat()
            })

            return {
                'success': False,
                'data': {},
                'error': str(e)
            }

    def get_progress(self) -> Dict:
        """
        Get current pipeline progress for UI polling.

        Returns:
            Dict with:
            {
                'project_id': str,
                'running': bool,
                'current_stage': Optional[str],
                'current_stage_index': int,
                'total_stages': int,
                'percent_complete': float,
                'stages': Dict[str, Dict],  # Full stage status
                'start_time': Optional[str],
                'errors': List[Dict]
            }
        """
        pipeline_status = self.status_tracker.get_pipeline_status(self.project_id)

        if not pipeline_status:
            return {
                'project_id': self.project_id,
                'running': False,
                'current_stage': None,
                'current_stage_index': 0,
                'total_stages': 8,
                'percent_complete': 0.0,
                'stages': {},
                'start_time': None,
                'errors': []
            }

        # Calculate percent complete
        stages = pipeline_status.get('stages', {})
        completed_count = sum(1 for s in stages.values() if s.get('completed', False))
        percent_complete = (completed_count / 8) * 100

        # Check if currently running
        running = (
            self.start_time is not None and
            self.end_time is None and
            self.current_stage is not None
        )

        return {
            'project_id': self.project_id,
            'running': running,
            'current_stage': self.current_stage,
            'current_stage_index': self.current_stage_index,
            'total_stages': 8,
            'percent_complete': round(percent_complete, 1),
            'stages': stages,
            'start_time': self.start_time.isoformat() if self.start_time else None,
            'elapsed_seconds': (datetime.now() - self.start_time).total_seconds() if self.start_time else 0,
            'errors': pipeline_status.get('errors', []),
            'overall_complete': pipeline_status.get('overall_complete', False)
        }

    def get_incomplete_stages(self) -> List[str]:
        """
        Get list of stages that haven't been completed yet.

        Returns:
            List of stage names (e.g., ['rename', 'organize'])
        """
        return self.status_tracker.get_incomplete_stages(self.project_id)

    def is_stage_complete(self, stage_name: str) -> bool:
        """
        Check if a specific stage is complete.

        Args:
            stage_name: Name of stage to check

        Returns:
            True if stage completed successfully
        """
        return self.status_tracker.is_stage_complete(self.project_id, stage_name)

    def is_pipeline_complete(self) -> bool:
        """
        Check if all pipeline stages are complete.

        Returns:
            True if all 8 stages completed successfully
        """
        return self.status_tracker.is_pipeline_complete(self.project_id)

    def get_stage_result(self, stage_name: str) -> Optional[Dict]:
        """
        Get the stored result for a specific stage.

        Args:
            stage_name: Name of stage

        Returns:
            Dict with stage data, or None if not found/not completed
        """
        pipeline_status = self.status_tracker.get_pipeline_status(self.project_id)
        if not pipeline_status:
            return None

        return pipeline_status.get('stages', {}).get(stage_name)

    def get_pipeline_summary(self) -> Dict:
        """
        Get a summary of the entire pipeline state.

        Returns:
            Dict with pipeline overview including stage statuses, timestamps, errors
        """
        pipeline_status = self.status_tracker.get_pipeline_status(self.project_id)

        if not pipeline_status:
            return {
                'project_id': self.project_id,
                'project_folder': str(self.project_folder),
                'pipeline_run': False,
                'overall_complete': False,
                'stages_complete': 0,
                'stages_total': 8,
                'last_run': None,
                'last_run_mode': None,
                'errors': []
            }

        stages = pipeline_status.get('stages', {})
        stages_complete = sum(1 for s in stages.values() if s.get('completed', False))

        return {
            'project_id': self.project_id,
            'project_folder': str(self.project_folder),
            'pipeline_run': True,
            'overall_complete': pipeline_status.get('overall_complete', False),
            'stages_complete': stages_complete,
            'stages_total': 8,
            'last_run': pipeline_status.get('last_run'),
            'last_run_mode': pipeline_status.get('last_run_mode'),
            'errors': pipeline_status.get('errors', []),
            'stages': {
                name: {
                    'completed': data.get('completed', False),
                    'completed_at': data.get('completed_at'),
                    'error': data.get('error')
                }
                for name, data in stages.items()
            }
        }

    def reset_pipeline(self):
        """
        Reset the pipeline status, clearing all stage completions.

        Useful for re-running the full pipeline from scratch.
        """
        logger.info(f"[MasterPipeline] Resetting pipeline for {self.project_id}")

        # Reset by starting a new pipeline run
        self.status_tracker.start_pipeline_run(self.project_id, mode='manual')

        # Clear local state
        self.current_stage = None
        self.current_stage_index = 0
        self.errors = []
        self.start_time = None
        self.end_time = None


# Convenience functions for one-shot pipeline execution

async def run_pipeline_for_project(
    project_folder: Path,
    mode: str = 'manual',
    stop_on_error: bool = False,
    openai_key: str = None,
    openrouter_key: str = None
) -> Dict:
    """
    Convenience function to run full LEGACY pipeline for a project.

    Args:
        project_folder: Path to project folder
        mode: 'manual' or 'auto'
        stop_on_error: Whether to stop on first error
        openai_key: Optional OpenAI API key
        openrouter_key: Optional OpenRouter API key

    Returns:
        Pipeline execution result dict
    """
    pipeline = MasterPipeline(
        project_folder,
        openai_key=openai_key,
        openrouter_key=openrouter_key
    )

    return await pipeline.run_full_pipeline(mode=mode, stop_on_error=stop_on_error)


async def run_unified_pipeline_for_project(
    project_folder: Path,
    mode: str = 'manual',
    stop_on_error: bool = False,
    openrouter_key: str = None
) -> Dict:
    """
    Convenience function to run the unified 4-stage pipeline (RECOMMENDED).

    This is the preferred way to run analysis on a project. Uses:
    1. UnifiedIDSplitStage - Identify and split docs
    2. OrganizeStage - Structure files
    3. RAGAnalysisStage - Build vector index
    4. UnifiedAIQueryStage - DeepSeek V3.2 extraction

    Args:
        project_folder: Path to project folder
        mode: 'manual' or 'auto'
        stop_on_error: Whether to stop on first error
        openrouter_key: Optional OpenRouter API key for DeepSeek V3.2

    Returns:
        Pipeline execution result dict
    """
    pipeline = MasterPipeline(
        project_folder,
        openrouter_key=openrouter_key
    )

    return await pipeline.run_unified_pipeline(mode=mode, stop_on_error=stop_on_error)


if __name__ == "__main__":
    # Example usage
    import sys

    if len(sys.argv) < 2:
        print("Usage: python3 master_pipeline.py <project_folder>")
        sys.exit(1)

    project_folder = Path(sys.argv[1])

    if not project_folder.exists():
        print(f"Error: Project folder does not exist: {project_folder}")
        sys.exit(1)

    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # Run pipeline
    print(f"Running pipeline for: {project_folder}")
    result = asyncio.run(run_pipeline_for_project(project_folder))

    print("\n" + "="*60)
    print("Pipeline Results:")
    print("="*60)
    print(f"Success: {result['success']}")
    print(f"Completed stages: {len(result['completed_stages'])}/8")
    print(f"Failed stages: {len(result['failed_stages'])}/8")
    print(f"Duration: {result['duration_seconds']:.1f}s")

    if result['errors']:
        print(f"\nErrors ({len(result['errors'])}):")
        for error in result['errors']:
            print(f"  - {error['stage']}: {error['error']}")

    ai_usage = result.get('ai_usage', {})
    if ai_usage:
        print(f"\nAI Usage:")
        print(f"  GPT-5 nano: {ai_usage.get('gpt5_nano', {}).get('calls', 0)} calls, "
              f"{ai_usage.get('gpt5_nano', {}).get('tokens', 0)} tokens")
        print(f"  DeepSeek: {ai_usage.get('deepseek', {}).get('calls', 0)} calls, "
              f"{ai_usage.get('deepseek', {}).get('tokens', 0)} tokens")
        print(f"  Estimated cost: ${ai_usage.get('total_estimated_cost', 0):.4f}")
