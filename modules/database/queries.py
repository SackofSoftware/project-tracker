"""
Database Query Functions

Common CRUD operations for the Project Tracker database.
"""

from typing import Optional, List, Dict, Any
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import func, desc, or_, and_

from .models import (
    Project, ProjectStatus, ProjectFile, Division8Scope,
    Vendor, VendorQuote, ProjectDogProject, PlanHubLink,
    ProjectNote, ProjectTag, Competitor, ExtractedProjectData,
    Company
)
from .db import get_session


# ==================== PROJECT QUERIES ====================

def get_project(project_id: str, session: Session = None) -> Optional[Project]:
    """Get project by ID"""
    if session:
        return session.query(Project).filter_by(id=project_id).first()

    with get_session() as db:
        return db.query(Project).filter_by(id=project_id).first()


def get_all_projects(session: Session = None) -> List[Project]:
    """Get all projects"""
    if session:
        return session.query(Project).order_by(Project.updated_at.desc()).all()

    with get_session() as db:
        return db.query(Project).order_by(Project.updated_at.desc()).all()


def get_projects_by_source(source: str, session: Session = None) -> List[Project]:
    """Get projects by source (local, projectdog, planhub)"""
    if session:
        return session.query(Project).filter_by(source=source).all()

    with get_session() as db:
        return db.query(Project).filter_by(source=source).all()


def get_upcoming_projects(days: int = 30, session: Session = None) -> List[Project]:
    """Get projects with upcoming bid dates"""
    from datetime import datetime, timedelta
    cutoff = datetime.now() + timedelta(days=days)

    if session:
        return session.query(Project)\
            .filter(Project.bid_date.isnot(None))\
            .filter(Project.bid_date <= cutoff)\
            .filter(Project.bid_date >= datetime.now())\
            .order_by(Project.bid_date).all()

    with get_session() as db:
        return db.query(Project)\
            .filter(Project.bid_date.isnot(None))\
            .filter(Project.bid_date <= cutoff)\
            .filter(Project.bid_date >= datetime.now())\
            .order_by(Project.bid_date).all()


def create_project(project_id: str, data: Dict[str, Any], session: Session = None) -> Project:
    """Create a new project"""
    project = Project(id=project_id, **data)

    if session:
        session.add(project)
        session.flush()
        return project

    with get_session() as db:
        db.add(project)
        db.flush()
        return project


def update_project(project_id: str, data: Dict[str, Any], session: Session = None) -> Optional[Project]:
    """Update project data"""
    if session:
        project = session.query(Project).filter_by(id=project_id).first()
        if project:
            for key, value in data.items():
                if hasattr(project, key):
                    setattr(project, key, value)
            session.flush()
        return project

    with get_session() as db:
        project = db.query(Project).filter_by(id=project_id).first()
        if project:
            for key, value in data.items():
                if hasattr(project, key):
                    setattr(project, key, value)
        return project


def delete_project(project_id: str, session: Session = None) -> bool:
    """Delete project and all related data"""
    if session:
        project = session.query(Project).filter_by(id=project_id).first()
        if project:
            session.delete(project)
            session.flush()
            return True
        return False

    with get_session() as db:
        project = db.query(Project).filter_by(id=project_id).first()
        if project:
            db.delete(project)
            return True
        return False


def search_projects(query: str, session: Session = None) -> List[Project]:
    """Search projects by title, address, or city"""
    search_term = f"%{query}%"

    if session:
        return session.query(Project).filter(
            or_(
                Project.title.ilike(search_term),
                Project.address.ilike(search_term),
                Project.city.ilike(search_term)
            )
        ).all()

    with get_session() as db:
        return db.query(Project).filter(
            or_(
                Project.title.ilike(search_term),
                Project.address.ilike(search_term),
                Project.city.ilike(search_term)
            )
        ).all()


# ==================== PROJECT STATUS QUERIES ====================

