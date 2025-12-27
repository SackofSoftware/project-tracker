"""
SQLAlchemy Models for Project Tracker Database

Defines the complete database schema for centralizing all project data.
"""

from sqlalchemy import Column, String, Integer, Float, Boolean, DateTime, Text, JSON, ForeignKey, Table, UniqueConstraint, Index
from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy.sql import func
from datetime import datetime

Base = declarative_base()


# ==================== CORE TABLES ====================

class Project(Base):
    """Core project information"""
    __tablename__ = 'projects'

    id = Column(String, primary_key=True)  # Project slug (e.g., "21-27-neptune")
    folder_path = Column(String)
    title = Column(String)
    source = Column(String)  # 'local', 'projectdog', 'planhub', etc.

    # Basic metadata
    address = Column(String)
    city = Column(String)
    state = Column(String)
    zip_code = Column(String)

    # Contact information
    owner_name = Column(String)
    owner_contact = Column(String)
    architect_name = Column(String)
    architect_contact = Column(String)
    engineer_name = Column(String)
    engineer_contact = Column(String)

    # Dates
    bid_date = Column(DateTime)
    sub_bid_date = Column(DateTime)
    pre_bid_meeting_date = Column(DateTime)
    pre_bid_meeting_location = Column(String)
    pre_bid_mandatory = Column(Boolean)
    substantial_completion = Column(DateTime)
    final_completion = Column(DateTime)

    # Project details
    estimated_value = Column(String)
    project_duration = Column(String)
    liquidated_damages = Column(String)

    # Requirements
    dcam_required = Column(Boolean, default=False)
    prevailing_wage = Column(Boolean, default=False)
    prequalification_required = Column(Boolean, default=False)
    mbe_goal_percent = Column(Float)

    # PlanHub-specific fields
    square_footage = Column(Integer)
    construction_type = Column(String)  # 'Government / Public', 'Commercial', 'Residential'
    project_type = Column(String)       # 'Renovation/Remodel/Repair', 'New Construction'
    building_use = Column(String)       # 'Education/School', 'Bank/Financial', 'Retail', etc.
    description = Column(Text)
    trades = Column(String)             # Comma-separated trades (e.g., "Glazing; Windows; Doors")
    distance_miles = Column(Float)
    planhub_viewed = Column(Boolean, default=False)
    planhub_locked = Column(Boolean, default=False)

    # Workflow status (NEW - for project lifecycle tracking)
    # Values: forecast, bid_opportunity, bidding, gc_awarded, under_contract, lost, complete
    workflow_status = Column(String, default='bid_opportunity')
    workflow_status_changed_at = Column(DateTime)
    workflow_status_notes = Column(Text)

    # Archived status
    archived = Column(Boolean, default=False)
    archived_date = Column(DateTime)
    archived_reason = Column(String)  # 'past_bid_date', 'no_bid', 'lost', 'completed', 'manual', 'declined'

    # Timestamps
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    last_synced_at = Column(DateTime)  # Track last background sync

    # Relationships
    status = relationship("ProjectStatus", back_populates="project", uselist=False)
    files = relationship("ProjectFile", back_populates="project", cascade="all, delete-orphan")
    division8_scope = relationship("Division8Scope", back_populates="project", uselist=False)
    quotes = relationship("VendorQuote", back_populates="project", cascade="all, delete-orphan")
    notes = relationship("ProjectNote", back_populates="project", cascade="all, delete-orphan")
    tags = relationship("ProjectTag", back_populates="project", cascade="all, delete-orphan")
    competitors = relationship("Competitor", back_populates="project", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Project(id='{self.id}', title='{self.title}')>"


class ProjectStatus(Base):
    """Project bid status, decisions, proposals, and estimates"""
    __tablename__ = 'project_status'

    id = Column(Integer, primary_key=True)
    project_id = Column(String, ForeignKey('projects.id'), unique=True)

    # Bid decision
    bid_decision = Column(String)  # 'bid', 'no-bid', 'pending'
    bid_decision_reason = Column(Text)
    bid_decision_date = Column(DateTime)

    # Proposal
    proposal_generated = Column(Boolean, default=False)
    proposal_generated_date = Column(DateTime)
    proposal_submitted = Column(Boolean, default=False)
    proposal_submitted_date = Column(DateTime)
    proposal_notes = Column(Text)

    # Estimate
    estimate_created = Column(Boolean, default=False)
    estimate_created_date = Column(DateTime)
    estimate_total = Column(Float)
    estimate_confidence = Column(String)
    estimate_notes = Column(Text)

    # Estimate breakdown (JSON stored as TEXT for flexibility)
    windows_material = Column(Float)
    windows_labor = Column(Float)
    windows_total = Column(Float)

    doors_material = Column(Float)
    doors_labor = Column(Float)
    doors_total = Column(Float)

    hardware_material = Column(Float)
    hardware_labor = Column(Float)
    hardware_total = Column(Float)

    storefront_material = Column(Float)
    storefront_labor = Column(Float)
    storefront_total = Column(Float)

    curtain_wall_material = Column(Float)
    curtain_wall_labor = Column(Float)
    curtain_wall_total = Column(Float)

    glazing_material = Column(Float)
    glazing_labor = Column(Float)
    glazing_total = Column(Float)

    misc_material = Column(Float)
    misc_labor = Column(Float)
    misc_total = Column(Float)

    # Documents
    documents_acquired = Column(Boolean, default=False)
    documents_acquired_date = Column(DateTime)
    has_specs = Column(Boolean, default=False)
    has_drawings = Column(Boolean, default=False)
    addenda_count = Column(Integer, default=0)

    # Timestamps
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    # Relationships
    project = relationship("Project", back_populates="status")

    def __repr__(self):
        return f"<ProjectStatus(project_id='{self.project_id}', bid_decision='{self.bid_decision}')>"


class ProjectFile(Base):
    """File classifications for project documents"""
    __tablename__ = 'project_files'

    id = Column(Integer, primary_key=True)
    project_id = Column(String, ForeignKey('projects.id'))

    name = Column(String, nullable=False)
    path = Column(String, nullable=False)
    file_type = Column(String)  # 'drawing_set', 'specification', 'email', etc.
    confidence = Column(Float)

    # File details (from classification)
    pages = Column(Integer)
    size_mb = Column(Float)
    width_pt = Column(Integer)
    height_pt = Column(Integer)
    dimensions = Column(String)
    extension = Column(String)

    # Drawing-specific
    sheet_number = Column(String)
    sheet_title = Column(String)
    discipline = Column(String)  # A, S, M, E, P, etc.

    # Metadata
    classified_by = Column(String)  # 'heuristic', 'llm', 'user'
    created_at = Column(DateTime, default=func.now())

    # Relationships
    project = relationship("Project", back_populates="files")

    def __repr__(self):
        return f"<ProjectFile(name='{self.name}', type='{self.file_type}')>"


class Division8Scope(Base):
    """RAG-analyzed Division 8 scope from specifications"""
    __tablename__ = 'division8_scope'

    id = Column(Integer, primary_key=True)
    project_id = Column(String, ForeignKey('projects.id'), unique=True)

    # Summary
    scope_summary = Column(Text)
    confidence = Column(String)

    # Windows
    windows_count = Column(String)
    windows_types = Column(JSON)  # Array of window types
    windows_notes = Column(Text)

    # Doors
    metal_door_count = Column(String)
    wood_door_count = Column(String)
    doors_notes = Column(Text)

    # Storefront
    storefront_description = Column(Text)
    storefront_sf_estimate = Column(String)

    # Hardware
    hardware_groups = Column(JSON)  # Array of hardware groups
    hardware_manufacturers = Column(JSON)  # Array of manufacturers
    hardware_notes = Column(Text)

    # Glass
    glass_specs = Column(JSON)  # Array of glass specifications
    glass_notes = Column(Text)

    # Exclusions
    exclusions = Column(JSON)  # Array of exclusions

    # RAG metadata
    embedder_model = Column(String)
    generator_model = Column(String)
    chunks_analyzed = Column(Integer)
    total_chunks = Column(Integer)
    tokens_used = Column(Integer)

    # Timestamps
    generated_at = Column(DateTime)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    # Relationships
    project = relationship("Project", back_populates="division8_scope")

    def __repr__(self):
        return f"<Division8Scope(project_id='{self.project_id}', confidence='{self.confidence}')>"


# ==================== VENDOR TABLES ====================

class Vendor(Base):
    """Vendor database with contact information"""
    __tablename__ = 'vendors'

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False, unique=True)

    # Contact
    contact_name = Column(String)
    email = Column(String)
    phone = Column(String)
    fax = Column(String)

    # Address
    address = Column(String)
    city = Column(String)
    state = Column(String)
    zip_code = Column(String)

    # Business details
    company_type = Column(String)  # 'manufacturer', 'distributor', 'subcontractor'
    specialties = Column(JSON)  # Array of specialties
    certifications = Column(JSON)  # Array of certifications

    # Status
    active = Column(Boolean, default=True)
    notes = Column(Text)

    # Timestamps
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    # Relationships
    quotes = relationship("VendorQuote", back_populates="vendor", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Vendor(name='{self.name}')>"


class VendorQuote(Base):
    """Vendor quotes linked to projects and vendors"""
    __tablename__ = 'vendor_quotes'

    id = Column(Integer, primary_key=True)
    project_id = Column(String, ForeignKey('projects.id'))
    vendor_id = Column(Integer, ForeignKey('vendors.id'))

    # Quote details
    quote_number = Column(String)
    quote_date = Column(DateTime)
    category = Column(String)  # 'windows', 'doors', 'hardware', etc.

    # Pricing
    amount = Column(Float)
    unit_price = Column(Float)
    quantity = Column(Float)
    unit = Column(String)  # 'ea', 'sf', 'lf', etc.

    # Status
    status = Column(String)  # 'pending', 'received', 'accepted', 'rejected'
    notes = Column(Text)

    # Files
    quote_file_path = Column(String)

    # Timestamps
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    # Relationships
    project = relationship("Project", back_populates="quotes")
    vendor = relationship("Vendor", back_populates="quotes")

    def __repr__(self):
        return f"<VendorQuote(project_id='{self.project_id}', vendor='{self.vendor_id}', amount={self.amount})>"


# ==================== PROJECTDOG TABLES ====================

class ProjectDogProject(Base):
    """Projects scraped from ProjectDog.com"""
    __tablename__ = 'projectdog_projects'

    id = Column(Integer, primary_key=True)
    project_code = Column(String, unique=True, nullable=False)
    interest_list_id = Column(String)

    title = Column(String)
    is_rfq = Column(Boolean, default=False)
    is_dcam = Column(Boolean, default=False)

    # Dates
    bid_date = Column(DateTime)
    sub_bid_date = Column(DateTime)

    # Location
    city = Column(String)
    state = Column(String)
    location_raw = Column(String)

    # Project details
    estimated_value = Column(String)

    # Documents
    has_documents = Column(Boolean, default=False)
    has_ebid = Column(Boolean, default=False)
    documents_acquired = Column(Boolean, default=False)
    documents = Column(JSON)  # Array of document objects
    document_recipients = Column(JSON)  # Array of recipients
    url = Column(String)  # ProjectDog project URL

    # Metadata
    scraped_at = Column(DateTime)

    # Timestamps
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    def __repr__(self):
        return f"<ProjectDogProject(code='{self.project_code}', title='{self.title}')>"


class PlanHubLink(Base):
    """Mapping between PlanHub IDs and local project folders"""
    __tablename__ = 'planhub_links'

    id = Column(Integer, primary_key=True)
    planhub_id = Column(String, unique=True, nullable=False)
    project_id = Column(String, nullable=False)  # Local project slug

    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    def __repr__(self):
        return f"<PlanHubLink(planhub_id='{self.planhub_id}', project_id='{self.project_id}')>"


class ProjectSourceLink(Base):
    """
    Unified linking table for all external project sources.
    Links external source records (PlanHub, ProjectDog, Email, GovWin) to canonical local projects.
    """
    __tablename__ = 'project_source_links'

    id = Column(Integer, primary_key=True)

    # Local project (canonical) - the project this source links to
    project_id = Column(String, ForeignKey('projects.id'), nullable=False, index=True)

    # External source reference
    source_type = Column(String, nullable=False)  # 'planhub', 'projectdog', 'email', 'govwin'
    source_id = Column(String, nullable=False)    # ID in external system (e.g., planhub project ID)
    source_data = Column(JSON)                    # Cached snapshot of external data

    # Matching metadata
    match_confidence = Column(Float, default=1.0)  # 0-1 confidence score
    match_type = Column(String, default='manual')  # 'auto', 'manual', 'suggested'
    matched_by = Column(String)                    # 'system' or username

    # Timestamps
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    # Relationship back to project
    project = relationship("Project", backref="source_links")

    # Unique constraint: one link per source_type + source_id combination
    __table_args__ = (
        UniqueConstraint('source_type', 'source_id', name='uq_source_link'),
        Index('ix_project_source_links_project', 'project_id', 'source_type'),
    )

    def __repr__(self):
        return f"<ProjectSourceLink(project_id='{self.project_id}', source_type='{self.source_type}', source_id='{self.source_id}')>"


# ==================== SUPPORTING TABLES ====================

class ProjectNote(Base):
    """User notes on projects"""
    __tablename__ = 'project_notes'

    id = Column(Integer, primary_key=True)
    project_id = Column(String, ForeignKey('projects.id'))

    content = Column(Text, nullable=False)
    note_type = Column(String)  # 'general', 'estimate', 'bid', etc.

    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    created_by = Column(String, default='user')

    # Relationships
    project = relationship("Project", back_populates="notes")

    def __repr__(self):
        return f"<ProjectNote(project_id='{self.project_id}', type='{self.note_type}')>"


class ProjectTag(Base):
    """Tags for categorizing projects"""
    __tablename__ = 'project_tags'

    id = Column(Integer, primary_key=True)
    project_id = Column(String, ForeignKey('projects.id'))
    tag = Column(String, nullable=False)

    created_at = Column(DateTime, default=func.now())

    # Relationships
    project = relationship("Project", back_populates="tags")

    def __repr__(self):
        return f"<ProjectTag(project_id='{self.project_id}', tag='{self.tag}')>"


class Competitor(Base):
    """Competitors tracked per project"""
    __tablename__ = 'competitors'

    id = Column(Integer, primary_key=True)
    project_id = Column(String, ForeignKey('projects.id'))

    company_name = Column(String, nullable=False)
    contact_name = Column(String)
    notes = Column(Text)

    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    # Relationships
    project = relationship("Project", back_populates="competitors")

    def __repr__(self):
        return f"<Competitor(project_id='{self.project_id}', company='{self.company_name}')>"


# ==================== CONTRACTOR TABLES ====================

class ProjectContractor(Base):
    """
    GCs and subcontractors associated with projects.
    Tracks bid invitations, awards, and relationships.
    """
    __tablename__ = 'project_contractors'

    id = Column(Integer, primary_key=True)
    project_id = Column(String, ForeignKey('projects.id'), nullable=False)

    # Contractor Info
    company_name = Column(String, nullable=False)
    company_id = Column(String, ForeignKey('companies.id'), nullable=True)  # Link to companies table
    contact_name = Column(String)
    contact_email = Column(String)
    contact_phone = Column(String)

    # Role
    role = Column(String, nullable=False)  # 'gc', 'sub', 'bid_inviter', 'cm'
    trade = Column(String)  # For subs: 'glazing', 'doors', 'hardware', etc.

    # Relationship Status
    relationship_type = Column(String)  # 'invited', 'bidding', 'awarded', 'declined', 'lost'
    invited_date = Column(DateTime)
    response_date = Column(DateTime)
    awarded_date = Column(DateTime)

    # Source Tracking
    source = Column(String)  # 'planhub', 'email', 'manual', 'projectdog'

    # Notes
    notes = Column(Text)

    # Timestamps
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    # Relationships
    project = relationship("Project", backref="contractors")
    company = relationship("Company", backref="project_associations")

    # Indexes for fast lookups
    __table_args__ = (
        Index('ix_project_contractors_project', 'project_id'),
        Index('ix_project_contractors_company', 'company_name'),
        Index('ix_project_contractors_role', 'role'),
    )

    def __repr__(self):
        return f"<ProjectContractor(project_id='{self.project_id}', company='{self.company_name}', role='{self.role}')>"

    def to_dict(self):
        return {
            'id': self.id,
            'project_id': self.project_id,
            'company_name': self.company_name,
            'company_id': self.company_id,
            'contact_name': self.contact_name,
            'contact_email': self.contact_email,
            'contact_phone': self.contact_phone,
            'role': self.role,
            'trade': self.trade,
            'relationship_type': self.relationship_type,
            'invited_date': self.invited_date.isoformat() if self.invited_date else None,
            'response_date': self.response_date.isoformat() if self.response_date else None,
            'awarded_date': self.awarded_date.isoformat() if self.awarded_date else None,
            'source': self.source,
            'notes': self.notes,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }


# ==================== DEDUPLICATION TABLES ====================

class DeduplicationLog(Base):
    """
    Audit trail for all deduplication decisions.
    Supports auto-merges (≥90% confidence), user approvals, and rejections.
    """
    __tablename__ = 'deduplication_log'

    id = Column(Integer, primary_key=True)

    # The merge action
    canonical_project_id = Column(String, ForeignKey('projects.id'), nullable=False)
    merged_source_type = Column(String, nullable=False)  # 'planhub', 'email', 'bidding', etc.
    merged_source_id = Column(String, nullable=False)

    # Matching details
    match_confidence = Column(Float)  # 0-1 score
    match_reasons = Column(JSON)  # {"name": 0.85, "location": 1.0, "date": 0.9}

    # Decision
    decision = Column(String, nullable=False)  # 'auto_merged', 'user_approved', 'user_rejected'
    decided_by = Column(String)  # 'system' or username
    decided_at = Column(DateTime, default=func.now())

    # Rollback support
    pre_merge_snapshot = Column(JSON)  # Full snapshot of merged record before merge

    # Indexes
    __table_args__ = (
        Index('ix_dedup_log_canonical', 'canonical_project_id'),
        Index('ix_dedup_log_decision', 'decision'),
        Index('ix_dedup_log_source', 'merged_source_type', 'merged_source_id'),
    )

    def __repr__(self):
        return f"<DeduplicationLog(canonical='{self.canonical_project_id}', source='{self.merged_source_type}:{self.merged_source_id}', decision='{self.decision}')>"

    def to_dict(self):
        return {
            'id': self.id,
            'canonical_project_id': self.canonical_project_id,
            'merged_source_type': self.merged_source_type,
            'merged_source_id': self.merged_source_id,
            'match_confidence': self.match_confidence,
            'match_reasons': self.match_reasons,
            'decision': self.decision,
            'decided_by': self.decided_by,
            'decided_at': self.decided_at.isoformat() if self.decided_at else None,
            'pre_merge_snapshot': self.pre_merge_snapshot
        }


class PendingDuplicate(Base):
    """
    Potential duplicates awaiting user review (confidence 0.70-0.89).
    Auto-merges happen at ≥0.90, below 0.50 are ignored.
    """
    __tablename__ = 'pending_duplicates'

    id = Column(Integer, primary_key=True)

    # The two projects that might be duplicates
    project_a_id = Column(String, ForeignKey('projects.id'), nullable=False)
    project_b_id = Column(String, nullable=False)  # Could be project ID or source reference
    project_b_type = Column(String, nullable=False)  # 'project', 'planhub', 'email', etc.

    # Match scoring
    match_confidence = Column(Float, nullable=False)
    match_reasons = Column(JSON)  # Detailed breakdown

    # Review status
    status = Column(String, default='pending')  # 'pending', 'merged', 'rejected', 'deferred'
    reviewed_by = Column(String)
    reviewed_at = Column(DateTime)
    review_notes = Column(Text)

    # Timestamps
    created_at = Column(DateTime, default=func.now())

    # Indexes
    __table_args__ = (
        Index('ix_pending_dup_status', 'status'),
        Index('ix_pending_dup_confidence', 'match_confidence'),
        UniqueConstraint('project_a_id', 'project_b_id', 'project_b_type', name='uq_pending_duplicate'),
    )

    def __repr__(self):
        return f"<PendingDuplicate(a='{self.project_a_id}', b='{self.project_b_id}', confidence={self.match_confidence})>"

    def to_dict(self):
        return {
            'id': self.id,
            'project_a_id': self.project_a_id,
            'project_b_id': self.project_b_id,
            'project_b_type': self.project_b_type,
            'match_confidence': self.match_confidence,
            'match_reasons': self.match_reasons,
            'status': self.status,
            'reviewed_by': self.reviewed_by,
            'reviewed_at': self.reviewed_at.isoformat() if self.reviewed_at else None,
            'review_notes': self.review_notes,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }


# ==================== EXTRACTED DATA TABLES ====================

class ExtractedProjectData(Base):
    """Cached extracted project data from AI analysis"""
    __tablename__ = 'extracted_project_data'

    id = Column(Integer, primary_key=True)
    project_id = Column(String, unique=True)

    # Raw extracted data (full JSON)
    data = Column(JSON)

    # Metadata
    schema_version = Column(String)
    extractor_model = Column(String)
    source_folder = Column(String)

    # Timestamps
    extracted_at = Column(DateTime)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    def __repr__(self):
        return f"<ExtractedProjectData(project_id='{self.project_id}', model='{self.extractor_model}')>"


# ==================== ANNOTATION TABLES ====================

class PDFAnnotation(Base):
    """PDF annotations for glazing takeoff tool"""
    __tablename__ = 'pdf_annotations'

    id = Column(String, primary_key=True)  # UUID
    project_id = Column(String, nullable=False)
    pdf_path = Column(String, nullable=False)  # Relative path within project
    page_number = Column(Integer, nullable=False)

    # Annotation type
    annotation_type = Column(String, default='tag_marker')  # 'tag_marker', 'region_zone', 'schedule_region'

    # Geometry stored in PDF coordinates (origin bottom-left, 72 DPI)
    geometry = Column(JSON, nullable=False)  # {type: 'polygon', points: [[x,y],...]}

    # Classification
    classification = Column(JSON)  # {category: 'window', typeLabel: 'A', confidence: 0.95}

    # Visual style
    style = Column(JSON)  # {strokeColor, fillColor, strokeWidth}

    # Data extracted by vision model (for schedule regions)
    extracted_data = Column(JSON)  # {width, height, frameMaterial, glassType, etc.}

    # Metadata
    source = Column(String, default='manual')  # 'manual', 'auto-detected'
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    def __repr__(self):
        return f"<PDFAnnotation(id='{self.id}', project='{self.project_id}', type='{self.annotation_type}')>"

    def to_dict(self):
        """Convert to dictionary for JSON serialization"""
        return {
            'id': self.id,
            'project_id': self.project_id,
            'pdf_path': self.pdf_path,
            'page_number': self.page_number,
            'annotation_type': self.annotation_type,
            'geometry': self.geometry,
            'classification': self.classification,
            'style': self.style,
            'extracted_data': self.extracted_data,
            'source': self.source,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }


class DetailRegistry(Base):
    """
    Registry of architectural details and their associated window/door types.
    Enables bidirectional lookup: detail -> types and type -> details.
    """
    __tablename__ = 'detail_registry'

    id = Column(Integer, primary_key=True)
    project_id = Column(String, nullable=False)

    # Detail identification
    detail_id = Column(String, nullable=False)  # e.g., "A501-B", "D/A300", "3/A502"
    detail_title = Column(String)  # e.g., "Jamb Detail", "Head Detail"
    detail_type = Column(String)  # 'jamb', 'head', 'sill', 'threshold', 'frame', 'mullion', 'other'

    # Source location
    source_sheet = Column(String)  # Sheet where detail is drawn (e.g., "A501")
    source_page = Column(Integer)  # Page number

    # Associations (bidirectional)
    applies_to_types = Column(JSON)  # ["A", "B", "C"] - window/door type labels
    applies_to_categories = Column(JSON)  # ["window", "door", "storefront", "curtainwall"]

    # Link to zone annotation (optional)
    annotation_id = Column(String, ForeignKey('pdf_annotations.id'), nullable=True)

    # Notes
    notes = Column(Text)

    # Metadata
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    def __repr__(self):
        return f"<DetailRegistry(detail_id='{self.detail_id}', applies_to={self.applies_to_types})>"

    def to_dict(self):
        """Convert to dictionary for JSON serialization"""
        return {
            'id': self.id,
            'project_id': self.project_id,
            'detail_id': self.detail_id,
            'detail_title': self.detail_title,
            'detail_type': self.detail_type,
            'source_sheet': self.source_sheet,
            'source_page': self.source_page,
            'applies_to_types': self.applies_to_types or [],
            'applies_to_categories': self.applies_to_categories or [],
            'annotation_id': self.annotation_id,
            'notes': self.notes,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }


# ==================== PROJECT LIFECYCLE & INTEGRATION TABLES ====================

class ProjectNumber(Base):
    """
    Sequential project numbering with lifecycle prefixes.

    Prefixes:
    - B = Bidding (active bids in progress)
    - L = Lead (early stage/forecasting)
    - O = Opportunity (potential, not yet qualified)
    - A = Awarded (won)
    - X = Lost/Not Bid/Gone
    """
    __tablename__ = 'project_numbers'

    id = Column(Integer, primary_key=True)
    project_id = Column(String, ForeignKey('projects.id'), unique=True, nullable=False)
    number = Column(Integer, nullable=False)  # Sequential: 1, 2, 3...
    prefix = Column(String(1), nullable=False)  # B, L, O, A, X
    full_number = Column(String(10), nullable=False, unique=True)  # B-001, L-042

    # Audit trail for lifecycle transitions
    previous_prefix = Column(String(1))
    transition_date = Column(DateTime)
    transition_reason = Column(String)

    # Timestamps
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    # Relationship
    project = relationship("Project", backref="project_number_ref")

    def __repr__(self):
        return f"<ProjectNumber(full_number='{self.full_number}', project_id='{self.project_id}')>"

    def to_dict(self):
        return {
            'id': self.id,
            'project_id': self.project_id,
            'number': self.number,
            'prefix': self.prefix,
            'full_number': self.full_number,
            'previous_prefix': self.previous_prefix,
            'transition_date': self.transition_date.isoformat() if self.transition_date else None,
            'transition_reason': self.transition_reason,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }


class ProjectEmail(Base):
    """
    Emails matched to projects from Email Monitor.

    Supports auto-matching with fuzzy confidence scoring and manual override.
    """
    __tablename__ = 'project_emails'

    id = Column(Integer, primary_key=True)
    project_id = Column(String, ForeignKey('projects.id'), nullable=True)  # Nullable for unmatched

    # Email metadata
    subject = Column(String, nullable=False)
    sender = Column(String)
    sender_name = Column(String)
    received_time = Column(DateTime, nullable=False)
    metadata_path = Column(String, nullable=False, unique=True)  # Path to metadata JSON

    # Classification (from Email Monitor)
    email_type = Column(String)  # bid_invite, deadline_reminder, addendum, rfi, project_update
    source_platform = Column(String)  # planhub, buildingconnected, blubook, smartbidnet
    project_folder = Column(String)  # Original folder name in Email Monitor
    extracted_project_name = Column(String)  # Name extracted by classifier
    extracted_bid_date = Column(DateTime)

    # Matching
    match_confidence = Column(Float)  # 0-1 confidence score
    match_type = Column(String)  # 'auto', 'manual', 'unmatched'
    matched_by = Column(String)  # 'system', 'user'
    matched_at = Column(DateTime)

    # Content
    attachments = Column(JSON)  # [{name, path, size}]
    links = Column(JSON)  # Extracted URLs

    # Timestamps
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    # Relationship
    project = relationship("Project", backref="emails")

    def __repr__(self):
        return f"<ProjectEmail(id={self.id}, subject='{self.subject[:30]}...', match_type='{self.match_type}')>"

    def to_dict(self):
        return {
            'id': self.id,
            'project_id': self.project_id,
            'subject': self.subject,
            'sender': self.sender,
            'sender_name': self.sender_name,
            'received_time': self.received_time.isoformat() if self.received_time else None,
            'metadata_path': self.metadata_path,
            'email_type': self.email_type,
            'source_platform': self.source_platform,
            'project_folder': self.project_folder,
            'extracted_project_name': self.extracted_project_name,
            'extracted_bid_date': self.extracted_bid_date.isoformat() if self.extracted_bid_date else None,
            'match_confidence': self.match_confidence,
            'match_type': self.match_type,
            'attachments': self.attachments,
            'links': self.links,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }


class GovLead(Base):
    """
    Government leads from GovWin database.

    Entity types:
    - BID = Active procurement opportunities with response dates
    - LEAD = Forecasted opportunities from Capital Improvement Plans
    """
    __tablename__ = 'gov_leads'

    id = Column(Integer, primary_key=True)
    opportunity_id = Column(String, unique=True, nullable=False)
    project_id = Column(String, ForeignKey('projects.id'), nullable=True)  # Link if converted

    # Core fields from govwin.db
    entity_type = Column(String)  # 'BID' or 'LEAD'
    title = Column(String, nullable=False)
    status = Column(String)  # 'done', 'queued', etc.
    state = Column(String)
    organization = Column(String)
    estimated_value = Column(Float)  # Parsed from string
    response_date = Column(DateTime)  # Bid deadline
    solicitation_date = Column(DateTime)

    # Full text
    description = Column(Text)

    # JSON fields (stored as-is from GovWin)
    overview_data = Column(JSON)  # Parsed from overview_json
    contact_data = Column(JSON)  # Parsed from contact_json

    # Tracking
    interest_level = Column(String)  # 'high', 'medium', 'low', 'not_interested'
    notes = Column(Text)
    converted_to_project = Column(Boolean, default=False)
    converted_at = Column(DateTime)

    # Sync tracking
    last_synced = Column(DateTime)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    # Relationship
    project = relationship("Project", backref="gov_lead")

    def __repr__(self):
        return f"<GovLead(opportunity_id='{self.opportunity_id}', title='{self.title[:40]}...', type='{self.entity_type}')>"

    def to_dict(self):
        return {
            'id': self.id,
            'opportunity_id': self.opportunity_id,
            'project_id': self.project_id,
            'entity_type': self.entity_type,
            'title': self.title,
            'status': self.status,
            'state': self.state,
            'organization': self.organization,
            'estimated_value': self.estimated_value,
            'response_date': self.response_date.isoformat() if self.response_date else None,
            'solicitation_date': self.solicitation_date.isoformat() if self.solicitation_date else None,
            'description': self.description,
            'overview_data': self.overview_data,
            'contact_data': self.contact_data,
            'interest_level': self.interest_level,
            'converted_to_project': self.converted_to_project,
            'converted_at': self.converted_at.isoformat() if self.converted_at else None,
            'last_synced': self.last_synced.isoformat() if self.last_synced else None,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }


# ==================== COMPANY RESEARCH TABLES ====================

class Company(Base):
    """
    Company profiles for contractors, vendors, architects, owners.
    Populated via research agent with structured artifacts.
    """
    __tablename__ = 'companies'

    id = Column(String, primary_key=True)  # UUID
    name = Column(String, nullable=False, unique=True)
    company_type = Column(String)  # 'contractor', 'vendor', 'architect', 'owner'
    website = Column(String)
    headquarters = Column(String)
    phone = Column(String)
    email = Column(String)
    founded = Column(Integer)
    employee_count = Column(String)  # "21-50", "50-100", etc.
    description = Column(Text)
    company_summary = Column(Text)  # 6-8 sentence AI-generated summary

    # Structured data (JSON for flexibility)
    certifications = Column(JSON)  # ["WBE", "LEED", "ABC"]
    leadership = Column(JSON)  # {president: {name, title}, ceo: {}, ...}
    staff = Column(JSON)  # {estimators: [], project_managers: [], superintendents: []}
    services = Column(JSON)  # ["General Contracting", "Construction Management"]
    portfolio = Column(JSON)  # [{name, type, size, year, location}]
    awards = Column(JSON)  # ["Award 2024", ...]
    legal_issues = Column(JSON)  # [{case_name, court, status, url}]
    social_links = Column(JSON)  # {linkedin, facebook, instagram, twitter}
    ratings = Column(JSON)  # {bbb: "A+", google_reviews: 4.5}

    # Research status
    research_status = Column(String, default='pending')  # pending, in_progress, complete, failed
    last_researched = Column(DateTime)

    # Timestamps
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    # Relationships
    research_sessions = relationship("ResearchSession", back_populates="company", cascade="all, delete-orphan")
    research_claims = relationship("ResearchClaim", back_populates="company", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Company(id='{self.id}', name='{self.name}', type='{self.company_type}')>"

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'company_type': self.company_type,
            'website': self.website,
            'headquarters': self.headquarters,
            'phone': self.phone,
            'email': self.email,
            'founded': self.founded,
            'employee_count': self.employee_count,
            'description': self.description,
            'company_summary': self.company_summary,
            'certifications': self.certifications or [],
            'leadership': self.leadership or {},
            'staff': self.staff or {},
            'services': self.services or [],
            'portfolio': self.portfolio or [],
            'awards': self.awards or [],
            'legal_issues': self.legal_issues or [],
            'social_links': self.social_links or {},
            'ratings': self.ratings or {},
            'research_status': self.research_status,
            'last_researched': self.last_researched.isoformat() if self.last_researched else None,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }


class ResearchSession(Base):
    """A research session for a company with progress tracking."""
    __tablename__ = 'research_sessions'

    id = Column(String, primary_key=True)  # UUID
    company_id = Column(String, ForeignKey('companies.id'))

    query = Column(Text)  # Original research query
    status = Column(String, default='queued')  # queued, running, complete, failed
    started_at = Column(DateTime)
    completed_at = Column(DateTime)

    # Progress tracking for UI
    current_stage = Column(String)  # search, extract, verify, compile
    progress_pct = Column(Integer, default=0)
    stages_completed = Column(JSON)  # ["search", "extract"]

    # Final outputs
    final_report = Column(Text)
    sources_used = Column(JSON)  # [url1, url2, ...]
    tokens_used = Column(Integer)
    cost_usd = Column(Float)

    # Error tracking
    error_message = Column(Text)

    created_at = Column(DateTime, default=func.now())

    # Relationships
    company = relationship("Company", back_populates="research_sessions")
    claims = relationship("ResearchClaim", back_populates="session", cascade="all, delete-orphan")
    hypotheses = relationship("ResearchHypothesis", back_populates="session", cascade="all, delete-orphan")
    assumptions = relationship("ResearchAssumption", back_populates="session", cascade="all, delete-orphan")
    conflicts = relationship("ResearchConflict", back_populates="session", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<ResearchSession(id='{self.id}', company_id='{self.company_id}', status='{self.status}')>"

    def to_dict(self):
        return {
            'id': self.id,
            'company_id': self.company_id,
            'query': self.query,
            'status': self.status,
            'started_at': self.started_at.isoformat() if self.started_at else None,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None,
            'current_stage': self.current_stage,
            'progress_pct': self.progress_pct,
            'stages_completed': self.stages_completed or [],
            'final_report': self.final_report,
            'sources_used': self.sources_used or [],
            'tokens_used': self.tokens_used,
            'cost_usd': self.cost_usd,
            'error_message': self.error_message,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }


class ResearchClaim(Base):
    """A discrete, verifiable claim about a company."""
    __tablename__ = 'research_claims'

    id = Column(String, primary_key=True)  # UUID
    session_id = Column(String, ForeignKey('research_sessions.id'))
    company_id = Column(String, ForeignKey('companies.id'))

    claim_text = Column(Text, nullable=False)
    claim_type = Column(String)  # capability, certification, experience, legal, financial, contact, leadership
    confidence = Column(Float)  # 0-1

    # Support classification
    support_type = Column(String)  # direct, inferred, conflicting
    verified = Column(Boolean, default=False)
    verified_by = Column(String)  # 'system', 'user'
    verified_at = Column(DateTime)

    created_at = Column(DateTime, default=func.now())

    # Relationships
    session = relationship("ResearchSession", back_populates="claims")
    company = relationship("Company", back_populates="research_claims")
    evidence = relationship("ResearchEvidence", back_populates="claim", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<ResearchClaim(id='{self.id}', type='{self.claim_type}', confidence={self.confidence})>"

    def to_dict(self):
        return {
            'id': self.id,
            'session_id': self.session_id,
            'company_id': self.company_id,
            'claim_text': self.claim_text,
            'claim_type': self.claim_type,
            'confidence': self.confidence,
            'support_type': self.support_type,
            'verified': self.verified,
            'verified_by': self.verified_by,
            'verified_at': self.verified_at.isoformat() if self.verified_at else None,
            'evidence': [e.to_dict() for e in self.evidence] if self.evidence else [],
            'created_at': self.created_at.isoformat() if self.created_at else None
        }


class ResearchEvidence(Base):
    """Evidence supporting a claim with source citation."""
    __tablename__ = 'research_evidence'

    id = Column(String, primary_key=True)  # UUID
    claim_id = Column(String, ForeignKey('research_claims.id'))

    evidence_text = Column(Text)
    source_url = Column(String)
    source_title = Column(String)
    source_type = Column(String)  # website, legal_record, news, social_media
    excerpt = Column(Text)  # Relevant quote from source
    accessed_at = Column(DateTime)

    created_at = Column(DateTime, default=func.now())

    # Relationships
    claim = relationship("ResearchClaim", back_populates="evidence")

    def __repr__(self):
        return f"<ResearchEvidence(id='{self.id}', source='{self.source_title}')>"

    def to_dict(self):
        return {
            'id': self.id,
            'claim_id': self.claim_id,
            'evidence_text': self.evidence_text,
            'source_url': self.source_url,
            'source_title': self.source_title,
            'source_type': self.source_type,
            'excerpt': self.excerpt,
            'accessed_at': self.accessed_at.isoformat() if self.accessed_at else None,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }


class ResearchHypothesis(Base):
    """Working hypothesis combining multiple claims."""
    __tablename__ = 'research_hypotheses'

    id = Column(String, primary_key=True)  # UUID
    session_id = Column(String, ForeignKey('research_sessions.id'))

    title = Column(String)
    description = Column(Text)
    status = Column(String)  # unconfirmed, confirmed, refuted
    supporting_claims = Column(JSON)  # [claim_id, ...]
    refuting_claims = Column(JSON)  # [claim_id, ...]
    confidence = Column(Float)

    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    # Relationships
    session = relationship("ResearchSession", back_populates="hypotheses")

    def __repr__(self):
        return f"<ResearchHypothesis(id='{self.id}', title='{self.title}', status='{self.status}')>"

    def to_dict(self):
        return {
            'id': self.id,
            'session_id': self.session_id,
            'title': self.title,
            'description': self.description,
            'status': self.status,
            'supporting_claims': self.supporting_claims or [],
            'refuting_claims': self.refuting_claims or [],
            'confidence': self.confidence,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }


class ResearchAssumption(Base):
    """Explicit assumption with risk assessment."""
    __tablename__ = 'research_assumptions'

    id = Column(String, primary_key=True)  # UUID
    session_id = Column(String, ForeignKey('research_sessions.id'))

    assumption_text = Column(Text)
    source = Column(String)  # explicit, inferred, default
    confidence = Column(Float)
    impact_if_wrong = Column(Text)  # What would be affected if this is wrong
    risk_level = Column(String)  # low, medium, high

    created_at = Column(DateTime, default=func.now())

    # Relationships
    session = relationship("ResearchSession", back_populates="assumptions")

    def __repr__(self):
        return f"<ResearchAssumption(id='{self.id}', risk='{self.risk_level}')>"

    def to_dict(self):
        return {
            'id': self.id,
            'session_id': self.session_id,
            'assumption_text': self.assumption_text,
            'source': self.source,
            'confidence': self.confidence,
            'impact_if_wrong': self.impact_if_wrong,
            'risk_level': self.risk_level,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }


class ResearchConflict(Base):
    """Identified contradiction between sources requiring resolution."""
    __tablename__ = 'research_conflicts'

    id = Column(String, primary_key=True)  # UUID
    session_id = Column(String, ForeignKey('research_sessions.id'))

    description = Column(Text)
    source_1 = Column(String)
    source_1_value = Column(String)
    source_2 = Column(String)
    source_2_value = Column(String)
    conflicting_claims = Column(JSON)  # [claim_id, claim_id]
    resolution_status = Column(String, default='unresolved')  # unresolved, resolved, needs_user_input
    resolution = Column(Text)
    resolved_by = Column(String)  # 'system', 'user'
    resolved_at = Column(DateTime)

    created_at = Column(DateTime, default=func.now())

    # Relationships
    session = relationship("ResearchSession", back_populates="conflicts")

    def __repr__(self):
        return f"<ResearchConflict(id='{self.id}', status='{self.resolution_status}')>"

    def to_dict(self):
        return {
            'id': self.id,
            'session_id': self.session_id,
            'description': self.description,
            'source_1': self.source_1,
            'source_1_value': self.source_1_value,
            'source_2': self.source_2,
            'source_2_value': self.source_2_value,
            'conflicting_claims': self.conflicting_claims or [],
            'resolution_status': self.resolution_status,
            'resolution': self.resolution,
            'resolved_by': self.resolved_by,
            'resolved_at': self.resolved_at.isoformat() if self.resolved_at else None,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }
