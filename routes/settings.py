"""
Settings Routes Blueprint

Handles user preferences including:
- Theme selection (brutalist, fruit, dialup, saas)
- Dark mode toggle
- API key management (OpenRouter, ProjectDog)
- Folder path configuration
- Email/file monitoring settings
- Notification preferences
"""

import os
import json
from pathlib import Path
from flask import Blueprint, jsonify, request, render_template

settings_bp = Blueprint('settings', __name__)

# =============================================================================
# CONFIGURATION
# =============================================================================

SETTINGS_FILE = Path(__file__).parent.parent / "static" / "data" / "user_settings.json"

# Valid theme options
VALID_THEMES = ['brutalist', 'fruit', 'dialup', 'saas']

# Default settings structure
DEFAULT_SETTINGS = {
    "theme": "brutalist",
    "dark_mode": False,
    "api_keys": {
        "openrouter": "",
        "projectdog_email": "",
        "projectdog_password": ""
    },
    "paths": {
        "bidding_folder": "",
        "archive_folder": "",
        "downloads_folder": ""
    },
    "monitoring": {
        "enabled": False,
        "watch_folder": "",
        "auto_classify": True,
        "check_interval_seconds": 60
    },
    "notifications": {
        "desktop_enabled": True,
        "email_enabled": False,
        "email_address": "",
        "notify_on_new_project": True,
        "notify_on_bid_deadline": True,
        "deadline_warning_days": 3
    },
    "display": {
        "items_per_page": 25,
        "default_view": "table",  # table, grid, list
        "show_archived": False,
        "compact_mode": False
    },
    "sync": {
        "auto_sync_enabled": True,
        "sync_interval_hours": 24,
        "last_sync": None
    }
}


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def deep_merge(base: dict, override: dict) -> dict:
    """
    Deep merge two dictionaries. Override values take precedence.
    Nested dicts are merged recursively.
    """
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def load_settings() -> dict:
    """
    Load settings from file, merged with defaults.
    Returns default settings if file doesn't exist or is invalid.
    """
    if SETTINGS_FILE.exists():
        try:
            with open(SETTINGS_FILE, 'r') as f:
                saved = json.load(f)
                return deep_merge(DEFAULT_SETTINGS.copy(), saved)
        except (json.JSONDecodeError, IOError) as e:
            print(f"Warning: Could not load settings file: {e}")
    return DEFAULT_SETTINGS.copy()


def save_settings(settings: dict) -> bool:
    """
    Save settings to file.
    Returns True on success, False on failure.
    """
    try:
        SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(SETTINGS_FILE, 'w') as f:
            json.dump(settings, f, indent=2, default=str)
        return True
    except (IOError, OSError) as e:
        print(f"Error saving settings: {e}")
        return False


def mask_sensitive_values(settings: dict) -> dict:
    """
    Mask sensitive values (API keys, passwords) for safe API responses.
    """
    masked = json.loads(json.dumps(settings))  # Deep copy
    api_keys = masked.get('api_keys', {})

    if api_keys.get('openrouter'):
        key = api_keys['openrouter']
        api_keys['openrouter'] = f"{'*' * 8}{key[-4:]}" if len(key) > 4 else '********'

    if api_keys.get('projectdog_password'):
        api_keys['projectdog_password'] = '********'

    return masked


def apply_env_overrides(settings: dict) -> None:
    """
    Apply settings to environment variables where needed.
    """
    api_keys = settings.get('api_keys', {})
    paths = settings.get('paths', {})

    if api_keys.get('openrouter'):
        os.environ['OPENROUTER_API_KEY'] = api_keys['openrouter']

    if api_keys.get('projectdog_email'):
        os.environ['PROJECTDOG_EMAIL'] = api_keys['projectdog_email']

    if api_keys.get('projectdog_password'):
        os.environ['PROJECTDOG_PASSWORD'] = api_keys['projectdog_password']

    if paths.get('bidding_folder'):
        os.environ['BIDDING_FOLDER'] = paths['bidding_folder']


# =============================================================================
# SETTINGS PAGE
# =============================================================================

@settings_bp.route('/settings')
def settings_page():
    """Render the settings page"""
    settings = load_settings()
    return render_template(
        'settings.html',
        settings=settings,
        themes=VALID_THEMES
    )