def get_project_status(project_id: str, session: Session = None) -> Optional[ProjectStatus]:
    """Get project status"""
    if session:
        return session.query(ProjectStatus).filter_by(project_id=project_id).first()

    with get_session() as db:
        return db.query(ProjectStatus).filter_by(project_id=project_id).first()


def create_or_update_status(project_id: str, data: Dict[str, Any], session: Session = None) -> ProjectStatus:
    """Create or update project status"""
    if session:
        status = session.query(ProjectStatus).filter_by(project_id=project_id).first()
        if status:
            for key, value in data.items():
                if hasattr(status, key):
                    setattr(status, key, value)
        else:
            status = ProjectStatus(project_id=project_id, **data)
            session.add(status)
        session.flush()
        return status

    with get_session() as db:
        status = db.query(ProjectStatus).filter_by(project_id=project_id).first()
        if status:
            for key, value in data.items():
                if hasattr(status, key):
                    setattr(status, key, value)
        else:
            status = ProjectStatus(project_id=project_id, **data)
            db.add(status)
        return status


# ==================== PROJECT FILES QUERIES ====================

def get_project_files(project_id: str, file_type: str = None, session: Session = None) -> List[ProjectFile]:
    """Get files for a project, optionally filtered by type"""
    if session:
        query = session.query(ProjectFile).filter_by(project_id=project_id)
        if file_type:
            query = query.filter_by(file_type=file_type)
        return query.all()

    with get_session() as db:
        query = db.query(ProjectFile).filter_by(project_id=project_id)
        if file_type:
            query = query.filter_by(file_type=file_type)
        return query.all()


def add_project_file(project_id: str, file_data: Dict[str, Any], session: Session = None) -> ProjectFile:
    """Add a file record to a project"""
    file_record = ProjectFile(project_id=project_id, **file_data)

    if session:
        session.add(file_record)
        session.flush()
        return file_record

    with get_session() as db:
        db.add(file_record)
        db.flush()
        return file_record


def bulk_add_files(project_id: str, files_data: List[Dict[str, Any]], session: Session = None) -> List[ProjectFile]:
    """Add multiple file records at once"""
    file_records = [ProjectFile(project_id=project_id, **file_data) for file_data in files_data]

    if session:
        session.bulk_save_objects(file_records, return_defaults=True)
        session.flush()
        return file_records

    with get_session() as db:
        db.bulk_save_objects(file_records, return_defaults=True)
        db.flush()
        return file_records


# ==================== DIVISION 8 SCOPE QUERIES ====================

def get_division8_scope(project_id: str, session: Session = None) -> Optional[Division8Scope]:
    """Get Division 8 scope analysis for a project"""
    if session:
        return session.query(Division8Scope).filter_by(project_id=project_id).first()

    with get_session() as db:
        return db.query(Division8Scope).filter_by(project_id=project_id).first()


def save_division8_scope(project_id: str, scope_data: Dict[str, Any], session: Session = None) -> Division8Scope:
    """Save or update Division 8 scope analysis"""
    if session:
        scope = session.query(Division8Scope).filter_by(project_id=project_id).first()
        if scope:
            for key, value in scope_data.items():
                if hasattr(scope, key):
                    setattr(scope, key, value)
        else:
            scope = Division8Scope(project_id=project_id, **scope_data)
            session.add(scope)
        session.flush()
        return scope

    with get_session() as db:
        scope = db.query(Division8Scope).filter_by(project_id=project_id).first()
        if scope:
            for key, value in scope_data.items():
                if hasattr(scope, key):
                    setattr(scope, key, value)
        else:
            scope = Division8Scope(project_id=project_id, **scope_data)
            db.add(scope)
        return scope


# ==================== VENDOR QUERIES ====================

