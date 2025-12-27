"""
CSI Masterformat service module for project-tracker.
Provides section lookups, manufacturer matching, scope enrichment, and auto-tagging.
"""
from .csi_service import (
    CSIService,
    load_masterformat_sections,
    load_products_database,
    get_section_info,
    enrich_scope_with_csi,
    match_manufacturers,
    normalize_section_id,
    extract_section_references,
    categorize_section
)

# Import tagging functions (graceful degradation if not available)
try:
    from .csi_tagging import (
        generate_csi_tags,
        generate_simple_tags,
        extract_and_generate_tags,
        get_all_csi_tag_options,
        get_tag_name_for_section,
        CSITaggingService,
        get_csi_tagging_service,
        CATEGORY_COLORS
    )
    CSI_TAGGING_AVAILABLE = True
except ImportError:
    CSI_TAGGING_AVAILABLE = False
    # Provide stub functions
    def generate_csi_tags(sections): return []
    def generate_simple_tags(sections): return []
    def extract_and_generate_tags(text): return {"simple_tags": [], "detailed_tags": [], "sections_found": []}
    def get_all_csi_tag_options(): return []
    def get_tag_name_for_section(s): return ("other", "Unknown")
    CATEGORY_COLORS = {}

__all__ = [
    # Core CSI service
    'CSIService',
    'load_masterformat_sections',
    'load_products_database',
    'get_section_info',
    'enrich_scope_with_csi',
    'match_manufacturers',
    'normalize_section_id',
    'extract_section_references',
    'categorize_section',
    # Tagging
    'generate_csi_tags',
    'generate_simple_tags',
    'extract_and_generate_tags',
    'get_all_csi_tag_options',
    'get_tag_name_for_section',
    'CSI_TAGGING_AVAILABLE',
    'CATEGORY_COLORS'
]