# =============================================================================
# FULL SETTINGS API
# =============================================================================

@settings_bp.route('/api/settings', methods=['GET'])
def api_get_settings():
    """
    Get all settings (with sensitive values masked).

    Returns:
        JSON with status and settings object
    """
    settings = load_settings()
    masked = mask_sensitive_values(settings)
    return jsonify({
        "status": "ok",
        "settings": masked,
        "available_themes": VALID_THEMES
    })


@settings_bp.route('/api/settings', methods=['POST'])
def api_update_settings():
    """
    Update multiple settings at once.

    Expects JSON body with settings to update.
    Performs deep merge with existing settings.

    Returns:
        JSON with status and message
    """
    data = request.get_json() or {}

    if not data:
        return jsonify({"error": "No settings provided"}), 400

    settings = load_settings()
    settings = deep_merge(settings, data)

    # Apply to environment
    apply_env_overrides(settings)

    if save_settings(settings):
        return jsonify({
            "status": "ok",
            "message": "Settings saved successfully"
        })

    return jsonify({"error": "Failed to save settings"}), 500


# =============================================================================
# THEME API
# =============================================================================

@settings_bp.route('/api/settings/theme', methods=['GET'])
def api_get_theme():
    """Get current theme and dark mode setting"""
    settings = load_settings()
    return jsonify({
        "status": "ok",
        "theme": settings.get('theme', 'brutalist'),
        "dark_mode": settings.get('dark_mode', False),
        "available_themes": VALID_THEMES
    })


@settings_bp.route('/api/settings/theme', methods=['POST'])
def api_set_theme():
    """
    Set theme and/or dark mode preference.

    Expects JSON body with:
        - theme (optional): Theme identifier
        - dark_mode (optional): Boolean for dark mode
    """
    data = request.get_json() or {}
    theme = data.get('theme')
    dark_mode = data.get('dark_mode')

    # Validate theme
    if theme is not None and theme not in VALID_THEMES:
        return jsonify({
            "error": f"Invalid theme. Must be one of: {VALID_THEMES}"
        }), 400

    settings = load_settings()

    if theme is not None:
        settings['theme'] = theme

    if dark_mode is not None:
        settings['dark_mode'] = bool(dark_mode)

    if save_settings(settings):
        return jsonify({
            "status": "ok",
            "theme": settings['theme'],
            "dark_mode": settings['dark_mode']
        })

    return jsonify({"error": "Failed to save theme preference"}), 500


# =============================================================================
# API KEYS
# =============================================================================

@settings_bp.route('/api/settings/api-keys', methods=['GET'])
def api_get_api_keys():
    """Get API keys (masked for security)"""
    settings = load_settings()
    masked = mask_sensitive_values(settings)
    return jsonify({
        "status": "ok",
        "api_keys": masked.get('api_keys', {}),
        "has_openrouter": bool(settings.get('api_keys', {}).get('openrouter')),
        "has_projectdog": bool(settings.get('api_keys', {}).get('projectdog_email'))
    })


@settings_bp.route('/api/settings/api-keys', methods=['POST'])
def api_set_api_keys():
    """
    Update API keys.

    Expects JSON body with any of:
        - openrouter: OpenRouter API key
        - projectdog_email: ProjectDog login email
        - projectdog_password: ProjectDog login password
    """
    data = request.get_json() or {}

    if not data:
        return jsonify({"error": "No API keys provided"}), 400

    settings = load_settings()

    # Update only provided keys (don't clear others)
    if 'openrouter' in data and data['openrouter']:
        settings['api_keys']['openrouter'] = data['openrouter']
        os.environ['OPENROUTER_API_KEY'] = data['openrouter']

    if 'projectdog_email' in data:
        settings['api_keys']['projectdog_email'] = data['projectdog_email']
        os.environ['PROJECTDOG_EMAIL'] = data['projectdog_email']

    if 'projectdog_password' in data and data['projectdog_password']:
        settings['api_keys']['projectdog_password'] = data['projectdog_password']
        os.environ['PROJECTDOG_PASSWORD'] = data['projectdog_password']

    if save_settings(settings):
        return jsonify({
            "status": "ok",
            "message": "API keys updated successfully"
        })

    return jsonify({"error": "Failed to save API keys"}), 500