def get_vendor(vendor_id: int = None, name: str = None, session: Session = None) -> Optional[Vendor]:
    """Get vendor by ID or name"""
    if session:
        if vendor_id:
            return session.query(Vendor).filter_by(id=vendor_id).first()
        if name:
            return session.query(Vendor).filter_by(name=name).first()
        return None

    with get_session() as db:
        if vendor_id:
            return db.query(Vendor).filter_by(id=vendor_id).first()
        if name:
            return db.query(Vendor).filter_by(name=name).first()
        return None


def get_all_vendors(active_only: bool = True, session: Session = None) -> List[Vendor]:
    """Get all vendors"""
    if session:
        query = session.query(Vendor)
        if active_only:
            query = query.filter_by(active=True)
        return query.order_by(Vendor.name).all()

    with get_session() as db:
        query = db.query(Vendor)
        if active_only:
            query = query.filter_by(active=True)
        return query.order_by(Vendor.name).all()


def create_vendor(vendor_data: Dict[str, Any], session: Session = None) -> Vendor:
    """Create a new vendor"""
    vendor = Vendor(**vendor_data)

    if session:
        session.add(vendor)
        session.flush()
        return vendor

    with get_session() as db:
        db.add(vendor)
        db.flush()
        return vendor


def get_or_create_vendor(name: str, vendor_data: Dict[str, Any] = None, session: Session = None) -> Vendor:
    """Get existing vendor by name or create new one"""
    vendor = get_vendor(name=name, session=session)
    if vendor:
        return vendor

    data = vendor_data or {}
    data['name'] = name
    return create_vendor(data, session=session)


# ==================== VENDOR QUOTES QUERIES ====================

def get_project_quotes(project_id: str, session: Session = None) -> List[VendorQuote]:
    """Get all quotes for a project"""
    if session:
        return session.query(VendorQuote).filter_by(project_id=project_id).all()

    with get_session() as db:
        return db.query(VendorQuote).filter_by(project_id=project_id).all()


def add_vendor_quote(quote_data: Dict[str, Any], session: Session = None) -> VendorQuote:
    """Add a vendor quote"""
    quote = VendorQuote(**quote_data)

    if session:
        session.add(quote)
        session.flush()
        return quote

    with get_session() as db:
        db.add(quote)
        db.flush()
        return quote


# ==================== PROJECTDOG QUERIES ====================

def get_projectdog_project(project_code: str, session: Session = None) -> Optional[ProjectDogProject]:
    """Get ProjectDog project by code"""
    if session:
        return session.query(ProjectDogProject).filter_by(project_code=project_code).first()

    with get_session() as db:
        return db.query(ProjectDogProject).filter_by(project_code=project_code).first()


def get_all_projectdog_projects(session: Session = None) -> List[ProjectDogProject]:
    """Get all ProjectDog projects"""
    if session:
        return session.query(ProjectDogProject).order_by(ProjectDogProject.scraped_at.desc()).all()

    with get_session() as db:
        return db.query(ProjectDogProject).order_by(ProjectDogProject.scraped_at.desc()).all()


def save_projectdog_project(project_data: Dict[str, Any], session: Session = None) -> ProjectDogProject:
    """Save or update ProjectDog project"""
    project_code = project_data.get('project_code')

    if session:
        project = session.query(ProjectDogProject).filter_by(project_code=project_code).first()
        if project:
            for key, value in project_data.items():
                if hasattr(project, key):
                    setattr(project, key, value)
        else:
            project = ProjectDogProject(**project_data)
            session.add(project)
        session.flush()
        return project

    with get_session() as db:
        project = db.query(ProjectDogProject).filter_by(project_code=project_code).first()
        if project:
            for key, value in project_data.items():
                if hasattr(project, key):
                    setattr(project, key, value)
        else:
            project = ProjectDogProject(**project_data)
            db.add(project)
        return project


def bulk_save_projectdog_projects(projects_data: List[Dict[str, Any]], session: Session = None) -> int:
    """Bulk save ProjectDog projects, returns count saved"""
    count = 0

    if session:
        for project_data in projects_data:
            save_projectdog_project(project_data, session=session)
            count += 1
        return count

    with get_session() as db:
        for project_data in projects_data:
            save_projectdog_project(project_data, session=db)
            count += 1
        return count


