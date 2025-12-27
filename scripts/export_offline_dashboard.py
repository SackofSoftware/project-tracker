#!/usr/bin/env python3
"""
Generate a fully self-contained offline HTML snapshot of the dashboard.

The output file (offline_dashboard.html) inlines CSS, JS, logos, and embeds
the current project data so it can be opened directly on a phone or tablet
without running the Flask server or accessing PDFs.
"""

import base64
import json
import sys
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT))

from jinja2 import Environment, FileSystemLoader, select_autoescape

from utils import (
    get_all_projects,
    get_bidding_reader,
    get_status_tracker,
    _last_refresh,
)

TEMPLATES_DIR = ROOT / "templates"
STATIC_DIR = ROOT / "static"

# Replica of template filters (avoids importing full app module)
TAG_CATEGORIES = {
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
    "Storefront": "storefront",
    "Entrances": "storefront",
    "All-Glass Entrances": "storefront",
    "Automatic Entrances": "storefront",
    "Revolving Entrances": "storefront",
    "Balanced Doors": "storefront",
    "Curtain Wall": "curtainwall",
    "Structural Glass Curtain Wall": "curtainwall",
    "Sloped Curtain Wall": "curtainwall",
    "Unitized Curtain Wall": "curtainwall",
    "Point-Supported Curtain Wall": "curtainwall",
    "Window Wall": "curtainwall",
    "Translucent Assemblies": "curtainwall",
    "Windows": "windows",
    "Aluminum Windows": "windows",
    "Steel Windows": "windows",
    "Wood Windows": "windows",
    "Vinyl Windows": "windows",
    "Composite Windows": "windows",
    "Fiberglass Windows": "windows",
    "Skylights": "skylights",
    "Roof Windows": "skylights",
    "Unit Skylights": "skylights",
    "Door Hardware": "hardware",
    "Access Control": "hardware",
    "Window Hardware": "hardware",
    "Special Function Hardware": "hardware",
    "Hardware Accessories": "hardware",
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
    "Detention Windows": "specialty",
    "Security Windows": "specialty",
    "Blast-Resistant Windows": "specialty",
    "Bullet-Resistant Windows": "specialty",
    "Sound Control Windows": "specialty",
    "Pass Windows": "specialty",
    "Blast-Resistant Doors": "specialty",
    "Bullet-Resistant Doors": "specialty",
    "Bullet-Resistant Glazing": "specialty",
    "Ballistic Glazing": "specialty",
    "Security Glazing": "specialty",
    "Electrochromic Glazing": "specialty",
    "Louvers": "louvers",
    "Fixed Louvers": "louvers",
    "Operable Louvers": "louvers",
    "Equipment Screens": "louvers",
    "Vents": "louvers",
}

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
    "Metal-Framed Skylights": "Skylights",
    "Electrochromic Glazing": "Smart Glass",
    "Sound Control Windows": "Sound Win",
    "Translucent Assemblies": "Translucent",
}


def format_date_filter(date_str):
    """Convert various date formats to mm/dd/yy for templates."""
    from datetime import datetime

    if not date_str or date_str == "None" or date_str == "":
        return ""
    try:
        if isinstance(date_str, str) and "-" in date_str and len(date_str) >= 10:
            parts = date_str[:10].split("-")
            if len(parts) == 3 and len(parts[0]) == 4:
                return f"{parts[1]}/{parts[2]}/{parts[0][2:]}"
        if isinstance(date_str, str) and "/" in date_str:
            parts = date_str.split("/")
            if len(parts) == 3:
                if len(parts[2]) == 4:
                    return f"{parts[0]}/{parts[1]}/{parts[2][2:]}"
                if len(parts[2]) == 2:
                    return date_str
        if isinstance(date_str, datetime):
            return date_str.strftime("%m/%d/%y")
        return str(date_str)
    except Exception:
        return str(date_str)


def tag_category_filter(tag_name):
    """Match tag to CSS category class."""
    return TAG_CATEGORIES.get(tag_name, "other")


def tag_short_filter(tag_name):
    """Short display label for tags."""
    return SHORT_NAMES.get(tag_name, tag_name)