# =============================================================================
# FOLDER PATHS
# =============================================================================

@settings_bp.route('/api/settings/paths', methods=['GET'])
def api_get_paths():
    """Get configured folder paths"""
    settings = load_settings()
    paths = settings.get('paths', {})

    # Check which paths exist
    path_status = {}
    for key, path in paths.items():
        if path:
            expanded = Path(path).expanduser()
            path_status[key] = {
                "path": str(expanded),
                "exists": expanded.exists(),
                "is_directory": expanded.is_dir() if expanded.exists() else None
            }
        else:
            path_status[key] = {"path": "", "exists": False}

    return jsonify({
        "status": "ok",
        "paths": path_status
    })


@settings_bp.route('/api/settings/paths', methods=['POST'])
def api_set_paths():
    """
    Update folder paths.

    Expects JSON body with any of:
        - bidding_folder: Path to bidding projects folder
        - archive_folder: Path for archived projects
        - downloads_folder: Path for downloaded documents

    Validates that paths exist before saving.
    """
    data = request.get_json() or {}

    if not data:
        return jsonify({"error": "No paths provided"}), 400

    settings = load_settings()
    errors = []

    for key in ['bidding_folder', 'archive_folder', 'downloads_folder']:
        if key in data:
            path_str = data[key]

            if path_str:
                path = Path(path_str).expanduser()

                # Validate path exists
                if not path.exists():
                    errors.append(f"{key}: Path does not exist: {path}")
                    continue

                if not path.is_dir():
                    errors.append(f"{key}: Path is not a directory: {path}")
                    continue

                settings['paths'][key] = str(path)

                # Update environment variable for bidding folder
                if key == 'bidding_folder':
                    os.environ['BIDDING_FOLDER'] = str(path)
            else:
                # Allow clearing a path
                settings['paths'][key] = ''

    if errors:
        return jsonify({
            "error": "Some paths could not be set",
            "details": errors
        }), 400

    if save_settings(settings):
        return jsonify({
            "status": "ok",
            "message": "Paths updated successfully"
        })

    return jsonify({"error": "Failed to save paths"}), 500


# =============================================================================
# MONITORING SETTINGS
# =============================================================================

@settings_bp.route('/api/settings/monitoring', methods=['GET'])
def api_get_monitoring():
    """Get email/file monitoring settings"""
    settings = load_settings()
    return jsonify({
        "status": "ok",
        "monitoring": settings.get('monitoring', {})
    })


@settings_bp.route('/api/settings/monitoring', methods=['POST'])
def api_set_monitoring():
    """
    Update monitoring settings.

    Expects JSON body with any of:
        - enabled: Boolean to enable/disable monitoring
        - watch_folder: Path to monitor for new files
        - auto_classify: Boolean to auto-classify incoming documents
        - check_interval_seconds: How often to check for new files
    """
    data = request.get_json() or {}
    settings = load_settings()

    valid_keys = ['enabled', 'watch_folder', 'auto_classify', 'check_interval_seconds']

    for key in valid_keys:
        if key in data:
            if key == 'watch_folder' and data[key]:
                # Validate watch folder exists
                path = Path(data[key]).expanduser()
                if not path.exists():
                    return jsonify({"error": f"Watch folder does not exist: {path}"}), 400
                settings['monitoring'][key] = str(path)
            elif key == 'check_interval_seconds':
                # Validate interval is reasonable
                interval = int(data[key])
                if interval < 10 or interval > 3600:
                    return jsonify({"error": "Check interval must be between 10 and 3600 seconds"}), 400
                settings['monitoring'][key] = interval
            else:
                settings['monitoring'][key] = data[key]

    if save_settings(settings):
        return jsonify({
            "status": "ok",
            "message": "Monitoring settings updated"
        })

    return jsonify({"error": "Failed to save monitoring settings"}), 500


# =============================================================================
# NOTIFICATION SETTINGS
# =============================================================================

@settings_bp.route('/api/settings/notifications', methods=['GET'])
def api_get_notifications():
    """Get notification settings"""
    settings = load_settings()
    return jsonify({
        "status": "ok",
        "notifications": settings.get('notifications', {})
    })