# ==================== PLANHUB QUERIES ====================

def get_planhub_link(planhub_id: str = None, project_id: str = None, session: Session = None) -> Optional[PlanHubLink]:
    """Get PlanHub link by PlanHub ID or project ID"""
    if session:
        if planhub_id:
            return session.query(PlanHubLink).filter_by(planhub_id=planhub_id).first()
        if project_id:
            return session.query(PlanHubLink).filter_by(project_id=project_id).first()
        return None

    with get_session() as db:
        if planhub_id:
            return db.query(PlanHubLink).filter_by(planhub_id=planhub_id).first()
        if project_id:
            return db.query(PlanHubLink).filter_by(project_id=project_id).first()
        return None


def save_planhub_link(planhub_id: str, project_id: str, session: Session = None) -> PlanHubLink:
    """Save or update PlanHub link"""
    if session:
        link = session.query(PlanHubLink).filter_by(planhub_id=planhub_id).first()
        if link:
            link.project_id = project_id
        else:
            link = PlanHubLink(planhub_id=planhub_id, project_id=project_id)
            session.add(link)
        session.flush()
        return link

    with get_session() as db:
        link = db.query(PlanHubLink).filter_by(planhub_id=planhub_id).first()
        if link:
            link.project_id = project_id
        else:
            link = PlanHubLink(planhub_id=planhub_id, project_id=project_id)
            db.add(link)
        return link


# ==================== NOTES, TAGS, COMPETITORS ====================

def add_project_note(project_id: str, content: str, note_type: str = 'general', session: Session = None) -> ProjectNote:
    """Add a note to a project"""
    note = ProjectNote(project_id=project_id, content=content, note_type=note_type)

    if session:
        session.add(note)
        session.flush()
        return note

    with get_session() as db:
        db.add(note)
        db.flush()
        return note


def get_project_notes(project_id: str, session: Session = None) -> List[ProjectNote]:
    """Get all notes for a project"""
    if session:
        return session.query(ProjectNote).filter_by(project_id=project_id).order_by(ProjectNote.created_at.desc()).all()

    with get_session() as db:
        return db.query(ProjectNote).filter_by(project_id=project_id).order_by(ProjectNote.created_at.desc()).all()


def add_project_tag(project_id: str, tag: str, session: Session = None) -> ProjectTag:
    """Add a tag to a project"""
    project_tag = ProjectTag(project_id=project_id, tag=tag)

    if session:
        session.add(project_tag)
        session.flush()
        return project_tag

    with get_session() as db:
        db.add(project_tag)
        db.flush()
        return project_tag


def add_competitor(project_id: str, company_name: str, contact_name: str = None, notes: str = None, session: Session = None) -> Competitor:
    """Add a competitor to a project"""
    competitor = Competitor(
        project_id=project_id,
        company_name=company_name,
        contact_name=contact_name,
        notes=notes
    )

    if session:
        session.add(competitor)
        session.flush()
        return competitor

    with get_session() as db:
        db.add(competitor)
        db.flush()
        return competitor


# ==================== EXTRACTED DATA QUERIES ====================

def get_extracted_data(project_id: str, session: Session = None) -> Optional[ExtractedProjectData]:
    """Get extracted project data"""
    if session:
        return session.query(ExtractedProjectData).filter_by(project_id=project_id).first()

    with get_session() as db:
        return db.query(ExtractedProjectData).filter_by(project_id=project_id).first()


