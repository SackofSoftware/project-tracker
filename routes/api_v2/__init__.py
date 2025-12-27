"""
API v2 - Database-Centric Project API

New RESTful API with proper separation of concerns:
- /api/v2/projects - Full project lifecycle
- /api/v2/opportunities - Bid opportunity assessment queue
- /api/v2/leads - GovWin forecasting (separate from projects)
- /api/v2/duplicates - Deduplication review
- /api/v2/sync - Background sync control
"""

from flask import Blueprint

# Create main v2 blueprint
api_v2_bp = Blueprint('api_v2', __name__, url_prefix='/api/v2')

# Import and register sub-blueprints
from .projects import projects_bp
from .opportunities import opportunities_bp
from .leads import leads_bp
from .duplicates import duplicates_bp
from .sync import sync_bp

api_v2_bp.register_blueprint(projects_bp)
api_v2_bp.register_blueprint(opportunities_bp)
api_v2_bp.register_blueprint(leads_bp)
api_v2_bp.register_blueprint(duplicates_bp)
api_v2_bp.register_blueprint(sync_bp)