def _data_uri(path: Path) -> str:
    """Return a data URI for an image file."""
    mime = "image/png" if path.suffix.lower() == ".png" else "image/jpeg"
    encoded = base64.b64encode(path.read_bytes()).decode()
    return f"data:{mime};base64,{encoded}"


def _build_inline_js(projects_json: str) -> str:
    """Minimal JS to support filtering/sorting/offline detail in snapshot."""
    js = textwrap.dedent(
        """
        (() => {
          const OFFLINE_PROJECTS = __PROJECTS_JSON__;
          const projectMap = {};
          OFFLINE_PROJECTS.forEach((p) => {
            const key = p.project_code || p.id || p.folder || '';
            if (key) projectMap[String(key)] = p;
          });

          const offlineNotice = (action) => () => alert(`${action} is disabled in the offline snapshot.`);

          // Stub networked actions
          window.refreshProjects = offlineNotice('Refresh');
          window.startBatchScan = offlineNotice('Batch scan');
          window.triggerSync = offlineNotice('Sync');
          window.autoArchiveOld = offlineNotice('Auto-archive');
          window.downloadDocs = offlineNotice('Download');
          window.downloadAllDocs = offlineNotice('Batch download');
          window.showStatusModal = offlineNotice('Status editor');
          window.closeModal = () => {};
          window.addTag = offlineNotice('Tag edit');
          window.addNote = offlineNotice('Note edit');
          window.saveStatus = offlineNotice('Status save');
          window.showLinkModal = offlineNotice('PlanHub link');
          window.closeLinkModal = () => {};
          window.unlinkProject = offlineNotice('Unlink');
          window.saveLink = offlineNotice('Link save');

          // Intercept fetch for intake badge to avoid network calls
          const originalFetch = window.fetch;
          window.fetch = (...args) => {
            const url = args[0];
            if (typeof url === 'string' && url.includes('/api/intake/pending')) {
              return Promise.resolve({
                json: async () => ({ folders: [] }),
              });
            }
            return originalFetch ? originalFetch(...args) : Promise.resolve({ json: async () => ({}) });
          };

          const formatDate = (dateStr) => {
            if (!dateStr || dateStr === 'None' || dateStr === '') return '';
            let d;
            if (/^\\d{4}-\\d{2}-\\d{2}/.test(dateStr)) {
              const parts = dateStr.split('-');
              d = new Date(parts[0], parts[1] - 1, parts[2]);
            } else if (dateStr.includes('/')) {
              const parts = dateStr.split('/');
              if (parts.length === 3) {
                if (parts[2].length === 2) return dateStr.replace(/(\\d{2})\\/(\\d{2})\\/(\\d{2})/, '$1/$2/$3');
                d = new Date(parts[2], parts[0] - 1, parts[1]);
              }
            } else {
              d = new Date(dateStr);
            }
            if (!d || isNaN(d.getTime())) return dateStr;
            const month = String(d.getMonth() + 1).padStart(2, '0');
            const day = String(d.getDate()).padStart(2, '0');
            const year = String(d.getFullYear()).slice(-2);
            return `${month}/${day}/${year}`;
          };

          const parseDateValue = (dateStr) => {
            if (!dateStr || dateStr === 'None' || dateStr === '') return null;
            const parsed = Date.parse(dateStr);
            if (!isNaN(parsed)) return parsed;
            const parts = dateStr.split('/');
            if (parts.length === 3) {
              const d = new Date(parts[2], parts[0] - 1, parts[1]);
              if (!isNaN(d.getTime())) return d.getTime();
            }
            const iso = dateStr.split('-');
            if (iso.length === 3) {
              const d = new Date(iso[0], iso[1] - 1, iso[2]);
              if (!isNaN(d.getTime())) return d.getTime();
            }
            return null;
          };

          window.setView = (view) => {
            const grid = document.getElementById('projectGrid');
            const gridBtn = document.getElementById('gridViewBtn');
            const listBtn = document.getElementById('listViewBtn');
            if (!grid) return;
            if (view === 'list') {
              grid.classList.add('list-view');
              grid.classList.remove('grid-view');
              gridBtn?.classList.remove('active');
              listBtn?.classList.add('active');
            } else {
              grid.classList.remove('list-view');
              grid.classList.add('grid-view');
              gridBtn?.classList.add('active');
              listBtn?.classList.remove('active');
            }
            localStorage.setItem('projectView', view);
          };

          window.sortProjects = () => {
            const sortBy = document.getElementById('sortBy')?.value;
            const grid = document.getElementById('projectGrid');
            if (!grid || !sortBy) return;
            const cards = Array.from(grid.querySelectorAll('.project-card'));
            cards.sort((a, b) => {
              let valA, valB;
              switch (sortBy) {
                case 'bid_date_asc':
                case 'bid_date_desc':
                  valA = parseDateValue(a.dataset.bidDate);
                  valB = parseDateValue(b.dataset.bidDate);
                  if (!valA && valB) return 1;
                  if (valA && !valB) return -1;
                  if (!valA && !valB) return 0;
                  return sortBy === 'bid_date_asc' ? valA - valB : valB - valA;
                case 'updated_desc':
                  valA = parseDateValue(a.dataset.dateUpdated) || parseDateValue(a.dataset.dateAdded) || 0;
                  valB = parseDateValue(b.dataset.dateUpdated) || parseDateValue(b.dataset.dateAdded) || 0;
                  return valB - valA;
                case 'added_desc':
                  valA = parseDateValue(a.dataset.dateAdded) || 0;
                  valB = parseDateValue(b.dataset.dateAdded) || 0;
                  return valB - valA;
                case 'added_asc':
                  valA = parseDateValue(a.dataset.dateAdded) || Infinity;
                  valB = parseDateValue(b.dataset.dateAdded) || Infinity;
                  return valA - valB;
                case 'title_asc':
                  valA = (a.dataset.title || '').toLowerCase();
                  valB = (b.dataset.title || '').toLowerCase();
                  return valA.localeCompare(valB);
                case 'title_desc':
                  valA = (a.dataset.title || '').toLowerCase();
                  valB = (b.dataset.title || '').toLowerCase();
                  return valB.localeCompare(valA);
                default:
                  return 0;
              }
            });
            cards.forEach((card) => grid.appendChild(card));
          };

          window.filterProjects = () => {
            const sourceFilter = document.getElementById('sourceFilter')?.value || 'all';
            const typeFilter = document.getElementById('typeFilter')?.value || 'all';
            const searchFilter = (document.getElementById('searchFilter')?.value || '').toLowerCase();
            const stateFilter = document.getElementById('stateFilter')?.value || 'all';
            const statusFilter = document.getElementById('statusFilter')?.value || 'all';
            const scopeFilter = document.getElementById('scopeFilter')?.value || 'all';
            const archivedFilter = document.getElementById('archivedFilter')?.value || 'active';

            const cards = document.querySelectorAll('#projectGrid .project-card');
            let visible = 0;
            cards.forEach((card) => {
              const source = card.dataset.source || '';
              const type = card.dataset.type || '';
              const title = card.dataset.title || '';
              const folder = card.dataset.folder || '';
              const state = card.dataset.state || '';
              const decision = card.dataset.decision || '';
              const hasEstimate = card.dataset.hasEstimate === 'true';
              const hasProposal = card.dataset.hasProposal === 'true';
              const isArchived = card.dataset.archived === 'true';
              const scopes = card.dataset.scope ? card.dataset.scope.toLowerCase() : '';

              let show = true;
              if (archivedFilter === 'active' && isArchived) show = false;
              else if (archivedFilter === 'archived' && !isArchived) show = false;

              if (sourceFilter !== 'all' && source !== sourceFilter) show = false;
              if (typeFilter !== 'all' && type !== typeFilter) show = false;
              if (stateFilter !== 'all' && state !== stateFilter) show = false;

              if (statusFilter !== 'all') {
                if (statusFilter === 'has_estimate' && !hasEstimate) show = false;
                else if (statusFilter === 'has_proposal' && !hasProposal) show = false;
                else if (['bid', 'no_bid', 'pending', 'gc_awarded', 'awarded', 'lost'].includes(statusFilter) && decision !== statusFilter) {
                  show = false;
                }
              }

              if (scopeFilter !== 'all') {
                if (!scopes.split(',').map((s) => s.trim().toLowerCase()).filter(Boolean).includes(scopeFilter.toLowerCase())) {
                  show = false;
                }
              }

              if (searchFilter) {
                const haystack = `${title} ${folder}`.toLowerCase();
                if (!haystack.includes(searchFilter)) show = false;
              }

              card.style.display = show ? '' : 'none';
              if (show) visible += 1;
            });

            const countEl = document.querySelector('#projectGrid')?.closest('.section')?.querySelector('.count');
            if (countEl) {
              const total = document.querySelectorAll('#projectGrid .project-card').length;
              countEl.textContent = `(${visible}/${total})`;
            }
          };

          const populateScopeFilter = () => {
            const select = document.getElementById('scopeFilter');
            if (!select) return;
            const counts = {};
            document.querySelectorAll('#projectGrid .project-card').forEach((card) => {
              const scopes = card.dataset.scope ? card.dataset.scope.split(',') : [];
              scopes.forEach((scope) => {
                const key = scope.trim();
                if (!key) return;
                counts[key] = (counts[key] || 0) + 1;
              });
            });
            Object.entries(counts)
              .sort((a, b) => b[1] - a[1])
              .forEach(([scope, count]) => {
                const opt = document.createElement('option');
                opt.value = scope;
                opt.textContent = `${scope} (${count})`;
                select.appendChild(opt);
              });
          };

          const openOfflineDetail = (projectId) => {
            const project = projectMap[projectId];
            if (!project) return;

            let modal = document.getElementById('offlineDetailModal');
            if (!modal) {
              modal = document.createElement('div');
              modal.id = 'offlineDetailModal';
              modal.className = 'offline-detail-backdrop';
              modal.innerHTML = `
                <div class="offline-detail">
                  <div class="offline-detail-header">
                    <h2 id="offlineTitle"></h2>
                    <button class="close-btn" id="offlineCloseBtn">&times;</button>
                  </div>
                  <div class="offline-detail-body">
                    <div class="offline-meta" id="offlineMeta"></div>
                    <p class="offline-summary" id="offlineSummary"></p>
                    <div class="offline-tags" id="offlineTags"></div>
                    <div class="offline-gc" id="offlineGC"></div>
                    <div class="offline-scope" id="offlineScope"></div>
                  </div>
                </div>`;
              document.body.appendChild(modal);
              modal.addEventListener('click', (e) => {
                if (e.target.id === 'offlineDetailModal') modal.style.display = 'none';
              });
              modal.querySelector('#offlineCloseBtn').onclick = () => modal.style.display = 'none';
            }

            const title = project.title || project.folder || 'Project';
            const location = project.location;
            const bidDate = project.bid_date || project.schedule?.bid_date || '';
            const owner = project.owner || '';
            const architect = project.architect || '';
            const summary = project.division_8?.scope_summary || project.rag_analysis?.scope_summary || '';
            const scopeTags = project.csi_tags || [];
            const gcs = project.general_contractors || [];
            const planhub = project.planhub_urls || {};

            modal.querySelector('#offlineTitle').textContent = title;

            const metaParts = [];
            if (project.source) metaParts.push(project.source === 'projectdog' ? 'ProjectDog' : project.source === 'planhub' ? 'PlanHub' : 'Local');
            if (location?.city) metaParts.push(`${location.city}${location.state ? ', ' + location.state : ''}`);
            else if (location?.raw) metaParts.push(location.raw);
            if (bidDate) metaParts.push(`Bid: ${formatDate(bidDate)}`);
            if (owner) metaParts.push(`Owner: ${owner}`);
            if (architect) metaParts.push(`Architect: ${architect}`);
            modal.querySelector('#offlineMeta').textContent = metaParts.join(' • ');

            modal.querySelector('#offlineSummary').textContent = summary || 'No scope summary available.';

            const tagsEl = modal.querySelector('#offlineTags');
            tagsEl.innerHTML = '';
            scopeTags.forEach((t) => {
              const span = document.createElement('span');
              span.className = 'status-tag custom';
              span.textContent = t;
              tagsEl.appendChild(span);
            });

            const gcEl = modal.querySelector('#offlineGC');
            gcEl.innerHTML = '';
            if (gcs.length > 0) {
              const titleEl = document.createElement('div');
              titleEl.className = 'offline-subtitle';
              titleEl.textContent = 'General Contractors';
              gcEl.appendChild(titleEl);
              gcs.slice(0, 6).forEach((gc) => {
                const row = document.createElement('div');
                row.className = 'offline-row';
                row.textContent = `${gc.name || ''}${gc.phone ? ' • ' + gc.phone : ''}${gc.email ? ' • ' + gc.email : ''}`;
                gcEl.appendChild(row);
              });
            }

            const scopeEl = modal.querySelector('#offlineScope');
            scopeEl.innerHTML = '';
            const doorCounts = project.division_8?.rag_doors || project.rag_analysis?.doors;
            const winCounts = project.division_8?.rag_windows || project.rag_analysis?.windows;
            if (doorCounts || winCounts) {
              const titleEl = document.createElement('div');
              titleEl.className = 'offline-subtitle';
              titleEl.textContent = 'Extracted Quantities';
              scopeEl.appendChild(titleEl);
              if (doorCounts?.metal_count !== undefined) {
                const row = document.createElement('div');
                row.className = 'offline-row';
                row.textContent = `Metal doors: ${doorCounts.metal_count}`;
                scopeEl.appendChild(row);
              }
              if (winCounts?.count !== undefined) {
                const row = document.createElement('div');
                row.className = 'offline-row';
                row.textContent = `Windows: ${winCounts.count}`;
                scopeEl.appendChild(row);
              }
            }

            const links = [];
            if (project.planhub_id && planhub.project_info) links.push(`PlanHub info: ${planhub.project_info}`);
            if (project.url) links.push(`ProjectDog: ${project.url}`);
            if (links.length > 0) {
              const linksEl = document.createElement('div');
              linksEl.className = 'offline-row';
              linksEl.innerHTML = links.map((l) => `<div>${l}</div>`).join('');
              scopeEl.appendChild(linksEl);
            }

            modal.style.display = 'flex';
          };

          document.addEventListener('DOMContentLoaded', () => {
            const brand = document.querySelector('.header-brand');
            if (brand) {
              const pill = document.createElement('span');
              pill.className = 'offline-pill';
              pill.textContent = 'Offline snapshot';
              brand.appendChild(pill);
            }

            populateScopeFilter();
            const savedView = localStorage.getItem('projectView') || 'grid';
            setView(savedView);
            document.querySelectorAll('.project-card').forEach((card) => {
              const id = card.dataset.id || card.dataset.folder;
              card.onclick = (e) => {
                e.preventDefault();
                e.stopPropagation();
                openOfflineDetail(id);
              };
              card.style.cursor = 'pointer';
            });
            sortProjects();
            filterProjects();
            document.querySelectorAll('.bid-date').forEach((el) => {
              const text = el.textContent;
              const match = text.match(/Bid:\\s*(.+)/);
              if (match) el.textContent = 'Bid: ' + formatDate(match[1]);
            });
          });
        })();
        """
    ).strip()
    return js.replace("__PROJECTS_JSON__", projects_json)