@settings_bp.route('/api/settings/notifications', methods=['POST'])
def api_set_notifications():
    """Update notification settings"""
    data = request.get_json() or {}
    settings = load_settings()

    valid_keys = [
        'desktop_enabled', 'email_enabled', 'email_address',
        'notify_on_new_project', 'notify_on_bid_deadline', 'deadline_warning_days'
    ]

    for key in valid_keys:
        if key in data:
            settings['notifications'][key] = data[key]

    if save_settings(settings):
        return jsonify({
            "status": "ok",
            "message": "Notification settings updated"
        })

    return jsonify({"error": "Failed to save notification settings"}), 500


# =============================================================================
# DISPLAY SETTINGS
# =============================================================================

@settings_bp.route('/api/settings/display', methods=['GET'])
def api_get_display():
    """Get display/UI settings"""
    settings = load_settings()
    return jsonify({
        "status": "ok",
        "display": settings.get('display', {})
    })


@settings_bp.route('/api/settings/display', methods=['POST'])
def api_set_display():
    """Update display/UI settings"""
    data = request.get_json() or {}
    settings = load_settings()

    valid_keys = ['items_per_page', 'default_view', 'show_archived', 'compact_mode']
    valid_views = ['table', 'grid', 'list']

    for key in valid_keys:
        if key in data:
            if key == 'default_view' and data[key] not in valid_views:
                return jsonify({"error": f"Invalid view. Must be one of: {valid_views}"}), 400
            if key == 'items_per_page':
                items = int(data[key])
                if items < 10 or items > 100:
                    return jsonify({"error": "Items per page must be between 10 and 100"}), 400
                settings['display'][key] = items
            else:
                settings['display'][key] = data[key]

    if save_settings(settings):
        return jsonify({
            "status": "ok",
            "message": "Display settings updated"
        })

    return jsonify({"error": "Failed to save display settings"}), 500


# =============================================================================
# RESET SETTINGS
# =============================================================================

@settings_bp.route('/api/settings/reset', methods=['POST'])
def api_reset_settings():
    """
    Reset all settings to defaults.

    Optionally accepts JSON body with:
        - section: Only reset a specific section (e.g., 'theme', 'api_keys')
    """
    data = request.get_json() or {}
    section = data.get('section')

    if section:
        # Reset only a specific section
        if section not in DEFAULT_SETTINGS:
            return jsonify({"error": f"Unknown settings section: {section}"}), 400

        settings = load_settings()
        settings[section] = DEFAULT_SETTINGS[section]

        if save_settings(settings):
            return jsonify({
                "status": "ok",
                "message": f"Reset {section} settings to defaults"
            })
    else:
        # Reset all settings
        if save_settings(DEFAULT_SETTINGS.copy()):
            return jsonify({
                "status": "ok",
                "message": "All settings reset to defaults"
            })

    return jsonify({"error": "Failed to reset settings"}), 500


# =============================================================================
# EXPORT/IMPORT SETTINGS
# =============================================================================

@settings_bp.route('/api/settings/export', methods=['GET'])
def api_export_settings():
    """
    Export settings as JSON for backup.
    Sensitive values are masked.
    """
    settings = load_settings()
    masked = mask_sensitive_values(settings)

    return jsonify({
        "status": "ok",
        "settings": masked,
        "note": "Sensitive values (API keys, passwords) are masked and will need to be re-entered after import"
    })


@settings_bp.route('/api/settings/import', methods=['POST'])
def api_import_settings():
    """
    Import settings from JSON.
    Merges with existing settings (does not overwrite API keys unless provided).
    """
    data = request.get_json()

    if not data or 'settings' not in data:
        return jsonify({"error": "No settings provided. Expected {settings: {...}}"}), 400

    imported = data['settings']
    current = load_settings()

    # Don't overwrite API keys with masked values
    if 'api_keys' in imported:
        for key in ['openrouter', 'projectdog_password']:
            if key in imported['api_keys'] and '*' in str(imported['api_keys'].get(key, '')):
                # Remove masked values
                del imported['api_keys'][key]

    # Merge imported with current
    merged = deep_merge(current, imported)

    if save_settings(merged):
        return jsonify({
            "status": "ok",
            "message": "Settings imported successfully"
        })

    return jsonify({"error": "Failed to import settings"}), 500
