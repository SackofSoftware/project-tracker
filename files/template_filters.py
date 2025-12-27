"""
Template Filters for CSI Scope Tags
Add these to app.py after the existing template filters
"""

# =====================================================================
# TAG CATEGORY MAPPING
# Maps tag names to CSS class names for coloring
# =====================================================================

TAG_CATEGORIES = {
    # Doors
    "Hollow Metal Doors": "doors",
    "Hollow Metal Frames": "doors",
    "Aluminum Doors": "doors",
    "Aluminum Frames": "doors",
    "Stainless Doors": "doors",
    "Wood Doors": "doors",
    "FRP Doors": "doors",
    "Composite Doors": "doors",
    "Access Doors": "doors",
    "Sliding Glass Doors": "doors",
    "Coiling Doors": "doors",
    "Overhead Coiling Doors": "doors",
    "Security Grilles": "doors",
    "Folding Doors": "doors",
    "Sectional Doors": "doors",
    "Traffic Doors": "doors",
    "Detention Doors": "doors",
    
    # Storefront
    "Storefront": "storefront",
    "Entrances": "storefront",
    "All-Glass Entrances": "storefront",
    "Automatic Entrances": "storefront",
    "Revolving Entrances": "storefront",
    "Balanced Doors": "storefront",
    
    # Curtain Wall
    "Curtain Wall": "curtainwall",
    "Structural Glass Curtain Wall": "curtainwall",
    "Sloped Curtain Wall": "curtainwall",
    "Unitized Curtain Wall": "curtainwall",
    "Point-Supported Curtain Wall": "curtainwall",
    "Window Wall": "curtainwall",
    "Translucent Assemblies": "curtainwall",
    
    # Windows
    "Windows": "windows",
    "Aluminum Windows": "windows",
    "Steel Windows": "windows",
    "Wood Windows": "windows",
    "Vinyl Windows": "windows",
    "Composite Windows": "windows",
    "Fiberglass Windows": "windows",
    
    # Skylights
    "Skylights": "skylights",
    "Roof Windows": "skylights",
    "Unit Skylights": "skylights",
    "Metal-Framed Skylights": "skylights",
    
    # Hardware
    "Door Hardware": "hardware",
    "Access Control": "hardware",
    "Window Hardware": "hardware",
    "Special Function Hardware": "hardware",
    "Hardware Accessories": "hardware",
    
    # Glazing
    "Glazing": "glazing",
    "Glass Glazing": "glazing",
    "Float Glass": "glazing",
    "Decorative Glass": "glazing",
    "Insulating Glass": "glazing",
    "Laminated Glass": "glazing",
    "Tempered Glass": "glazing",
    "Fire-Rated Glass": "glazing",
    "Spandrel Glass": "glazing",
    "Mirrors": "glazing",
    "Plastic Glazing": "glazing",
    "Window Film": "glazing",
    
    # Specialty (blast/ballistic/security)
    "Detention Windows": "specialty",
    "Security Windows": "specialty",
    "Blast-Resistant Windows": "specialty",
    "Bullet-Resistant Windows": "specialty",
    "Sound Control Windows": "specialty",
    "Pass Windows": "specialty",
    "Blast-Resistant Doors": "specialty",
    "Bullet-Resistant Doors": "specialty",
    "Vault Doors": "specialty",
    "Security Doors": "specialty",
    "Bullet-Resistant Glazing": "specialty",
    "Ballistic Glazing": "specialty",
    "Security Glazing": "specialty",
    "Electrochromic Glazing": "specialty",
    
    # Louvers
    "Louvers": "louvers",
    "Fixed Louvers": "louvers",
    "Operable Louvers": "louvers",
    "Equipment Screens": "louvers",
    "Vents": "louvers",
}


# =====================================================================
# SHORT NAMES
# Abbreviated names for compact display on cards
# =====================================================================