def main() -> None:
    """Render the dashboard template to a single offline HTML file."""
    env = Environment(
        loader=FileSystemLoader(TEMPLATES_DIR),
        autoescape=select_autoescape(["html", "xml"]),
    )
    env.filters["format_date"] = format_date_filter
    env.filters["tag_category"] = tag_category_filter
    env.filters["tag_short"] = tag_short_filter
    env.globals["url_for"] = lambda endpoint, filename: f"static/{filename}"

    template = env.get_template("dashboard.html")

    projects = get_all_projects()
    bidding_reader = get_bidding_reader()
    status_tracker = get_status_tracker()

    stats = bidding_reader.get_summary_stats()
    upcoming = bidding_reader.get_upcoming_bids(30)
    tracking_stats = status_tracker.get_summary_stats()

    projectdog_projects = [p for p in projects if p.get("source") == "projectdog"]
    planhub_projects = [p for p in projects if p.get("source") == "planhub"]
    local_projects = [p for p in projects if p.get("source") in ("local_bidding", "local_extracted", "local_folder")]
    dcam_projects = [p for p in projectdog_projects if p.get("is_dcam")]
    rfq_projects = [p for p in projectdog_projects if p.get("is_rfq")]
    regular_projects = [p for p in projectdog_projects if not p.get("is_dcam") and not p.get("is_rfq")]

    rendered = template.render(
        projects=projects,
        local_projects=local_projects,
        projectdog_projects=projectdog_projects,
        planhub_projects=planhub_projects,
        dcam_projects=dcam_projects,
        rfq_projects=rfq_projects,
        regular_projects=regular_projects,
        upcoming_bids=upcoming[:10],
        stats=stats,
        tracking_stats=tracking_stats,
        last_refresh=_last_refresh,
        sync_status={"sync_in_progress": False, "next_run": None, "stage": "offline"},
    )

    css = (STATIC_DIR / "css" / "style.css").read_text()
    css += textwrap.dedent(
        """
        /* Offline snapshot overrides */
        .card-actions, .btn-download { display: none !important; }
        #statusModal, #linkModal { display: none !important; }
        .project-card { cursor: default; }
        .offline-pill {
            display: inline-block;
            margin-left: 0.75rem;
            padding: 0.35rem 0.6rem;
            font-size: 0.85rem;
            border: 2px solid #000;
            background: #fef08a;
            box-shadow: 4px 4px 0px #000000;
        }
        .offline-detail-backdrop {
            position: fixed;
            top: 0; left: 0; right: 0; bottom: 0;
            background: rgba(0,0,0,0.4);
            display: none;
            align-items: center;
            justify-content: center;
            z-index: 9999;
            padding: 1rem;
        }
        .offline-detail {
            background: var(--card-bg);
            border: 3px solid var(--border);
            box-shadow: var(--shadow);
            max-width: 720px;
            width: 100%;
            padding: 1rem 1.25rem;
            overflow-y: auto;
            max-height: 90vh;
        }
        .offline-detail-header {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 1rem;
            margin-bottom: 0.75rem;
        }
        .offline-detail-body {
            display: flex;
            flex-direction: column;
            gap: 0.75rem;
        }
        .offline-subtitle {
            font-weight: bold;
            margin-bottom: 0.25rem;
        }
        .offline-row {
            font-size: 0.95rem;
            margin-bottom: 0.25rem;
        }
        .offline-tags .status-tag { margin-right: 0.25rem; margin-bottom: 0.25rem; display: inline-block; }
        .offline-summary { font-size: 0.98rem; }
        .offline-meta { font-size: 0.9rem; color: var(--text-muted); }
        @media (max-width: 900px) {
            .header { flex-direction: column; gap: 0.75rem; }
            .header-content { flex-direction: column; align-items: flex-start; gap: 0.5rem; }
            .stats-grid { grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); }
            .filters { grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); }
        }
        """
    )

    logos = {
        "cws": _data_uri(STATIC_DIR / "images" / "cws-logo.png"),
        "projectdog": _data_uri(STATIC_DIR / "images" / "projectdoglogo.png"),
    }

    offline_js = _build_inline_js(json.dumps(projects, default=str))

    html = rendered

    # Inline CSS/JS and images
    html = html.replace('<link rel="stylesheet" href="static/css/style.css">', f"<style>\n{css}\n</style>")
    html = html.replace('src="static/images/cws-logo.png"', f'src="{logos["cws"]}"')
    html = html.replace('src="static/images/projectdoglogo.png"', f'src="{logos["projectdog"]}"')
    html = html.replace(
        '<script src="static/js/dashboard.js"></script>',
        f"<script>\n{offline_js}\n</script>",
    )

    output_path = ROOT / "offline_dashboard.html"
    output_path.write_text(html)
    print(f"Offline dashboard saved to {output_path}")


if __name__ == "__main__":
    main()