def save_extracted_data(project_id: str, data: Dict[str, Any], metadata: Dict[str, Any] = None, session: Session = None) -> ExtractedProjectData:
    """Save or update extracted project data"""
    if session:
        extracted = session.query(ExtractedProjectData).filter_by(project_id=project_id).first()
        if extracted:
            extracted.data = data
            if metadata:
                extracted.schema_version = metadata.get('schema_version')
                extracted.extractor_model = metadata.get('extractor_model')
                extracted.source_folder = metadata.get('source_folder')
                extracted.extracted_at = metadata.get('extracted_at')
        else:
            extracted = ExtractedProjectData(
                project_id=project_id,
                data=data,
                **(metadata or {})
            )
            session.add(extracted)
        session.flush()
        return extracted

    with get_session() as db:
        extracted = db.query(ExtractedProjectData).filter_by(project_id=project_id).first()
        if extracted:
            extracted.data = data
            if metadata:
                extracted.schema_version = metadata.get('schema_version')
                extracted.extractor_model = metadata.get('extractor_model')
                extracted.source_folder = metadata.get('source_folder')
                extracted.extracted_at = metadata.get('extracted_at')
        else:
            extracted = ExtractedProjectData(
                project_id=project_id,
                data=data,
                **(metadata or {})
            )
            db.add(extracted)
        return extracted


# ==================== STATISTICS QUERIES ====================

def get_dashboard_stats(session: Session = None) -> Dict[str, Any]:
    """Get dashboard statistics"""
    if session:
        return _compute_stats(session)

    with get_session() as db:
        return _compute_stats(db)


def _compute_stats(session: Session) -> Dict[str, Any]:
    """Compute dashboard statistics"""
    total_projects = session.query(Project).count()
    local_projects = session.query(Project).filter_by(source='local').count()
    projectdog_projects = session.query(ProjectDogProject).count()

    # Projects with upcoming bids (next 30 days)
    from datetime import datetime, timedelta
    cutoff = datetime.now() + timedelta(days=30)
    upcoming_bids = session.query(Project)\
        .filter(Project.bid_date.isnot(None))\
        .filter(Project.bid_date <= cutoff)\
        .filter(Project.bid_date >= datetime.now())\
        .count()

    # Projects with estimates
    projects_with_estimates = session.query(ProjectStatus)\
        .filter_by(estimate_created=True)\
        .count()

    # Projects with Division 8 scope analysis
    projects_with_scope = session.query(Division8Scope).count()

    return {
        'total_projects': total_projects,
        'local_projects': local_projects,
        'projectdog_projects': projectdog_projects,
        'upcoming_bids': upcoming_bids,
        'projects_with_estimates': projects_with_estimates,
        'projects_with_scope': projects_with_scope,
        'vendors_count': session.query(Vendor).filter_by(active=True).count(),
        'total_quotes': session.query(VendorQuote).count()
    }


# =============================================================================
# CONTRACTOR PROFILE FUNCTIONS
# =============================================================================

def link_company_to_vendor(company_name: str, vendor_name: str = None,
                          threshold: float = 0.85, session: Session = None) -> Dict[str, Any]:
    """
    Link Company and Vendor records by name matching.

    Args:
        company_name: Name of company to find
        vendor_name: Optional specific vendor name to match against
        threshold: Minimum similarity score for fuzzy matching (0-1)
        session: Optional database session

    Returns:
        Dict with keys:
            - company: Company object or None
            - vendor: Vendor object or None
            - match_confidence: 0.0-1.0 similarity score
            - match_method: 'exact'|'fuzzy'|'manual'|'none'
    """
    from difflib import SequenceMatcher

    if session is None:
        with get_session() as db:
            return _link_records(company_name, vendor_name, threshold, db)
    return _link_records(company_name, vendor_name, threshold, session)