SHORT_NAMES = {
    "Hollow Metal Doors": "HM Doors",
    "Hollow Metal Frames": "HM Frames",
    "Aluminum Windows": "Alum Win",
    "Vinyl Windows": "Vinyl Win",
    "Wood Windows": "Wood Win",
    "Composite Windows": "Comp Win",
    "Fiberglass Windows": "FG Win",
    "Blast-Resistant Windows": "Blast Win",
    "Bullet-Resistant Windows": "Ballistic Win",
    "Blast-Resistant Doors": "Blast Doors",
    "Bullet-Resistant Doors": "Ballistic Doors",
    "Bullet-Resistant Glazing": "Ballistic Glass",
    "Curtain Wall": "CW",
    "Unitized Curtain Wall": "Unitized CW",
    "Structural Glass Curtain Wall": "Struct Glass CW",
    "Point-Supported Curtain Wall": "Point-Supp CW",
    "Door Hardware": "Hardware",
    "Access Control": "Access Ctrl",
    "Automatic Entrances": "Auto Entry",
    "Revolving Entrances": "Revolving",
    "All-Glass Entrances": "All-Glass",
    "Sliding Glass Doors": "Sliding Glass",
    "Coiling Doors": "Coiling",
    "Overhead Coiling Doors": "Overhead Coil",
    "Insulating Glass": "IG",
    "Laminated Glass": "Lam Glass",
    "Tempered Glass": "Tempered",
    "Fire-Rated Glass": "Fire Glass",
    "Metal-Framed Skylights": "Skylights",
    "Electrochromic Glazing": "Smart Glass",
    "Sound Control Windows": "Sound Win",
    "Sound Control Doors": "Sound Doors",
    "Translucent Assemblies": "Translucent",
}


# =====================================================================
# JINJA TEMPLATE FILTERS
# Add these with @app.template_filter decorator
# =====================================================================

# @app.template_filter('tag_category')
def tag_category_filter(tag_name):
    """
    Get CSS category class for a scope tag.
    
    Usage in template:
        <span class="tag scope {{ tag|tag_category }}">{{ tag }}</span>
    """
    return TAG_CATEGORIES.get(tag_name, 'other')


# @app.template_filter('tag_short')  
def tag_short_filter(tag_name):
    """
    Get shortened display name for a scope tag.
    
    Usage in template:
        <span class="tag">{{ tag|tag_short }}</span>
    """
    return SHORT_NAMES.get(tag_name, tag_name)


# =====================================================================
# HOW TO ADD TO app.py
# =====================================================================
"""
1. Copy TAG_CATEGORIES and SHORT_NAMES dicts to app.py (or import from csi_tagging)

2. Register template filters:

    @app.template_filter('tag_category')
    def tag_category_filter(tag_name):
        return TAG_CATEGORIES.get(tag_name, 'other')

    @app.template_filter('tag_short')
    def tag_short_filter(tag_name):
        return SHORT_NAMES.get(tag_name, tag_name)

3. Usage in templates:

    {% for tag in project.csi_tags[:3] %}
    <span class="tag scope {{ tag|tag_category }}">{{ tag|tag_short }}</span>
    {% endfor %}

4. The CSS classes (.scope.doors, .scope.windows, etc.) are defined in the
   dashboard_scope_tags.html file.
"""


# =====================================================================
# PYTHON HELPERS (for use in app.py routes)
# =====================================================================

def get_scope_tag_display(tags, max_tags=3):
    """
    Prepare scope tags for template display.
    
    Args:
        tags: List of tag strings
        max_tags: Maximum tags to show before "+N more"
    
    Returns:
        Dict with display info
    """
    if not tags:
        return {"tags": [], "overflow": 0}
    
    display_tags = []
    for tag in tags[:max_tags]:
        display_tags.append({
            "name": tag,
            "short": SHORT_NAMES.get(tag, tag),
            "category": TAG_CATEGORIES.get(tag, 'other')
        })
    
    return {
        "tags": display_tags,
        "overflow": max(0, len(tags) - max_tags)
    }


def categorize_scope_tags(tags):
    """
    Group tags by category for detailed display.
    
    Returns:
        Dict mapping category names to tag lists
    """
    by_category = {}
    for tag in tags:
        cat = TAG_CATEGORIES.get(tag, 'other')
        if cat not in by_category:
            by_category[cat] = []
        by_category[cat].append(tag)
    return by_category
