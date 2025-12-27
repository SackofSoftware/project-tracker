"""
PDF Report Generator for Division 8 Analysis

Generates professional PDF reports from analysis data.
Uses WeasyPrint for HTML-to-PDF conversion.
"""

import logging
from datetime import datetime
from typing import Dict, Optional
from io import BytesIO

logger = logging.getLogger(__name__)

# Try to import WeasyPrint
try:
    from weasyprint import HTML, CSS
    WEASYPRINT_AVAILABLE = True
except ImportError:
    WEASYPRINT_AVAILABLE = False
    logger.warning("WeasyPrint not available. Install with: pip3 install weasyprint")


class AnalysisPDFGenerator:
    """Generate PDF reports from Division 8 analysis data."""

    def __init__(self):
        if not WEASYPRINT_AVAILABLE:
            raise ImportError(
                "WeasyPrint is required for PDF generation. "
                "Install with: pip3 install weasyprint"
            )

    def generate(self, project: dict, analysis: dict, project_name: str = None) -> bytes:
        """
        Generate PDF report and return as bytes.

        Args:
            project: Project metadata dict
            analysis: Analysis data dict
            project_name: Override project name

        Returns:
            PDF file as bytes
        """
        html_content = self._build_html(project, analysis, project_name)
        pdf_bytes = HTML(string=html_content).write_pdf()
        return pdf_bytes

    def _format_date(self, date_str: str) -> str:
        """Format ISO date string for display"""
        if not date_str:
            return "N/A"
        try:
            dt = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
            return dt.strftime("%B %d, %Y")
        except:
            return date_str

    def _build_html(self, project: dict, analysis: dict, project_name: str = None) -> str:
        """Build HTML content for PDF"""
        name = project_name or project.get('name') or project.get('title') or 'Unknown Project'
        location = ''
        if project.get('location'):
            loc = project['location']
            if isinstance(loc, dict):
                location = f"{loc.get('city', '')}, {loc.get('state', '')}"
            else:
                location = str(loc)
        elif project.get('address'):
            location = project['address']

        # Get metadata
        metadata = analysis.get('metadata', {})
        analyzed_date = self._format_date(metadata.get('analyzed_at', ''))
        confidence = metadata.get('confidence', 'unknown')

        # Get summary
        summary = analysis.get('summary', {})
        scope_desc = summary.get('scope_description', 'No summary available.')

        # Build sections
        doors_html = self._build_doors_section(analysis.get('doors', {}))
        windows_html = self._build_windows_section(analysis.get('windows', {}))
        storefronts_html = self._build_storefronts_section(
            analysis.get('storefronts', {}),
            analysis.get('curtain_wall', {})
        )
        hardware_html = self._build_hardware_section(analysis.get('hardware', {}))
        exclusions_html = self._build_exclusions_section(analysis.get('exclusions', []))

        return f'''<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <style>
        @page {{
            size: letter;
            margin: 0.75in;
            @bottom-center {{
                content: "Page " counter(page) " of " counter(pages);
                font-size: 9pt;
                color: #666;
            }}
        }}

        body {{
            font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif;
            font-size: 10pt;
            line-height: 1.4;
            color: #333;
        }}

        h1 {{
            font-size: 20pt;
            color: #1a365d;
            margin: 0 0 8px 0;
            border-bottom: 3px solid #1a365d;
            padding-bottom: 8px;
        }}

        h2 {{
            font-size: 14pt;
            color: #2d3748;
            margin: 24px 0 12px 0;
            border-bottom: 1px solid #e2e8f0;
            padding-bottom: 4px;
        }}

        h3 {{
            font-size: 11pt;
            color: #4a5568;
            margin: 16px 0 8px 0;
        }}

        .header {{
            margin-bottom: 24px;
        }}

        .header-meta {{
            display: flex;
            justify-content: space-between;
            font-size: 9pt;
            color: #666;
            margin-bottom: 16px;
        }}

        .project-info {{
            background: #f7fafc;
            border: 1px solid #e2e8f0;
            padding: 12px 16px;
            margin-bottom: 20px;
        }}

        .project-info strong {{
            font-size: 14pt;
            color: #1a365d;
        }}

        .project-info .location {{
            color: #666;
            margin-top: 4px;
        }}

        .summary-box {{
            background: #ebf8ff;
            border-left: 4px solid #3182ce;
            padding: 12px 16px;
            margin-bottom: 20px;
        }}

        .summary-box p {{
            margin: 0;
        }}

        .stats-grid {{
            display: flex;
            gap: 16px;
            margin-bottom: 24px;
        }}

        .stat-box {{
            flex: 1;
            text-align: center;
            padding: 12px;
            background: #f7fafc;
            border: 1px solid #e2e8f0;
        }}

        .stat-value {{
            font-size: 24pt;
            font-weight: bold;
            color: #1a365d;
        }}

        .stat-label {{
            font-size: 9pt;
            text-transform: uppercase;
            color: #666;
        }}

        .scope-section {{
            border: 1px solid #e2e8f0;
            margin-bottom: 16px;
            page-break-inside: avoid;
        }}

        .scope-header {{
            background: #edf2f7;
            padding: 8px 12px;
            font-weight: bold;
            font-size: 11pt;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}

        .scope-body {{
            padding: 12px 16px;
        }}

        table {{
            width: 100%;
            border-collapse: collapse;
            margin: 8px 0;
            font-size: 9pt;
        }}

        th, td {{
            border: 1px solid #e2e8f0;
            padding: 6px 8px;
            text-align: left;
        }}

        th {{
            background: #f7fafc;
            font-weight: 600;
        }}

        .badge {{
            display: inline-block;
            padding: 2px 8px;
            font-size: 8pt;
            font-weight: bold;
            text-transform: uppercase;
        }}

        .badge-specified {{
            background: #48bb78;
            color: white;
        }}

        .badge-not-specified {{
            background: #a0aec0;
            color: white;
        }}

        .badge-excluded {{
            background: #ed8936;
            color: white;
        }}

        .badge-confidence {{
            background: #3182ce;
            color: white;
        }}

        ul {{
            margin: 4px 0;
            padding-left: 20px;
        }}

        li {{
            margin-bottom: 4px;
        }}

        .field {{
            margin-bottom: 8px;
        }}

        .field-label {{
            font-size: 8pt;
            text-transform: uppercase;
            color: #666;
            margin-bottom: 2px;
        }}

        .field-value {{
            font-size: 10pt;
        }}

        .tags {{
            display: flex;
            flex-wrap: wrap;
            gap: 4px;
        }}

        .tag {{
            font-size: 8pt;
            padding: 2px 6px;
            background: #e2e8f0;
            border-radius: 2px;
        }}

        .footer {{
            margin-top: 32px;
            padding-top: 16px;
            border-top: 1px solid #e2e8f0;
            font-size: 8pt;
            color: #666;
            text-align: center;
        }}
    </style>
</head>
<body>
    <div class="header">
        <div class="header-meta">
            <span>Division 8 Scope Analysis Report</span>
            <span>Generated: {datetime.now().strftime("%B %d, %Y")}</span>
        </div>
        <h1>Division 8 Analysis</h1>
    </div>

    <div class="project-info">
        <strong>{name}</strong>
        {f'<div class="location">{location}</div>' if location else ''}
        <div style="margin-top: 8px; font-size: 9pt;">
            Analyzed: {analyzed_date} |
            Confidence: <span class="badge badge-confidence">{confidence}</span>
        </div>
    </div>

    <div class="summary-box">
        <p>{scope_desc}</p>
    </div>

    <div class="stats-grid">
        <div class="stat-box">
            <div class="stat-value">{summary.get('total_doors', '?')}</div>
            <div class="stat-label">Doors</div>
        </div>
        <div class="stat-box">
            <div class="stat-value">{summary.get('total_windows', '?')}</div>
            <div class="stat-label">Windows</div>
        </div>
        <div class="stat-box">
            <div class="stat-value">{'Yes' if summary.get('has_storefront') else 'No'}</div>
            <div class="stat-label">Storefront</div>
        </div>
        <div class="stat-box">
            <div class="stat-value">{'Yes' if summary.get('has_hardware') else 'No'}</div>
            <div class="stat-label">Hardware</div>
        </div>
    </div>

    <h2>Doors</h2>
    {doors_html}

    <h2>Windows</h2>
    {windows_html}

    <h2>Storefronts & Curtain Wall</h2>
    {storefronts_html}

    <h2>Door Hardware</h2>
    {hardware_html}

    {exclusions_html}

    <div class="footer">
        Generated by Project Tracker - Division 8 Analysis Module
    </div>
</body>
</html>'''

    def _build_doors_section(self, doors: dict) -> str:
        """Build doors HTML section"""
        sections = []

        # Metal Doors
        metal = doors.get('metal_doors_frames', {})
        specified = metal.get('specified', False)
        badge_class = 'badge-specified' if specified else 'badge-not-specified'
        badge_text = 'Specified' if specified else 'Not Specified'

        metal_html = f'''
        <div class="scope-section">
            <div class="scope-header">
                Metal Doors & Frames
                <span class="badge {badge_class}">{badge_text}</span>
            </div>
            <div class="scope-body">
                <div class="field">
                    <div class="field-label">Count</div>
                    <div class="field-value">{metal.get('count', 'not specified')}</div>
                </div>
                {self._build_tags_field('Types', metal.get('types', []))}
                {self._build_list_field('Manufacturers', metal.get('manufacturers', []))}
                {self._build_notes_field(metal.get('notes', []))}
            </div>
        </div>'''
        sections.append(metal_html)

        # Wood Doors (excluded)
        wood = doors.get('wood_doors', {})
        wood_html = f'''
        <div class="scope-section">
            <div class="scope-header">
                Wood Doors
                <span class="badge badge-excluded">Excluded</span>
            </div>
            <div class="scope-body">
                <em>{wood.get('exclusion_note', 'Division 6 - by others')}</em>
            </div>
        </div>'''
        sections.append(wood_html)

        # Aluminum Doors
        alum = doors.get('aluminum_doors', {})
        if alum.get('specified'):
            alum_html = f'''
            <div class="scope-section">
                <div class="scope-header">
                    Aluminum Doors
                    <span class="badge badge-specified">Specified</span>
                </div>
                <div class="scope-body">
                    <div class="field">
                        <div class="field-label">Count</div>
                        <div class="field-value">{alum.get('count', 'not specified')}</div>
                    </div>
                    {self._build_tags_field('Types', alum.get('types', []))}
                </div>
            </div>'''
            sections.append(alum_html)

        # Access Doors
        access = doors.get('access_doors', {})
        if access.get('specified'):
            access_html = f'''
            <div class="scope-section">
                <div class="scope-header">
                    Access Doors & Panels
                    <span class="badge badge-specified">Specified</span>
                </div>
                <div class="scope-body">
                    <div class="field">
                        <div class="field-label">Count</div>
                        <div class="field-value">{access.get('count', 'not specified')}</div>
                    </div>
                    {self._build_tags_field('Types', access.get('types', []))}
                </div>
            </div>'''
            sections.append(access_html)

        return '\n'.join(sections)

    def _build_windows_section(self, windows: dict) -> str:
        """Build windows HTML section"""
        sections = []

        for window_type, label in [
            ('aluminum_windows', 'Aluminum Windows'),
            ('vinyl_windows', 'Vinyl Windows')
        ]:
            win = windows.get(window_type, {})
            specified = win.get('specified', False)
            badge_class = 'badge-specified' if specified else 'badge-not-specified'
            badge_text = 'Specified' if specified else 'Not Specified'

            perf_html = ''
            if win.get('performance'):
                perf_items = [f'{k}: {v}' for k, v in win['performance'].items()]
                perf_html = f'''
                <div class="field">
                    <div class="field-label">Performance</div>
                    <div class="field-value">{', '.join(perf_items)}</div>
                </div>'''

            win_html = f'''
            <div class="scope-section">
                <div class="scope-header">
                    {label}
                    <span class="badge {badge_class}">{badge_text}</span>
                </div>
                <div class="scope-body">
                    <div class="field">
                        <div class="field-label">Count</div>
                        <div class="field-value">{win.get('count', 'not specified')}</div>
                    </div>
                    {self._build_tags_field('Types', win.get('types', []))}
                    {self._build_list_field('Manufacturers', win.get('manufacturers', []))}
                    {perf_html}
                    {self._build_notes_field(win.get('notes', []))}
                </div>
            </div>'''
            sections.append(win_html)

        return '\n'.join(sections)

    def _build_storefronts_section(self, storefronts: dict, curtain_wall: dict) -> str:
        """Build storefronts HTML section"""
        sections = []

        for scope, label in [(storefronts, 'Storefront'), (curtain_wall, 'Curtain Wall')]:
            specified = scope.get('specified', False)
            badge_class = 'badge-specified' if specified else 'badge-not-specified'
            badge_text = 'Specified' if specified else 'Not Specified'

            sf_html = ''
            if scope.get('sf_estimate'):
                sf_html = f'''
                <div class="field">
                    <div class="field-label">Estimated SF</div>
                    <div class="field-value" style="font-size: 14pt; font-weight: bold;">{scope['sf_estimate']} SF</div>
                </div>'''

            section_html = f'''
            <div class="scope-section">
                <div class="scope-header">
                    {label}
                    <span class="badge {badge_class}">{badge_text}</span>
                </div>
                <div class="scope-body">
                    {sf_html}
                    {self._build_tags_field('Systems', scope.get('systems', []))}
                    {self._build_list_field('Manufacturers', scope.get('manufacturers', []))}
                    {self._build_notes_field(scope.get('notes', []))}
                </div>
            </div>'''
            sections.append(section_html)

        return '\n'.join(sections)

    def _build_hardware_section(self, hardware: dict) -> str:
        """Build hardware HTML section"""
        specified = hardware.get('specified', False)
        badge_class = 'badge-specified' if specified else 'badge-not-specified'
        badge_text = 'Specified' if specified else 'Not Specified'

        return f'''
        <div class="scope-section">
            <div class="scope-header">
                Door Hardware
                <span class="badge {badge_class}">{badge_text}</span>
            </div>
            <div class="scope-body">
                {self._build_tags_field('Hardware Sets', hardware.get('hardware_sets', []))}
                {self._build_list_field('Manufacturers', hardware.get('manufacturers', []))}
                {self._build_tags_field('Lockset Types', hardware.get('lockset_types', []))}
                <div class="field">
                    <div class="field-label">Finish</div>
                    <div class="field-value">{hardware.get('finish', 'not specified')}</div>
                </div>
                <div class="field">
                    <div class="field-label">Access Control</div>
                    <div class="field-value">{'Yes' if hardware.get('access_control') else 'No'}</div>
                </div>
                {self._build_notes_field(hardware.get('notes', []))}
            </div>
        </div>'''

    def _build_exclusions_section(self, exclusions: list) -> str:
        """Build exclusions HTML section"""
        if not exclusions:
            return ''

        items = '\n'.join(f'<li>{exc}</li>' for exc in exclusions)
        return f'''
        <h2>Exclusions</h2>
        <div class="scope-section">
            <div class="scope-header" style="background: #fed7d7;">
                Items Excluded from Division 8 Scope
            </div>
            <div class="scope-body">
                <ul>
                    {items}
                </ul>
            </div>
        </div>'''

    def _build_tags_field(self, label: str, items: list) -> str:
        """Build a field with tag-style items"""
        if not items:
            return ''
        tags = ' '.join(f'<span class="tag">{item}</span>' for item in items)
        return f'''
        <div class="field">
            <div class="field-label">{label}</div>
            <div class="tags">{tags}</div>
        </div>'''

    def _build_list_field(self, label: str, items: list) -> str:
        """Build a field with comma-separated list"""
        if not items:
            return ''
        return f'''
        <div class="field">
            <div class="field-label">{label}</div>
            <div class="field-value">{', '.join(str(i) for i in items)}</div>
        </div>'''

    def _build_notes_field(self, notes: list) -> str:
        """Build a notes field"""
        if not notes:
            return ''
        items = '\n'.join(f'<li>{note[:200]}</li>' for note in notes[:5])
        return f'''
        <div class="field">
            <div class="field-label">Notes</div>
            <ul>{items}</ul>
        </div>'''
