"""
Flask Blueprint Registration for Project Tracker

This module registers all route blueprints with the Flask application.
Each blueprint handles a specific domain of functionality.
"""

from flask import Flask


def register_blueprints(app: Flask):
    """
    Register all blueprints with the Flask app.

    Blueprints are registered in order of dependency:
    1. Core utilities (sync, stats)
    2. Data access (projects, status, projectdog)
    3. Feature modules (csi, extraction, scope)
    4. UI routes (dashboard)
    """
    # Import blueprints here to avoid circular imports
    from .sync import sync_bp
    from .csi import csi_bp
    from .status import status_bp
    from .projects import projects_bp
    from .projectdog import projectdog_bp
    from .planhub import planhub_bp
    from .extraction import extraction_bp
    from .scope import scope_bp
    from .vendors import vendors_bp
    from .files import files_bp
    from .notes import notes_bp
    from .brief import brief_bp
    from .estimates import estimates_bp
    from .thumbnails import thumbnails_bp
    from .takeoff import takeoff_bp
    from .dashboard import dashboard_bp
    from .pipeline import pipeline_bp
    from .rag import rag_bp
    from .audit import audit_bp
    from .intake import intake_bp
    from .archived import archived_bp
    from .annotation import annotation_bp
    from .validation import validation_bp
    from .pdf_tools import pdf_tools_bp
    from .settings import settings_bp
    from .emails import emails_bp
    from .govleads import govleads_bp

    # New Command Center blueprints
    from .sse import sse_bp
    from .scope_cards import scope_cards_bp
    from .documents import documents_bp
    from .chat import chat_bp
    from .timeline import timeline_bp

    # Quantity verification blueprint
    from .quantity_verification import qty_verification_bp

    # Project source linking blueprint
    from .linking import linking_bp

    # Company research blueprint
    from .research import research_bp

    # Contractors profile blueprint
    from .contractors import contractors_bp

    # Job queue blueprint
    from .jobs import jobs_bp

    # Division 8 Analysis blueprint
    from .analysis import analysis_bp

    # Register each blueprint
    app.register_blueprint(pdf_tools_bp)
    app.register_blueprint(validation_bp)
    app.register_blueprint(annotation_bp)
    app.register_blueprint(archived_bp)
    app.register_blueprint(rag_bp)
    app.register_blueprint(audit_bp)
    app.register_blueprint(intake_bp)
    app.register_blueprint(sync_bp)
    app.register_blueprint(csi_bp)
    app.register_blueprint(status_bp)
    app.register_blueprint(projects_bp)
    app.register_blueprint(projectdog_bp)
    app.register_blueprint(planhub_bp)
    app.register_blueprint(extraction_bp)
    app.register_blueprint(scope_bp)
    app.register_blueprint(vendors_bp)
    app.register_blueprint(files_bp)
    app.register_blueprint(notes_bp)
    app.register_blueprint(brief_bp)
    app.register_blueprint(estimates_bp)
    app.register_blueprint(thumbnails_bp)
    app.register_blueprint(takeoff_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(pipeline_bp)
    app.register_blueprint(settings_bp)
    app.register_blueprint(emails_bp)
    app.register_blueprint(govleads_bp)

    # Command Center blueprints
    app.register_blueprint(sse_bp)
    app.register_blueprint(scope_cards_bp)
    app.register_blueprint(documents_bp)
    app.register_blueprint(chat_bp)
    app.register_blueprint(timeline_bp)

    # Quantity verification
    app.register_blueprint(qty_verification_bp)

    # Project source linking
    app.register_blueprint(linking_bp)

    # Company research
    app.register_blueprint(research_bp)

    # Contractors profile
    app.register_blueprint(contractors_bp)

    # Job queue
    app.register_blueprint(jobs_bp)

    # Division 8 Analysis
    app.register_blueprint(analysis_bp)

    print(f"Registered 38 blueprints")