def _link_records(company_name, vendor_name, threshold, session):
    """Internal helper for link_company_to_vendor"""
    # Try exact company match first
    company = session.query(Company).filter_by(name=company_name).first()

    if vendor_name:
        # Manual match requested
        vendor = session.query(Vendor).filter_by(name=vendor_name).first()
        if company and vendor:
            return {
                'company': company,
                'vendor': vendor,
                'match_confidence': 1.0,
                'match_method': 'manual'
            }

    # Fuzzy match against all vendors
    vendors = session.query(Vendor).all()
    best_match = None
    best_score = 0

    for v in vendors:
        score = SequenceMatcher(None, company_name.lower(), v.name.lower()).ratio()
        if score > best_score and score >= threshold:
            best_score = score
            best_match = v

    if best_match:
        return {
            'company': company,
            'vendor': best_match,
            'match_confidence': best_score,
            'match_method': 'fuzzy'
        }

    return {
        'company': company,
        'vendor': None,
        'match_confidence': 0.0,
        'match_method': 'none'
    }


def get_vendor_project_history(vendor_id: int, session: Session = None) -> List[Dict[str, Any]]:
    """
    Get all projects a vendor has submitted quotes for.

    Args:
        vendor_id: Vendor ID
        session: Optional database session

    Returns:
        List of dicts with keys:
            - project: Project object
            - quotes: List of VendorQuote objects for this project
            - total_quoted: Sum of quote amounts
            - quote_count: Number of quotes
            - status: ProjectStatus object or None
            - result: 'won'|'lost'|'pending'
    """
    if session is None:
        with get_session() as db:
            return _get_vendor_history(vendor_id, db)
    return _get_vendor_history(vendor_id, session)


def _get_vendor_history(vendor_id, session):
    """Internal helper for get_vendor_project_history"""
    from collections import defaultdict

    # Get all quotes for this vendor
    quotes = session.query(VendorQuote).filter_by(vendor_id=vendor_id).all()

    # Group by project
    projects_map = defaultdict(list)
    for quote in quotes:
        projects_map[quote.project_id].append(quote)

    results = []
    for project_id, project_quotes in projects_map.items():
        project = session.query(Project).filter_by(id=project_id).first()
        if not project:
            continue

        status = session.query(ProjectStatus).filter_by(project_id=project_id).first()

        # Calculate total quoted amount
        total = sum(q.amount for q in project_quotes if q.amount)

        # Determine result (simplified - would need award tracking for accurate won/lost)
        result = 'pending'
        if status:
            if status.bid_decision == 'bid' and status.proposal_submitted:
                result = 'won'  # Simplified assumption
            elif status.bid_decision == 'no-bid':
                result = 'lost'

        results.append({
            'project': project,
            'quotes': project_quotes,
            'total_quoted': total,
            'quote_count': len(project_quotes),
            'status': status,
            'result': result
        })

    # Sort by most recent project first
    results.sort(key=lambda x: x['project'].updated_at or datetime.min, reverse=True)
    return results


def get_contractor_statistics(contractor_name: str = None, vendor_id: int = None,
                              session: Session = None) -> Dict[str, Any]:
    """
    Get statistics for a contractor (from either Company or Vendor).

    Args:
        contractor_name: Company name to look up
        vendor_id: Vendor ID to get stats for
        session: Optional database session

    Returns:
        Dict with keys:
            - total_projects: int
            - projects_won: int
            - projects_lost: int
            - projects_pending: int
            - total_quoted_value: float
            - average_quote_value: float
            - specialties: List[str]
            - certifications: List[str]
            - recent_projects: List of recent Project objects
    """
    if session is None:
        with get_session() as db:
            return _get_contractor_stats(contractor_name, vendor_id, db)
    return _get_contractor_stats(contractor_name, vendor_id, session)


