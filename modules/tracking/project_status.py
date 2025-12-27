"""
Project Status Tracker
Manages internal status tracking for projects (proposals, estimates, notes)
"""

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any


class ProjectStatusTracker:
    """Tracks internal project status - proposals, estimates, notes"""

    def __init__(self, data_dir: str):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.status_file = self.data_dir / "project_status.json"
        self._status_data = self._load()

    def _load(self) -> Dict:
        """Load status data from file"""
        if self.status_file.exists():
            try:
                with open(self.status_file, 'r') as f:
                    return json.load(f)
            except Exception as e:
                print(f"Error loading status file: {e}")
        return {"projects": {}, "updated_at": None}

    def _save(self):
        """Save status data to file"""
        self._status_data["updated_at"] = datetime.now().isoformat()
        with open(self.status_file, 'w') as f:
            json.dump(self._status_data, f, indent=2)

    def get_status(self, project_id: str) -> Optional[Dict]:
        """Get status for a specific project"""
        return self._status_data.get("projects", {}).get(project_id)

    def set_status(self, project_id: str, status: Dict):
        """Set/update status for a project"""
        if "projects" not in self._status_data:
            self._status_data["projects"] = {}

        existing = self._status_data["projects"].get(project_id, {})
        existing.update(status)
        existing["last_updated"] = datetime.now().isoformat()

        self._status_data["projects"][project_id] = existing
        self._save()

    def create_project_status(self, project_id: str, project_title: str = None) -> Dict:
        """Create initial status entry for a project"""
        status = {
            "project_id": project_id,
            "project_title": project_title,
            "created_at": datetime.now().isoformat(),
            "last_updated": datetime.now().isoformat(),

            # Workflow stages
            "bid_decision": None,  # "pending", "bid", "no_bid", "gc_awarded", "awarded", "lost"
            "bid_decision_reason": None,
            "bid_decision_date": None,

            # Proposal tracking
            "proposal": {
                "generated": False,
                "generated_date": None,
                "submitted": False,
                "submitted_date": None,
                "notes": None
            },

            # Estimate tracking
            "estimate": {
                "created": False,
                "created_date": None,
                "total": None,
                "breakdown": {
                    "windows": {"material": None, "labor": None, "total": None},
                    "doors": {"material": None, "labor": None, "total": None},
                    "hardware": {"material": None, "labor": None, "total": None},
                    "storefront": {"material": None, "labor": None, "total": None},
                    "curtain_wall": {"material": None, "labor": None, "total": None},
                    "glazing": {"material": None, "labor": None, "total": None},
                    "misc": {"material": None, "labor": None, "total": None}
                },
                "notes": None,
                "confidence": None  # "low", "medium", "high"
            },

            # Documents acquired
            "documents": {
                "acquired": False,
                "acquired_date": None,
                "specs": False,
                "drawings": False,
                "addenda_count": 0
            },

            # Notes and tags
            "notes": [],
            "tags": [],  # e.g., ["dcam", "rfq", "priority", "complex"]

            # Competition tracking (from document recipients)
            "competitors": [],

            # Archive status
            "archived": False,
            "archived_date": None,
            "archived_reason": None,  # "past_bid_date", "no_bid", "lost", "completed", "manual"

            # Pipeline stage tracking
            "pipeline": self._create_pipeline_structure(),

            # Timeline / changelog
            "timeline": []
        }

        self._status_data["projects"][project_id] = status
        self._save()
        return status

    def _create_pipeline_structure(self) -> Dict:
        """Create initial pipeline tracking structure"""
        return {
            "last_run": None,
            "last_run_mode": None,  # "auto" or "manual"
            "file_fingerprint": None,  # Hash of file count/sizes for change detection
            "file_count_at_run": 0,  # Number of files when pipeline was run
            "stages": {
                "rename": {
                    "completed": False,
                    "completed_at": None,
                    "original_name": None,
                    "new_name": None,
                    "error": None
                },
                "organize": {
                    "completed": False,
                    "completed_at": None,
                    "files_moved": 0,
                    "folders_created": [],
                    "error": None
                },
                "split_specs": {
                    "completed": False,
                    "completed_at": None,
                    "sections_extracted": [],
                    "total_sections": 0,
                    "error": None
                },
                "split_drawings": {
                    "completed": False,
                    "completed_at": None,
                    "sheets_extracted": 0,
                    "by_discipline": {},
                    "error": None
                },
                "ai_analysis": {
                    "completed": False,
                    "completed_at": None,
                    "pages_analyzed": 0,
                    "model_used": None,
                    "tokens_used": 0,
                    "error": None
                },
                "schedule_parse": {
                    "completed": False,
                    "completed_at": None,
                    "door_entries": 0,
                    "window_entries": 0,
                    "storefront_entries": 0,
                    "metal_doors": 0,
                    "wood_doors_excluded": 0,
                    "error": None
                },
                "highlight": {
                    "completed": False,
                    "completed_at": None,
                    "pages_highlighted": 0,
                    "floor_plans": 0,
                    "exterior_elevations": 0,
                    "excluded_rcp": 0,
                    "error": None
                },
                "quotes": {
                    "completed": False,
                    "completed_at": None,
                    "quotes_found": 0,
                    "quotes_parsed": 0,
                    "vendors": [],
                    "total_value": 0,
                    "error": None
                }
            },
            "overall_complete": False,
            "errors": []
        }

    def update_bid_decision(self, project_id: str, decision: str, reason: str = None):
        """Update bid decision for a project"""
        status = self.get_status(project_id) or self.create_project_status(project_id)
        status["bid_decision"] = decision
        status["bid_decision_reason"] = reason
        status["bid_decision_date"] = datetime.now().isoformat()
        self.set_status(project_id, status)

    def update_proposal(self, project_id: str, generated: bool = None, submitted: bool = None, notes: str = None):
        """Update proposal status"""
        status = self.get_status(project_id) or self.create_project_status(project_id)
        proposal = status.get("proposal", {})

        if generated is not None:
            proposal["generated"] = generated
            if generated:
                proposal["generated_date"] = datetime.now().isoformat()

        if submitted is not None:
            proposal["submitted"] = submitted
            if submitted:
                proposal["submitted_date"] = datetime.now().isoformat()

        if notes is not None:
            proposal["notes"] = notes

        status["proposal"] = proposal
        self.set_status(project_id, status)

    def update_estimate(self, project_id: str, total: float = None, breakdown: Dict = None,
                        notes: str = None, confidence: str = None):
        """Update estimate data"""
        status = self.get_status(project_id) or self.create_project_status(project_id)
        estimate = status.get("estimate", {})

        if total is not None:
            estimate["created"] = True
            estimate["created_date"] = datetime.now().isoformat()
            estimate["total"] = total

        if breakdown:
            estimate["breakdown"].update(breakdown)

        if notes is not None:
            estimate["notes"] = notes

        if confidence is not None:
            estimate["confidence"] = confidence

        status["estimate"] = estimate
        self.set_status(project_id, status)

    def add_note(self, project_id: str, note: str, author: str = None):
        """Add a note to project"""
        status = self.get_status(project_id) or self.create_project_status(project_id)
        notes = status.get("notes", [])
        notes.append({
            "text": note,
            "author": author,
            "created_at": datetime.now().isoformat()
        })
        status["notes"] = notes
        self.set_status(project_id, status)

    def add_tag(self, project_id: str, tag: str):
        """Add a tag to project"""
        status = self.get_status(project_id) or self.create_project_status(project_id)
        tags = status.get("tags", [])
        if tag not in tags:
            tags.append(tag)
            status["tags"] = tags
            self.set_status(project_id, status)

    def remove_tag(self, project_id: str, tag: str):
        """Remove a tag from project"""
        status = self.get_status(project_id)
        if status:
            tags = status.get("tags", [])
            if tag in tags:
                tags.remove(tag)
                status["tags"] = tags
                self.set_status(project_id, status)

    # ==================== CSI TAG METHODS ====================

    def set_csi_tags(self, project_id: str, csi_tags: List[str]):
        """
        Set CSI-derived tags for a project.
        These are stored separately from manual tags and auto-generated from specs.

        Args:
            project_id: Project identifier
            csi_tags: List of CSI tag strings (e.g., ["Metal Windows", "Door Hardware"])
        """
        status = self.get_status(project_id) or self.create_project_status(project_id)
        status["csi_tags"] = sorted(list(set(csi_tags)))  # Dedupe and sort
        status["csi_tags_updated"] = datetime.now().isoformat()
        self.set_status(project_id, status)

    def get_csi_tags(self, project_id: str) -> List[str]:
        """Get CSI-derived tags for a project."""
        status = self.get_status(project_id)
        return status.get("csi_tags", []) if status else []

    def add_csi_tag(self, project_id: str, tag: str):
        """Add a single CSI tag to project."""
        status = self.get_status(project_id) or self.create_project_status(project_id)
        csi_tags = status.get("csi_tags", [])
        if tag not in csi_tags:
            csi_tags.append(tag)
            csi_tags.sort()
            status["csi_tags"] = csi_tags
            status["csi_tags_updated"] = datetime.now().isoformat()
            self.set_status(project_id, status)

    def remove_csi_tag(self, project_id: str, tag: str):
        """Remove a CSI tag from project."""
        status = self.get_status(project_id)
        if status:
            csi_tags = status.get("csi_tags", [])
            if tag in csi_tags:
                csi_tags.remove(tag)
                status["csi_tags"] = csi_tags
                self.set_status(project_id, status)

    def get_all_tags(self, project_id: str) -> Dict[str, List[str]]:
        """
        Get all tags (manual + CSI) for a project, categorized.

        Returns:
            Dict with 'manual' and 'csi' tag lists
        """
        status = self.get_status(project_id)
        if not status:
            return {"manual": [], "csi": [], "all": []}

        manual_tags = status.get("tags", [])
        csi_tags = status.get("csi_tags", [])

        # Merged list (deduplicated)
        all_tags = list(manual_tags)
        for tag in csi_tags:
            if tag not in all_tags:
                all_tags.append(tag)

        return {
            "manual": manual_tags,
            "csi": csi_tags,
            "all": all_tags
        }

    def get_projects_by_csi_tag(self, tag: str) -> List[Dict]:
        """Get all projects that have a specific CSI tag."""
        return [
            status for status in self._status_data.get("projects", {}).values()
            if tag in status.get("csi_tags", [])
        ]

    def get_all_csi_tags_in_use(self) -> Dict[str, int]:
        """
        Get all CSI tags currently in use across all projects with counts.

        Returns:
            Dict mapping tag names to project counts, sorted by count descending
        """
        tag_counts = {}
        for status in self._status_data.get("projects", {}).values():
            if not status.get("archived", False):  # Only active projects
                for tag in status.get("csi_tags", []):
                    tag_counts[tag] = tag_counts.get(tag, 0) + 1
        return dict(sorted(tag_counts.items(), key=lambda x: (-x[1], x[0])))

    def get_csi_tag_summary(self) -> Dict:
        """
        Get summary statistics about CSI tags across all projects.

        Returns:
            Dict with tag counts, most common tags, etc.
        """
        tag_counts = self.get_all_csi_tags_in_use()

        projects_with_tags = len([
            s for s in self._status_data.get("projects", {}).values()
            if s.get("csi_tags") and not s.get("archived", False)
        ])

        total_active = len([
            s for s in self._status_data.get("projects", {}).values()
            if not s.get("archived", False)
        ])

        return {
            "unique_tags": len(tag_counts),
            "projects_with_csi_tags": projects_with_tags,
            "total_active_projects": total_active,
            "coverage_pct": round(projects_with_tags / total_active * 100, 1) if total_active > 0 else 0,
            "top_tags": dict(list(tag_counts.items())[:10]),
            "all_tags": tag_counts
        }

    def update_competitors(self, project_id: str, competitors: List[str]):
        """Update list of competitors (from document recipients)"""
        status = self.get_status(project_id) or self.create_project_status(project_id)
        status["competitors"] = competitors
        self.set_status(project_id, status)

    def archive_project(self, project_id: str, reason: str = "manual"):
        """Archive a project"""
        status = self.get_status(project_id) or self.create_project_status(project_id)
        status["archived"] = True
        status["archived_date"] = datetime.now().isoformat()
        status["archived_reason"] = reason
        self.set_status(project_id, status)

    def unarchive_project(self, project_id: str):
        """Unarchive a project"""
        status = self.get_status(project_id)
        if status:
            status["archived"] = False
            status["archived_date"] = None
            status["archived_reason"] = None
            self.set_status(project_id, status)

    def is_archived(self, project_id: str) -> bool:
        """Check if a project is archived"""
        status = self.get_status(project_id)
        return status.get("archived", False) if status else False

    def get_archived_projects(self) -> List[Dict]:
        """Get all archived projects"""
        return [
            status for status in self._status_data.get("projects", {}).values()
            if status.get("archived", False)
        ]

    def get_active_projects(self) -> List[Dict]:
        """Get all non-archived projects"""
        return [
            status for status in self._status_data.get("projects", {}).values()
            if not status.get("archived", False)
        ]

    # ==================== TIMELINE METHODS ====================

    def add_timeline_event(
        self,
        project_id: str,
        event_type: str,
        title: str,
        description: str = None,
        actor: str = "system",
        source: str = None,
        changes: List[Dict] = None,
        tags: List[str] = None,
        related_file: str = None
    ) -> Dict:
        """
        Add an event to the project timeline.

        Args:
            project_id: Project identifier
            event_type: Type of event (project_created, document_added, scope_updated, etc.)
            title: Short title for the event
            description: Longer description (optional)
            actor: Who/what triggered the event (system, user, ai_assistant)
            source: Source of the change (folder_scan, spreadsheet, addendum, chat, etc.)
            changes: List of field changes [{"field": "x", "old": y, "new": z}]
            tags: Optional tags for filtering
            related_file: Path to related file if applicable

        Returns:
            The created event dict
        """
        status = self.get_status(project_id) or self.create_project_status(project_id)

        if "timeline" not in status:
            status["timeline"] = []

        event = {
            "id": str(uuid.uuid4())[:8],
            "timestamp": datetime.now().isoformat(),
            "event_type": event_type,
            "title": title,
            "description": description,
            "actor": actor,
            "source": source,
            "changes": changes or [],
            "tags": tags or [],
            "related_file": related_file
        }

        # Insert at beginning (newest first)
        status["timeline"].insert(0, event)

        # Keep timeline to reasonable size (last 100 events)
        if len(status["timeline"]) > 100:
            status["timeline"] = status["timeline"][:100]

        self.set_status(project_id, status)
        return event

    def get_timeline(self, project_id: str, limit: int = 50, event_type: str = None) -> List[Dict]:
        """
        Get timeline events for a project.

        Args:
            project_id: Project identifier
            limit: Maximum number of events to return
            event_type: Filter by event type (optional)

        Returns:
            List of timeline events (newest first)
        """
        status = self.get_status(project_id)
        if not status:
            return []

        timeline = status.get("timeline", [])

        if event_type:
            timeline = [e for e in timeline if e.get("event_type") == event_type]

        return timeline[:limit]

    def get_timeline_by_date_range(
        self,
        project_id: str,
        start_date: str = None,
        end_date: str = None
    ) -> List[Dict]:
        """Get timeline events within a date range."""
        status = self.get_status(project_id)
        if not status:
            return []

        timeline = status.get("timeline", [])
        filtered = []

        for event in timeline:
            event_date = event.get("timestamp", "")
            if start_date and event_date < start_date:
                continue
            if end_date and event_date > end_date:
                continue
            filtered.append(event)

        return filtered

    def log_scope_change(
        self,
        project_id: str,
        scope_type: str,
        field: str,
        old_value: Any,
        new_value: Any,
        source: str = "unknown"
    ):
        """
        Convenience method to log a scope card data change.

        Args:
            project_id: Project identifier
            scope_type: windows, doors, hardware, etc.
            field: Field that changed (count, manufacturer, etc.)
            old_value: Previous value
            new_value: New value
            source: Where the change came from (schedule, spreadsheet, chat, etc.)
        """
        self.add_timeline_event(
            project_id=project_id,
            event_type="scope_updated",
            title=f"{scope_type.title()} {field} updated",
            description=f"{field}: {old_value} → {new_value}",
            source=source,
            changes=[{"field": f"{scope_type}.{field}", "old": old_value, "new": new_value}],
            tags=[scope_type, "scope_change"]
        )

    def log_document_added(
        self,
        project_id: str,
        filename: str,
        doc_type: str,
        folder: str = None
    ):
        """
        Convenience method to log a document addition.

        Args:
            project_id: Project identifier
            filename: Name of the file
            doc_type: Type (spec, drawing, addendum, quote, spreadsheet)
            folder: Folder it was saved to
        """
        self.add_timeline_event(
            project_id=project_id,
            event_type="document_added",
            title=f"{doc_type.title()} added",
            description=filename,
            source="file_upload",
            related_file=f"{folder}/{filename}" if folder else filename,
            tags=[doc_type]
        )

    def log_bid_date_change(
        self,
        project_id: str,
        old_date: str,
        new_date: str,
        source: str = "user"
    ):
        """Convenience method to log bid date changes."""
        self.add_timeline_event(
            project_id=project_id,
            event_type="bid_date_changed",
            title="Bid date changed",
            description=f"{old_date or 'Not set'} → {new_date}",
            source=source,
            changes=[{"field": "bid_date", "old": old_date, "new": new_date}],
            tags=["schedule"]
        )

    def log_status_change(
        self,
        project_id: str,
        old_status: str,
        new_status: str,
        reason: str = None
    ):
        """Convenience method to log bid decision changes."""
        self.add_timeline_event(
            project_id=project_id,
            event_type="status_changed",
            title=f"Status: {new_status}",
            description=reason,
            source="user",
            changes=[{"field": "bid_decision", "old": old_status, "new": new_status}],
            tags=["status"]
        )

    def log_quote_received(
        self,
        project_id: str,
        vendor: str,
        amount: float,
        scope_types: List[str] = None
    ):
        """Convenience method to log vendor quotes."""
        self.add_timeline_event(
            project_id=project_id,
            event_type="quote_received",
            title=f"Quote from {vendor}",
            description=f"${amount:,.2f}" if amount else "Amount TBD",
            source="quote_upload",
            tags=["quote"] + (scope_types or [])
        )

    def log_addendum_processed(
        self,
        project_id: str,
        addendum_number: int,
        changes_summary: str,
        changes: List[Dict] = None
    ):
        """Convenience method to log addendum processing."""
        self.add_timeline_event(
            project_id=project_id,
            event_type="addendum_received",
            title=f"Addendum #{addendum_number}",
            description=changes_summary,
            source="addendum",
            changes=changes or [],
            tags=["addendum"]
        )

    def set_extracted_data(self, project_id: str, extracted_data: Dict):
        """Store AI-extracted Division 8 data from documents"""
        status = self.get_status(project_id) or self.create_project_status(project_id)

        # Store the full extraction result
        status["extracted_data"] = {
            "extracted_at": datetime.now().isoformat(),
            "model": extracted_data.get("meta", {}).get("extractor_model", "unknown"),
            "data": extracted_data
        }

        # Also populate relevant status fields from extraction
        if "project" in extracted_data:
            proj_info = extracted_data["project"]
            if proj_info.get("architect") and not status.get("architect"):
                status["architect"] = proj_info.get("architect")
            if proj_info.get("owner") and not status.get("owner"):
                status["owner"] = proj_info.get("owner")

        if "schedule" in extracted_data:
            sched = extracted_data["schedule"]
            if sched.get("bid_date"):
                status["extracted_bid_date"] = sched.get("bid_date")

        if "bid_requirements" in extracted_data:
            req = extracted_data["bid_requirements"]
            status["is_dcam_extracted"] = req.get("dcam_required", False)
            status["prevailing_wage"] = req.get("prevailing_wage", False)
            status["filed_sub_bids"] = req.get("filed_sub_bids", [])

        if "division_8" in extracted_data:
            div8 = extracted_data["division_8"]
            status["division_8_scope"] = {
                "spec_sections": div8.get("spec_sections", []),
                "scope_summary": div8.get("scope_summary"),
                "windows": div8.get("windows", {}),
                "storefront": div8.get("storefront", {}),
                "curtain_wall": div8.get("curtain_wall", {}),
                "doors": div8.get("doors", {}),
                "hardware": div8.get("hardware", {}),
                "glazing": div8.get("glazing", {})
            }

        if "openings_schedule" in extracted_data:
            status["openings_schedule"] = extracted_data["openings_schedule"]

        self.set_status(project_id, status)

    def get_extracted_data(self, project_id: str) -> Optional[Dict]:
        """Get stored extraction data for a project"""
        status = self.get_status(project_id)
        if status:
            return status.get("extracted_data")
        return None

    # ==================== PIPELINE METHODS ====================

    def start_pipeline_run(self, project_id: str, mode: str = "manual"):
        """Initialize a new pipeline run"""
        status = self.get_status(project_id) or self.create_project_status(project_id)

        if "pipeline" not in status:
            status["pipeline"] = self._create_pipeline_structure()

        status["pipeline"]["last_run"] = datetime.now().isoformat()
        status["pipeline"]["last_run_mode"] = mode
        status["pipeline"]["overall_complete"] = False
        status["pipeline"]["errors"] = []

        # Reset all stages
        for stage in status["pipeline"]["stages"].values():
            stage["completed"] = False
            stage["completed_at"] = None
            stage["error"] = None

        self.set_status(project_id, status)

    def update_pipeline_stage(self, project_id: str, stage: str,
                               completed: bool, data: Dict = None, error: str = None):
        """
        Update a single pipeline stage status.

        Args:
            project_id: Project identifier
            stage: Stage name (rename, organize, split_specs, etc.)
            completed: Whether stage completed successfully
            data: Stage-specific data to store
            error: Error message if stage failed
        """
        status = self.get_status(project_id) or self.create_project_status(project_id)

        if "pipeline" not in status:
            status["pipeline"] = self._create_pipeline_structure()

        valid_stages = ["rename", "organize", "split_specs", "split_drawings",
                        "ai_analysis", "schedule_parse", "highlight", "quotes"]

        if stage not in valid_stages:
            raise ValueError(f"Invalid stage: {stage}. Valid stages: {valid_stages}")

        stage_status = status["pipeline"]["stages"].get(stage, {})
        stage_status["completed"] = completed
        stage_status["completed_at"] = datetime.now().isoformat() if completed else None

        if data:
            stage_status.update(data)

        if error:
            stage_status["error"] = error
            status["pipeline"]["errors"].append({
                "stage": stage,
                "error": error,
                "timestamp": datetime.now().isoformat()
            })

        status["pipeline"]["stages"][stage] = stage_status

        # Check if all stages complete
        all_stages = status["pipeline"]["stages"]
        status["pipeline"]["overall_complete"] = all(
            s.get("completed", False) for s in all_stages.values()
        )

        self.set_status(project_id, status)

    def get_pipeline_status(self, project_id: str) -> Optional[Dict]:
        """Get pipeline status for a project"""
        status = self.get_status(project_id)
        if status:
            return status.get("pipeline")
        return None

    def is_pipeline_complete(self, project_id: str) -> bool:
        """Check if all pipeline stages are complete"""
        pipeline = self.get_pipeline_status(project_id)
        return pipeline.get("overall_complete", False) if pipeline else False

    def is_stage_complete(self, project_id: str, stage: str) -> bool:
        """Check if a specific pipeline stage is complete"""
        pipeline = self.get_pipeline_status(project_id)
        if not pipeline:
            return False
        return pipeline.get("stages", {}).get(stage, {}).get("completed", False)

    def get_incomplete_stages(self, project_id: str) -> List[str]:
        """Get list of incomplete pipeline stages"""
        pipeline = self.get_pipeline_status(project_id)
        if not pipeline:
            return ["rename", "organize", "split_specs", "split_drawings",
                    "ai_analysis", "schedule_parse", "highlight", "quotes"]

        return [
            stage for stage, data in pipeline.get("stages", {}).items()
            if not data.get("completed", False)
        ]

    def get_projects_needing_pipeline(self) -> List[Dict]:
        """Get all projects that haven't completed the pipeline"""
        return [
            status for status in self._status_data.get("projects", {}).values()
            if not status.get("archived", False) and
               not status.get("pipeline", {}).get("overall_complete", False)
        ]

    def compute_file_fingerprint(self, project_folder: Path) -> Tuple[str, int]:
        """
        Compute a fingerprint of project files for change detection.

        Uses file count + total size + most recent modification time to create
        a hash that changes when files are added, removed, or modified.

        Args:
            project_folder: Path to project folder

        Returns:
            Tuple of (fingerprint_hash, file_count)
        """
        import hashlib

        if not project_folder.exists():
            return None, 0

        # Count PDF files and get their stats
        pdf_files = list(project_folder.rglob('*.pdf'))
        file_count = len(pdf_files)

        if file_count == 0:
            return "empty", 0

        # Build fingerprint from file info
        # Using: count + total size + most recent mtime
        total_size = sum(f.stat().st_size for f in pdf_files)
        most_recent = max(f.stat().st_mtime for f in pdf_files)

        fingerprint_data = f"{file_count}:{total_size}:{int(most_recent)}"
        fingerprint_hash = hashlib.md5(fingerprint_data.encode()).hexdigest()[:12]

        return fingerprint_hash, file_count

    def update_pipeline_fingerprint(self, project_id: str, project_folder: Path):
        """
        Update the file fingerprint after a pipeline run.

        Args:
            project_id: Project identifier
            project_folder: Path to project folder
        """
        status = self.get_status(project_id) or self.create_project_status(project_id)

        if "pipeline" not in status:
            status["pipeline"] = self._create_pipeline_structure()

        fingerprint, file_count = self.compute_file_fingerprint(Path(project_folder))
        status["pipeline"]["file_fingerprint"] = fingerprint
        status["pipeline"]["file_count_at_run"] = file_count

        self.set_status(project_id, status)

    def project_needs_update(self, project_id: str, project_folder: Path) -> Dict:
        """
        Check if a project needs pipeline re-run due to file changes.

        Args:
            project_id: Project identifier
            project_folder: Path to project folder

        Returns:
            Dict with:
            - needs_update: bool
            - reason: str (why update is needed)
            - current_files: int
            - files_at_run: int
        """
        status = self.get_status(project_id)
        pipeline = status.get("pipeline") if status else None

        if not pipeline or not pipeline.get("overall_complete"):
            return {
                "needs_update": True,
                "reason": "Pipeline not completed",
                "current_files": 0,
                "files_at_run": 0
            }

        current_fingerprint, current_count = self.compute_file_fingerprint(Path(project_folder))
        stored_fingerprint = pipeline.get("file_fingerprint")
        stored_count = pipeline.get("file_count_at_run", 0)

        if current_fingerprint != stored_fingerprint:
            # Determine what changed
            if current_count > stored_count:
                reason = f"New files added ({stored_count} → {current_count})"
            elif current_count < stored_count:
                reason = f"Files removed ({stored_count} → {current_count})"
            else:
                reason = "Files modified"

            return {
                "needs_update": True,
                "reason": reason,
                "current_files": current_count,
                "files_at_run": stored_count
            }

        return {
            "needs_update": False,
            "reason": "No changes detected",
            "current_files": current_count,
            "files_at_run": stored_count
        }

    def get_projects_needing_update(self, bidding_folder: Path) -> List[Dict]:
        """
        Get all projects that need pipeline update (new or changed files).

        Args:
            bidding_folder: Path to bidding folder containing all projects

        Returns:
            List of dicts with project info and update reason
        """
        from pathlib import Path

        needing_update = []

        # Get all project folders in bidding folder
        if not bidding_folder.exists():
            return []

        for project_folder in bidding_folder.iterdir():
            if not project_folder.is_dir() or project_folder.name.startswith('.'):
                continue

            # Use folder name as project ID
            project_id = project_folder.name

            update_info = self.project_needs_update(project_id, project_folder)

            if update_info["needs_update"]:
                # Count PDFs for display
                pdf_count = len(list(project_folder.rglob('*.pdf')))

                needing_update.append({
                    "project_id": project_id,
                    "folder_path": str(project_folder),
                    "reason": update_info["reason"],
                    "current_files": update_info["current_files"],
                    "files_at_run": update_info["files_at_run"],
                    "pdf_count": pdf_count
                })

        return needing_update

    def get_pipeline_summary(self) -> Dict:
        """Get summary of pipeline completion across all projects"""
        projects = self._status_data.get("projects", {})
        active_projects = [p for p in projects.values() if not p.get("archived", False)]

        complete = len([p for p in active_projects
                        if p.get("pipeline", {}).get("overall_complete", False)])
        partial = len([p for p in active_projects
                       if p.get("pipeline", {}).get("last_run") and
                       not p.get("pipeline", {}).get("overall_complete", False)])
        not_started = len([p for p in active_projects
                           if not p.get("pipeline", {}).get("last_run")])

        return {
            "total_active": len(active_projects),
            "pipeline_complete": complete,
            "pipeline_partial": partial,
            "pipeline_not_started": not_started,
            "completion_rate": round(complete / len(active_projects) * 100, 1) if active_projects else 0
        }

    def get_all_status(self) -> Dict[str, Dict]:
        """Get all project statuses"""
        return self._status_data.get("projects", {})

    def get_projects_by_decision(self, decision: str) -> List[Dict]:
        """Get projects by bid decision"""
        return [
            status for status in self._status_data.get("projects", {}).values()
            if status.get("bid_decision") == decision
        ]

    def get_projects_with_estimates(self) -> List[Dict]:
        """Get projects that have estimates"""
        return [
            status for status in self._status_data.get("projects", {}).values()
            if status.get("estimate", {}).get("created")
        ]

    def get_pending_proposals(self) -> List[Dict]:
        """Get projects with proposals generated but not submitted"""
        return [
            status for status in self._status_data.get("projects", {}).values()
            if status.get("proposal", {}).get("generated") and not status.get("proposal", {}).get("submitted")
        ]

    def get_summary_stats(self) -> Dict:
        """Get summary statistics"""
        projects = self._status_data.get("projects", {})
        total = len(projects)

        bid_count = len([p for p in projects.values() if p.get("bid_decision") == "bid"])
        no_bid_count = len([p for p in projects.values() if p.get("bid_decision") == "no_bid"])
        pending_count = len([p for p in projects.values() if p.get("bid_decision") in (None, "pending")])
        gc_awarded_count = len([p for p in projects.values() if p.get("bid_decision") == "gc_awarded"])
        awarded_count = len([p for p in projects.values() if p.get("bid_decision") == "awarded"])
        lost_count = len([p for p in projects.values() if p.get("bid_decision") == "lost"])

        estimate_count = len([p for p in projects.values() if p.get("estimate", {}).get("created")])
        proposal_count = len([p for p in projects.values() if p.get("proposal", {}).get("generated")])
        submitted_count = len([p for p in projects.values() if p.get("proposal", {}).get("submitted")])

        return {
            "total_tracked": total,
            "decisions": {
                "bid": bid_count,
                "no_bid": no_bid_count,
                "pending": pending_count,
                "gc_awarded": gc_awarded_count,
                "awarded": awarded_count,
                "lost": lost_count
            },
            "estimates_created": estimate_count,
            "proposals_generated": proposal_count,
            "proposals_submitted": submitted_count
        }


# Module-level convenience functions
_tracker = None


def get_tracker(data_dir: str = None) -> ProjectStatusTracker:
    """Get or create the global tracker instance"""
    global _tracker
    if _tracker is None:
        if data_dir is None:
            data_dir = Path(__file__).parent.parent.parent / "static" / "data"
        _tracker = ProjectStatusTracker(data_dir)
    return _tracker


if __name__ == "__main__":
    # Test the tracker
    tracker = ProjectStatusTracker("test_data")

    # Create a test project
    status = tracker.create_project_status("test-123", "Test Project")
    print(f"Created status: {status}")

    # Update various fields
    tracker.update_bid_decision("test-123", "bid", "Good scope, fits our capabilities")
    tracker.update_estimate("test-123", total=125000, breakdown={"windows": {"total": 50000}})
    tracker.add_note("test-123", "Need to verify window sizes", "Andrew")
    tracker.add_tag("test-123", "priority")

    # Get updated status
    status = tracker.get_status("test-123")
    print(f"\nUpdated status: {json.dumps(status, indent=2)}")

    # Get summary
    print(f"\nSummary: {tracker.get_summary_stats()}")
