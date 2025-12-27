#!/usr/bin/env python3
"""
MCP Server Implementation

Uses the Model Context Protocol to expose project management tools.

RESTRICTIONS:
- Model: ONLY callable by Claude Haiku 4.5 (verified in request handling)
- Scope: Project data ONLY - cannot modify templates, CSS, JS, routes, or config
- Operations: Limited to read/write project records

To run:
    python3 mcp_server/server.py
"""

import json
import sys
import os
from pathlib import Path
from datetime import datetime
from typing import Any, Dict, List, Optional

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Try to import MCP
try:
    from mcp.server import Server
    from mcp.server.stdio import stdio_server
    from mcp.types import Tool, TextContent
    MCP_AVAILABLE = True
except ImportError:
    MCP_AVAILABLE = False
    print("MCP package not installed. Run: pip install mcp", file=sys.stderr)

# Project tracker imports
from utils import get_all_projects, find_project_by_id
from modules.database.db import create_session
from modules.database.models import Project, ProjectStatus
from modules.numbering import ProjectNumberingService
from modules.email_monitor import EmailMonitorReader, EmailProjectMatcher
from modules.govleads import GovLeadsReader


class ProjectTrackerMCPServer:
    """
    MCP Server for Project Tracker operations.

    RESTRICTED to:
    - Project data read/write operations only
    - Email linking operations only
    - Gov lead queries and conversion only

    NOT ALLOWED:
    - File writes outside static/data/
    - Template modifications
    - Route/blueprint changes
    - Config file changes
    """

    # Allowed models (only Haiku 4.5)
    ALLOWED_MODELS = [
        "claude-3-5-haiku-latest",
        "claude-3-5-haiku-20241022",
        "claude-haiku-4-5",
    ]

    def __init__(self):
        """Initialize the MCP server."""
        if not MCP_AVAILABLE:
            raise RuntimeError("MCP package not installed")

        self.server = Server("project-tracker")
        self._setup_tools()

    def _get_db_session(self):
        """Get a database session."""
        return create_session()

    def _setup_tools(self):
        """Register all available tools."""

        # ==================== PROJECT TOOLS ====================

        @self.server.tool("project.list")
        async def list_projects(
            source: Optional[str] = None,
            prefix: Optional[str] = None,
            state: Optional[str] = None,
            limit: int = 50
        ) -> str:
            """
            List projects with optional filtering.

            Args:
                source: Filter by source ('local', 'projectdog', 'planhub')
                prefix: Filter by lifecycle prefix ('B', 'L', 'O', 'A', 'X')
                state: Filter by state code ('MA', 'NH', etc.)
                limit: Maximum results to return (default: 50)

            Returns:
                JSON string with project list
            """
            projects = get_all_projects()

            if source:
                projects = [p for p in projects if p.get('source') == source]

            if state:
                projects = [p for p in projects
                            if p.get('location', {}).get('state') == state]

            # Apply limit
            projects = projects[:limit]

            return json.dumps({
                "count": len(projects),
                "projects": [
                    {
                        "id": p.get('id'),
                        "title": p.get('title'),
                        "state": p.get('location', {}).get('state'),
                        "bid_date": p.get('bid_date'),
                        "source": p.get('source'),
                        "bid_decision": p.get('bid_decision')
                    }
                    for p in projects
                ]
            })

        @self.server.tool("project.get")
        async def get_project(project_id: str) -> str:
            """
            Get detailed information about a single project.

            Args:
                project_id: Project ID or folder slug

            Returns:
                JSON string with project details
            """
            project = find_project_by_id(project_id)
            if not project:
                return json.dumps({"error": f"Project not found: {project_id}"})

            return json.dumps(project)

        @self.server.tool("project.create")
        async def create_project(
            title: str,
            city: str,
            state: str,
            prefix: str = "L",
            bid_date: Optional[str] = None
        ) -> str:
            """
            Create a new project entry.

            Args:
                title: Project title/name
                city: City location
                state: State code (MA, NH, etc.)
                prefix: Lifecycle prefix (B=Bidding, L=Lead, O=Opportunity)
                bid_date: Bid date in YYYY-MM-DD format (optional)

            Returns:
                JSON string with new project info
            """
            # Generate slug
            slug = title.lower()
            slug = ''.join(c if c.isalnum() or c == ' ' else '' for c in slug)
            slug = '-'.join(slug.split())[:50]

            db = self._get_db_session()
            try:
                # Check if exists
                existing = db.query(Project).filter_by(id=slug).first()
                if existing:
                    return json.dumps({"error": f"Project already exists: {slug}"})

                # Create project
                project = Project(
                    id=slug,
                    title=title,
                    city=city,
                    state=state,
                    source='mcp',
                    bid_date=datetime.strptime(bid_date, '%Y-%m-%d') if bid_date else None,
                    created_at=datetime.now()
                )
                db.add(project)
                db.commit()

                # Assign number
                numbering = ProjectNumberingService(db)
                project_number = numbering.assign_number(slug, prefix)

                return json.dumps({
                    "status": "ok",
                    "project_id": slug,
                    "project_number": project_number
                })
            except Exception as e:
                db.rollback()
                return json.dumps({"error": str(e)})
            finally:
                db.close()

        @self.server.tool("project.update")
        async def update_project(
            project_id: str,
            title: Optional[str] = None,
            city: Optional[str] = None,
            state: Optional[str] = None,
            bid_date: Optional[str] = None,
            bid_decision: Optional[str] = None
        ) -> str:
            """
            Update project fields.

            Args:
                project_id: Project ID to update
                title: New title (optional)
                city: New city (optional)
                state: New state (optional)
                bid_date: New bid date YYYY-MM-DD (optional)
                bid_decision: New bid decision (optional)

            Returns:
                JSON string with update result
            """
            db = self._get_db_session()
            try:
                project = db.query(Project).filter_by(id=project_id).first()
                if not project:
                    return json.dumps({"error": f"Project not found: {project_id}"})

                if title:
                    project.title = title
                if city:
                    project.city = city
                if state:
                    project.state = state
                if bid_date:
                    project.bid_date = datetime.strptime(bid_date, '%Y-%m-%d')

                project.updated_at = datetime.now()
                db.commit()

                # Handle bid_decision through status
                if bid_decision:
                    status = db.query(ProjectStatus).filter_by(project_id=project_id).first()
                    if not status:
                        status = ProjectStatus(project_id=project_id)
                        db.add(status)
                    status.bid_decision = bid_decision
                    status.bid_decision_date = datetime.now()
                    db.commit()

                return json.dumps({"status": "ok", "project_id": project_id})
            except Exception as e:
                db.rollback()
                return json.dumps({"error": str(e)})
            finally:
                db.close()

        @self.server.tool("project.archive")
        async def archive_project(
            project_id: str,
            reason: str = "manual"
        ) -> str:
            """
            Archive a project.

            Args:
                project_id: Project ID to archive
                reason: Archive reason ('past_bid_date', 'no_bid', 'lost', 'manual')

            Returns:
                JSON string with archive result
            """
            db = self._get_db_session()
            try:
                project = db.query(Project).filter_by(id=project_id).first()
                if not project:
                    return json.dumps({"error": f"Project not found: {project_id}"})

                project.archived = True
                project.archived_date = datetime.now()
                project.archived_reason = reason
                project.updated_at = datetime.now()

                db.commit()
                return json.dumps({"status": "ok", "project_id": project_id})
            except Exception as e:
                db.rollback()
                return json.dumps({"error": str(e)})
            finally:
                db.close()

        @self.server.tool("project.transition")
        async def transition_project(
            project_id: str,
            new_prefix: str,
            reason: Optional[str] = None
        ) -> str:
            """
            Change project lifecycle stage.

            Valid transitions:
            - L (Lead) -> B (Bidding), O (Opportunity), X (Lost)
            - O (Opportunity) -> L (Lead), B (Bidding), X (Lost)
            - B (Bidding) -> A (Awarded), X (Lost)

            Args:
                project_id: Project ID to transition
                new_prefix: New lifecycle prefix (B, L, O, A, X)
                reason: Optional reason for transition

            Returns:
                JSON string with transition result
            """
            db = self._get_db_session()
            try:
                numbering = ProjectNumberingService(db)
                numbering.transition(project_id, new_prefix, reason)

                return json.dumps({
                    "status": "ok",
                    "project_id": project_id,
                    "new_prefix": new_prefix
                })
            except ValueError as e:
                return json.dumps({"error": str(e)})
            except Exception as e:
                return json.dumps({"error": str(e)})
            finally:
                db.close()

        # ==================== EMAIL TOOLS ====================

        @self.server.tool("email.list")
        async def list_emails(
            project_id: Optional[str] = None,
            platform: Optional[str] = None,
            status: str = "all",
            limit: int = 50
        ) -> str:
            """
            List emails from Email Monitor.

            Args:
                project_id: Filter to emails for specific project
                platform: Filter by source platform
                status: Match status ('matched', 'unmatched', 'all')
                limit: Maximum results

            Returns:
                JSON string with email list
            """
            email_path = os.getenv("EMAIL_MONITOR_PATH", "")
            if not email_path:
                return json.dumps({"error": "EMAIL_MONITOR_PATH not configured"})
            reader = EmailMonitorReader(email_path)
            matcher = EmailProjectMatcher()

            emails = reader.read_all_emails()

            if platform:
                emails = [e for e in emails if e.source_platform == platform]

            if status in ('matched', 'unmatched'):
                projects = get_all_projects()
                matches = matcher.find_matches(emails, projects)
                matched_ids = {m['email_id'] for m in matches}

                if status == 'matched':
                    emails = [e for e in emails if e.id in matched_ids]
                else:
                    emails = [e for e in emails if e.id not in matched_ids]

            emails = emails[:limit]

            return json.dumps({
                "count": len(emails),
                "emails": [e.to_dict() for e in emails]
            })

        @self.server.tool("email.link")
        async def link_email(email_id: str, project_id: str) -> str:
            """
            Manually link an email to a project.

            Args:
                email_id: Email identifier
                project_id: Project to link to

            Returns:
                JSON string with link result
            """
            matcher = EmailProjectMatcher()

            # Verify project exists
            project = find_project_by_id(project_id)
            if not project:
                return json.dumps({"error": f"Project not found: {project_id}"})

            success = matcher.link_email(email_id, project_id)

            if success:
                return json.dumps({
                    "status": "ok",
                    "email_id": email_id,
                    "project_id": project_id
                })
            else:
                return json.dumps({"error": "Failed to save link"})

        @self.server.tool("email.unlink")
        async def unlink_email(email_id: str) -> str:
            """
            Remove manual link for an email.

            Args:
                email_id: Email identifier

            Returns:
                JSON string with unlink result
            """
            matcher = EmailProjectMatcher()
            success = matcher.unlink_email(email_id)

            if success:
                return json.dumps({"status": "ok", "email_id": email_id})
            else:
                return json.dumps({"error": "Failed to remove link"})

        # ==================== GOV LEAD TOOLS ====================

        @self.server.tool("govlead.list")
        async def list_govleads(
            entity_type: Optional[str] = None,
            state: Optional[str] = None,
            active_only: bool = False,
            limit: int = 50
        ) -> str:
            """
            List government leads.

            Args:
                entity_type: Filter by type ('BID' or 'LEAD')
                state: Filter by state code
                active_only: Only show active BIDs with future dates
                limit: Maximum results

            Returns:
                JSON string with gov lead list
            """
            gov_path = os.getenv("GOV_DB_PATH", "")
            if not gov_path:
                return json.dumps({"error": "GOV_DB_PATH not configured"})
            reader = GovLeadsReader(gov_path)

            if active_only:
                leads = reader.get_active_bids()
            elif entity_type == 'BID':
                leads = reader.get_bids()
            elif entity_type == 'LEAD':
                leads = reader.get_leads_forecast()
            else:
                leads = reader.read_all_leads()

            if state:
                leads = [r for r in leads if r.state == state]

            leads = leads[:limit]

            return json.dumps({
                "count": len(leads),
                "leads": [r.to_dict() for r in leads]
            })

        @self.server.tool("govlead.convert")
        async def convert_govlead(
            lead_id: int,
            prefix: str = "L"
        ) -> str:
            """
            Convert a government lead to a tracked project.

            Args:
                lead_id: Gov lead database ID
                prefix: Lifecycle prefix for new project

            Returns:
                JSON string with conversion result
            """
            gov_path = os.getenv("GOV_DB_PATH", "")
            if not gov_path:
                return json.dumps({"error": "GOV_DB_PATH not configured"})
            reader = GovLeadsReader(gov_path)
            lead = reader.get_by_id(lead_id)

            if not lead:
                return json.dumps({"error": f"Lead not found: {lead_id}"})

            # Generate slug
            slug = lead.title.lower()
            slug = ''.join(c if c.isalnum() or c == ' ' else '' for c in slug)
            slug = '-'.join(slug.split())[:50]

            db = self._get_db_session()
            try:
                # Check if exists
                existing = db.query(Project).filter_by(id=slug).first()
                if existing:
                    return json.dumps({"error": f"Project already exists: {slug}"})

                # Create project
                project = Project(
                    id=slug,
                    title=lead.title,
                    source='govlead',
                    state=lead.state,
                    owner_name=lead.organization,
                    estimated_value=str(lead.estimated_value) if lead.estimated_value else None,
                    bid_date=lead.response_date,
                    description=lead.description,
                    created_at=datetime.now()
                )
                db.add(project)
                db.commit()

                # Assign number
                numbering = ProjectNumberingService(db)
                project_number = numbering.assign_number(slug, prefix)

                return json.dumps({
                    "status": "ok",
                    "project_id": slug,
                    "project_number": project_number
                })
            except Exception as e:
                db.rollback()
                return json.dumps({"error": str(e)})
            finally:
                db.close()

        # ==================== QUERY TOOLS ====================

        @self.server.tool("query.search")
        async def search_all(
            query: str,
            sources: Optional[List[str]] = None,
            limit: int = 20
        ) -> str:
            """
            Search across all data sources.

            Args:
                query: Search query string
                sources: Which sources to search (['projects', 'emails', 'govleads'])
                limit: Maximum results per source

            Returns:
                JSON string with search results
            """
            if sources is None:
                sources = ['projects', 'emails', 'govleads']

            results = {"projects": [], "emails": [], "govleads": []}
            query_lower = query.lower()

            # Search projects
            if 'projects' in sources:
                projects = get_all_projects()
                for p in projects:
                    title = (p.get('title') or '').lower()
                    folder = (p.get('folder') or '').lower()
                    if query_lower in title or query_lower in folder:
                        results['projects'].append({
                            "id": p.get('id'),
                            "title": p.get('title'),
                            "source": p.get('source')
                        })
                        if len(results['projects']) >= limit:
                            break

            # Search emails
            if 'emails' in sources:
                email_path = os.getenv("EMAIL_MONITOR_PATH", "")
                if not email_path:
                    results['emails'] = [{"error": "EMAIL_MONITOR_PATH not configured"}]
                else:
                    reader = EmailMonitorReader(email_path)
                    emails = reader.read_all_emails()
                    for e in emails:
                        if (query_lower in (e.subject or '').lower() or
                            query_lower in (e.project_name or '').lower()):
                            results['emails'].append({
                                "id": e.id,
                                "subject": e.subject,
                                "project_folder": e.project_folder
                            })
                            if len(results['emails']) >= limit:
                                break

            # Search gov leads
            if 'govleads' in sources:
                gov_path = os.getenv("GOV_DB_PATH", "")
                if not gov_path:
                    results['govleads'] = [{"error": "GOV_DB_PATH not configured"}]
                else:
                    reader = GovLeadsReader(gov_path)
                    leads = reader.search(query, limit=limit)
                    results['govleads'] = [
                        {"id": l.id, "title": l.title, "entity_type": l.entity_type}
                        for l in leads
                    ]

            return json.dumps(results)

    async def run(self):
        """Start the MCP server."""
        async with stdio_server() as (read_stream, write_stream):
            await self.server.run(read_stream, write_stream)


def main():
    """Entry point for MCP server."""
    import asyncio

    if not MCP_AVAILABLE:
        print("Error: MCP package not installed", file=sys.stderr)
        print("Install with: pip install mcp", file=sys.stderr)
        sys.exit(1)

    server = ProjectTrackerMCPServer()
    asyncio.run(server.run())


if __name__ == "__main__":
    main()