def _get_contractor_stats(contractor_name, vendor_id, session):
    """Internal helper for get_contractor_statistics"""
    # Get vendor_id if not provided
    if not vendor_id and contractor_name:
        link_result = link_company_to_vendor(contractor_name, session=session)
        if link_result['vendor']:
            vendor_id = link_result['vendor'].id

    if not vendor_id:
        # No vendor data available
        company = session.query(Company).filter_by(name=contractor_name).first()
        return {
            'total_projects': 0,
            'projects_won': 0,
            'projects_lost': 0,
            'projects_pending': 0,
            'total_quoted_value': 0.0,
            'average_quote_value': 0.0,
            'specialties': [],
            'certifications': company.certifications if company else [],
            'recent_projects': []
        }

    # Get project history
    history = get_vendor_project_history(vendor_id, session=session)

    # Get vendor for specialties
    vendor = session.query(Vendor).filter_by(id=vendor_id).first()

    # Get company for certifications
    company = None
    if contractor_name:
        company = session.query(Company).filter_by(name=contractor_name).first()
    elif vendor:
        link_result = link_company_to_vendor(vendor.name, session=session)
        company = link_result['company']

    # Calculate statistics
    total_quoted = sum(h['total_quoted'] for h in history if h['total_quoted'])
    quote_count = sum(h['quote_count'] for h in history)

    return {
        'total_projects': len(history),
        'projects_won': sum(1 for h in history if h['result'] == 'won'),
        'projects_lost': sum(1 for h in history if h['result'] == 'lost'),
        'projects_pending': sum(1 for h in history if h['result'] == 'pending'),
        'total_quoted_value': total_quoted,
        'average_quote_value': total_quoted / quote_count if quote_count > 0 else 0.0,
        'specialties': vendor.specialties if vendor else [],
        'certifications': company.certifications if company else [],
        'recent_projects': [h['project'] for h in history[:10]]
    }


def get_planhub_gc_projects(contractor_name: str, session: Session = None) -> List[Dict[str, Any]]:
    """
    Get all PlanHub projects where contractor is listed as general contractor.

    Args:
        contractor_name: Name of contractor to search for
        session: Optional database session

    Returns:
        List of UnifiedProject dicts from PlanHub where contractor is GC
    """
    from difflib import SequenceMatcher
    from modules.planhub.planhub_db_reader import PlanHubDatabaseReader

    # Load all PlanHub projects with extracted data
    reader = PlanHubDatabaseReader()
    all_projects = reader.get_all_leads(status_filter=['done', 'queued'])

    matched_projects = []

    # Normalize contractor name for matching
    contractor_normalized = contractor_name.lower().strip()
    # Remove common suffixes
    for suffix in [', inc.', ', inc', ' inc.', ' inc', ', llc', ' llc',
                   ', corp.', ', corp', ' corp.', ' corp', ' corporation',
                   ', co.', ', co', ' co.', ' company', ' contractors',
                   ' construction', ' builders', ' group', ' services']:
        contractor_normalized = contractor_normalized.replace(suffix, '')

    for unified_project in all_projects:
        # Convert UnifiedProject to dict if needed
        if hasattr(unified_project, 'to_dict'):
            project = unified_project.to_dict()
        elif hasattr(unified_project, '__dict__'):
            project = vars(unified_project)
        else:
            project = unified_project

        general_contractors = project.get('general_contractors', [])

        for gc in general_contractors:
            # Handle if gc is a string or dict
            if isinstance(gc, str):
                gc_name = gc
            else:
                gc_name = gc.get('company_name', '') if isinstance(gc, dict) else str(gc)
            if not gc_name:
                continue

            # Normalize GC name
            gc_normalized = gc_name.lower().strip()
            for suffix in [', inc.', ', inc', ' inc.', ' inc', ', llc', ' llc',
                          ', corp.', ', corp', ' corp.', ' corp', ' corporation',
                          ', co.', ', co', ' co.', ' company', ' contractors',
                          ' construction', ' builders', ' group', ' services']:
                gc_normalized = gc_normalized.replace(suffix, '')

            # Fuzzy match
            similarity = SequenceMatcher(None, contractor_normalized, gc_normalized).ratio()

            if similarity >= 0.85:  # Same threshold as Company-Vendor linking
                matched_projects.append({
                    'project': project,
                    'gc_data': gc,
                    'match_confidence': similarity
                })
                break  # Found match in this project, move to next

    return matched_projects
