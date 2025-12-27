"""
CSI Tag Methods for ProjectStatusTracker

Add these methods to the ProjectStatusTracker class in project_status.py
Insert after the existing remove_tag() method (around line 200)
"""

# ==================== CSI TAG METHODS ====================
# Add these to the ProjectStatusTracker class

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
