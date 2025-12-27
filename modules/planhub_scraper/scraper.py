#!/usr/bin/env python3
"""
PlanHub Scraper with Auto-Discovery and Resume Support

Discovers leads from paginated list, skips locked projects, extracts all data.

Usage:
    python scraper.py login      - Manual login to save session cookies
    python scraper.py discover   - Just run lead discovery phase
    python scraper.py run        - Full scrape (discover + scrape leads)
    python scraper.py gui        - Start with GUI
    python scraper.py status     - Show progress statistics
    python scraper.py reset      - Reset discovery to start over
    python scraper.py vision     - Test vision model with screenshots
"""
import sys
import time
import json
from pathlib import Path
from typing import Dict, Any, Optional, List
from datetime import datetime

from playwright.sync_api import sync_playwright, Browser, BrowserContext, Page, TimeoutError as PlaywrightTimeout

from .config import (
    SESSION_FILE, SESSION_DIR, LOGIN_URL, LEADS_LIST_URL, BASE_URL,
    REQUEST_DELAY, HEADLESS, PAGE_LOAD_TIMEOUT, ELEMENT_WAIT_TIMEOUT,
    HTML_FALLBACK_DIR, MAX_RETRIES,
    LEADS_LIST_SELECTORS, TAB_SELECTORS, PROJECT_INFO_SELECTORS,
    PROJECT_FILES_SELECTORS, GC_SELECTORS, MARKET_INTEL_SELECTORS,
    QA_SELECTORS, MATERIAL_SELECTORS, LOGIN_VALIDATION,
    extract_lead_id, get_project_tab_url, is_login_redirect,
    VISION_ENABLED, VISION_USE_LOCAL, VISION_DEBUG_SCREENSHOTS, SCREENSHOT_DIR
)
from .db import Database, Lead, init_database, show_stats

# Vision helper (optional)
try:
    from .vision_helper import (
        take_screenshot, analyze_lead_list, wait_for_visual_load,
        check_page_loaded, call_vision_model, crop_image, crop_to_element,
        LEAD_LIST_PROMPT, CROP_REGIONS
    )
    VISION_AVAILABLE = True
except ImportError:
    VISION_AVAILABLE = False
    print("Note: vision_helper not available, vision features disabled")


class PlanHubScraper:
    def __init__(self, gui_callback=None):
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        self.db: Optional[Database] = None
        self.gui_callback = gui_callback
        self.running = True
        self.is_paused = False

    def update_gui(self, **kwargs):
        """Send update to GUI if callback is set"""
        if self.gui_callback:
            self.gui_callback(**kwargs)

    def log(self, message: str, tag: str = 'info'):
        """Log a message to both console and GUI"""
        print(f"  {message}")
        if self.gui_callback:
            self.gui_callback(log=message, log_tag=tag)

    def wait_if_paused(self):
        """Block while paused"""
        while self.is_paused and self.running:
            time.sleep(0.5)

    # ==============================================
    # Browser Management
    # ==============================================

    def start(self, headless: bool = HEADLESS):
        """Start browser with saved session if available"""
        self.playwright = sync_playwright().start()
        self.browser = self.playwright.chromium.launch(headless=headless)

        if SESSION_FILE.exists():
            print(f"Loading saved session from {SESSION_FILE}")
            self.context = self.browser.new_context(storage_state=str(SESSION_FILE))
        else:
            print("No saved session found, starting fresh")
            self.context = self.browser.new_context()

        self.page = self.context.new_page()
        self.page.set_default_timeout(PAGE_LOAD_TIMEOUT)

    def stop(self):
        """Close browser and cleanup"""
        if self.context:
            self.context.close()
        if self.browser:
            self.browser.close()
        if hasattr(self, 'playwright'):
            self.playwright.stop()

    def save_session(self):
        """Save current session cookies"""
        SESSION_DIR.mkdir(parents=True, exist_ok=True)
        self.context.storage_state(path=str(SESSION_FILE))
        print(f"Session saved to {SESSION_FILE}")

    # ==============================================
    # Authentication
    # ==============================================

    def is_logged_in(self) -> bool:
        """Check if we're logged into PlanHub"""
        try:
            self.page.goto(LEADS_LIST_URL, wait_until="domcontentloaded")
            time.sleep(5)  # Allow Angular to settle

            current_url = self.page.url

            # Check if redirected to login
            if is_login_redirect(current_url):
                return False

            # Check for login page indicators
            login_indicator = self.page.query_selector(LOGIN_VALIDATION["login_page_indicator"])
            if login_indicator:
                return False

            # Check for logged-in indicators
            logged_in = self.page.query_selector(LOGIN_VALIDATION["logged_in_indicator"])
            if logged_in:
                return True

            # If we're on leads list and no login form, assume logged in
            if "subcontractor.planhub.com/leads" in current_url:
                return True

            return False
        except Exception as e:
            print(f"Error checking login status: {e}")
            return False

    def manual_login(self):
        """Open browser for manual login, then save session"""
        print("\n=== Manual Login Required ===")
        print("1. Browser will open to PlanHub login page")
        print("2. Complete login (email, password, any 2FA)")
        print("3. Wait until you see the Leads list page")
        print("4. Press Enter here to save session")
        print()

        self.start(headless=False)
        self.page.goto(LOGIN_URL)

        input("Press Enter after you've logged in and see the leads list...")

        # Allow page to settle
        time.sleep(2)

        if self.is_logged_in():
            self.save_session()
            print("Login successful! Session saved.")
        else:
            print("Login verification failed. Saving session anyway...")
            self.save_session()
            print("Session saved - please test with: python scraper.py status")

        self.stop()

    # ==============================================
    # Angular Helpers
    # ==============================================

    def wait_for_angular_ready(self, timeout: int = ELEMENT_WAIT_TIMEOUT):
        """Wait for Angular app to finish loading"""
        try:
            # Wait for any loading spinners to disappear
            spinner = self.page.query_selector(LEADS_LIST_SELECTORS["loading_spinner"])
            if spinner:
                self.page.wait_for_selector(
                    LEADS_LIST_SELECTORS["loading_spinner"],
                    state="hidden",
                    timeout=timeout
                )

            # Wait for network to be idle
            self.page.wait_for_load_state("networkidle")

            # Additional delay for Angular rendering
            time.sleep(0.5)
        except Exception:
            pass

    def wait_for_content(self, timeout: int = 15) -> bool:
        """Wait for page content to load (no spinners, has actual content)

        This is more reliable than networkidle for Angular SPAs.
        Polls until: no loading spinners AND some content element exists.
        """
        start = time.time()
        while time.time() - start < timeout:
            # Check if loading spinner is gone
            spinner = self.page.query_selector("mat-spinner, .mat-progress-spinner, .loading")
            if not spinner:
                # Check for actual content
                content = self.page.query_selector("h1, .project-title, table, .card, mat-card, .details")
                if content:
                    return True
            time.sleep(0.5)
        self.log(f"Warning: Timeout waiting for content ({timeout}s)", 'warning')
        return False

    def safe_navigate(self, url: str):
        """Navigate with proper Angular wait"""
        self.page.goto(url, wait_until="domcontentloaded")
        time.sleep(3)  # Allow Angular to render
        self.wait_for_angular_ready()

        # Check for login redirect
        if is_login_redirect(self.page.url):
            raise Exception("Session expired - need to re-login")

    # ==============================================
    # Lead Discovery
    # ==============================================

    def _wait_for_leads_loaded(self, timeout: int = 30, use_vision: bool = False):
        """Smart wait: poll until lead items have actual content loaded

        Args:
            timeout: Max seconds to wait
            use_vision: If True, also use vision model to confirm content loaded
        """
        import time as t
        start = t.time()

        while t.time() - start < timeout:
            # Check if any lead-name has a title attribute (means data loaded)
            lead_with_title = self.page.query_selector("planhub-lead-item .lead-name[title]")
            if lead_with_title:
                title = lead_with_title.get_attribute('title')
                if title and len(title) > 3:  # Has actual content
                    elapsed = t.time() - start
                    print(f"    Leads loaded (CSS) in {elapsed:.1f}s")

                    # Optional vision confirmation
                    if use_vision and VISION_AVAILABLE and VISION_ENABLED:
                        print(f"    Verifying with vision model...")
                        result = analyze_lead_list(self.page, use_local=VISION_USE_LOCAL,
                                                   save_debug=VISION_DEBUG_SCREENSHOTS, crop=True)
                        if result.get('lead_count', 0) > 0:
                            print(f"    Vision confirmed: {result.get('lead_count')} leads visible")
                        elif result.get('raw_response'):
                            # Still got a response, might have leads
                            print(f"    Vision response: {result.get('raw_response', '')[:100]}...")
                    return True
            t.sleep(0.5)

        print(f"    Warning: Timeout waiting for leads ({timeout}s)")
        return False

    def _close_extra_tabs(self):
        """Close any tabs beyond the main one"""
        pages = self.context.pages
        if len(pages) > 1:
            # Keep only the first page (main list), close others
            for page in pages[1:]:
                try:
                    page.close()
                except:
                    pass
            print(f"    Closed {len(pages) - 1} extra tab(s)")

    def _click_and_get_lead_id(self, element) -> Optional[str]:
        """Click element to select it, then navigate to detail page in SAME tab"""
        try:
            import time as t

            # Remember current state
            original_url = self.page.url

            # Step 1: Click the lead in the list to select it (updates preview panel)
            element.click()
            t.sleep(0.5)  # Wait for preview to update

            # Step 2: Find "View Project Files" or similar button that navigates
            # These buttons typically navigate in same tab
            nav_button_selectors = [
                "button:has-text('View Project')",
                "a:has-text('View Project')",
                "[class*='preview'] a[href*='/leads/details/']",
                ".lead-preview a[href*='/leads/details/']",
                "a[href*='/leads/details/']",  # Any link to lead details
            ]

            for selector in nav_button_selectors:
                try:
                    nav_elem = self.page.query_selector(selector)
                    if nav_elem:
                        href = nav_elem.get_attribute('href')
                        if href and '/leads/details/' in href:
                            # Extract ID directly from href without clicking
                            lead_id = extract_lead_id(href)
                            if lead_id:
                                print(f"      Got ID from href: {lead_id}")
                                return lead_id
                except:
                    continue

            # Step 3: If no href found, try clicking with modifier to prevent new tab
            # Hold Ctrl on Mac to potentially change behavior, or just regular click
            try:
                # Try to find any element with href containing leads/details
                all_links = self.page.query_selector_all("a[href*='/leads/details/']")
                for link in all_links:
                    href = link.get_attribute('href')
                    if href:
                        lead_id = extract_lead_id(href)
                        if lead_id:
                            print(f"      Got ID from page link: {lead_id}")
                            return lead_id
            except:
                pass

            # Step 4: Last resort - check if clicking updated URL params
            t.sleep(0.5)
            current_url = self.page.url
            if current_url != original_url:
                lead_id = extract_lead_id(current_url)
                if lead_id:
                    print(f"      Got ID from URL change: {lead_id}")
                    self.page.go_back()
                    t.sleep(1)
                    return lead_id

            print(f"      Could not find lead ID")
            return None

        except Exception as e:
            print(f"      Click error: {e}")
            if "leads/list" not in self.page.url:
                try:
                    self.page.go_back()
                    time.sleep(1)
                except:
                    pass
            return None

    def discover_all_leads(self) -> int:
        """Paginate through all leads list pages and add to database.

        Uses API response interception to capture lead IDs (no clicking needed).
        """
        print("\n=== Discovering Leads ===")

        # Check pagination state
        state = self.db.get_pagination_state()
        start_page = 1
        if state and not state.get('discovery_complete'):
            start_page = state.get('last_page', 1)
            print(f"Resuming discovery from page {start_page}")
        elif state and state.get('discovery_complete'):
            print("Discovery already complete. Use 'python scraper.py reset' to start over.")
            return 0

        page_num = start_page
        total_discovered = 0
        consecutive_empty = 0

        # Set up persistent API response interception
        all_captured_leads = []

        def handle_response(response):
            """Capture lead IDs from API responses"""
            if response.status == 200 and 'api' in response.url.lower():
                try:
                    data = response.json()

                    def extract_ids(obj):
                        if isinstance(obj, dict):
                            if 'id' in obj and isinstance(obj['id'], (int, str)):
                                id_val = str(obj['id'])
                                if len(id_val) >= 5 and id_val.isdigit():
                                    name = obj.get('name') or obj.get('title') or obj.get('projectName') or ''
                                    is_locked = obj.get('isLocked', False) or obj.get('locked', False)
                                    # Avoid duplicates
                                    if not any(l['id'] == id_val for l in all_captured_leads):
                                        all_captured_leads.append({
                                            'id': id_val,
                                            'name': str(name),
                                            'locked': is_locked
                                        })
                            for v in obj.values():
                                extract_ids(v)
                        elif isinstance(obj, list):
                            for item in obj[:50]:
                                extract_ids(item)

                    extract_ids(data)
                except Exception:
                    pass

        # Register handler once, before any navigation
        self.page.on('response', handle_response)

        try:
            while self.running:
                self.wait_if_paused()

                print(f"\nProcessing page {page_num}...")
                self.update_gui(action=f"Discovering page {page_num}...")

                # Clear captured leads for this page (keep handler active)
                leads_before = len(all_captured_leads)

                # Navigate or wait for next page to load
                if page_num == start_page:
                    self.page.goto(LEADS_LIST_URL, wait_until="domcontentloaded")

                # Wait for leads to load
                try:
                    self.page.wait_for_selector(
                        LEADS_LIST_SELECTORS["lead_item"],
                        timeout=ELEMENT_WAIT_TIMEOUT
                    )
                except PlaywrightTimeout:
                    print("  No leads found on page - might be end")
                    consecutive_empty += 1
                    if consecutive_empty >= 2:
                        break
                    if not self._click_next_page():
                        break
                    page_num += 1
                    continue

                consecutive_empty = 0

                # Smart wait for content
                print("  Waiting for lead data to load...")
                self._wait_for_leads_loaded(use_vision=VISION_ENABLED and VISION_AVAILABLE)
                time.sleep(2)  # Extra time for API responses

                # Count new leads captured on this page
                new_captured = len(all_captured_leads) - leads_before

                # Get lead items from DOM
                containers = self.page.query_selector_all(LEADS_LIST_SELECTORS["lead_item_container"])
                num_items = len(containers)
                print(f"  Found {num_items} lead items on page")
                print(f"  Captured {new_captured} new IDs (total: {len(all_captured_leads)})")

                # Match DOM elements with API data
                page_leads = 0
                for container in containers:
                    self.wait_if_paused()
                    if not self.running:
                        break

                    # Get name from DOM
                    name_elem = container.query_selector(".lead-name")
                    if not name_elem:
                        continue

                    name = name_elem.get_attribute('title') or name_elem.inner_text().strip()

                    # Check locked status from DOM (more reliable)
                    is_locked = self._is_lead_locked(container)

                    # Find matching ID from ALL captured API data
                    lead_id = None
                    for lead in all_captured_leads:
                        if lead['name'] and name:
                            if lead['name'] in name or name in lead['name']:
                                lead_id = lead['id']
                                break

                    if lead_id:
                        status = "[LOCKED] " if is_locked else ""
                        print(f"    {status}{name[:50]} (ID: {lead_id})")

                        lead_data = {
                            'planhub_id': lead_id,
                            'name': name,
                            'url': f"{BASE_URL}/leads/details/{lead_id}/project-info",
                        }
                        if self.db.add_lead(lead_data, is_locked=is_locked):
                            total_discovered += 1
                            page_leads += 1
                    else:
                        print(f"    Could not match ID for: {name[:40]}")

                print(f"  Page {page_num}: {page_leads} new leads discovered")

                # Save pagination state
                self.db.update_pagination_state(page_num, total_discovered)

                # Try to go to next page
                if not self._has_next_page():
                    print("Reached last page!")
                    break

                if not self._click_next_page():
                    print("Could not navigate to next page")
                    break

                page_num += 1
                time.sleep(REQUEST_DELAY)

        finally:
            # Clean up response handler
            try:
                self.page.remove_listener('response', handle_response)
            except Exception:
                pass

        self.db.mark_discovery_complete(total_discovered)
        print(f"\nDiscovery complete! Total new leads: {total_discovered}")
        return total_discovered

    def _extract_lead_from_list(self, elem) -> Optional[dict]:
        """Extract lead info from list item element by clicking to get real URL"""
        try:
            # Get name from title attribute or inner text
            name_elem = elem.query_selector(".lead-name span, .lead-name")
            if not name_elem:
                name_elem = elem

            name = name_elem.inner_text().strip() if name_elem else "Unknown"

            # Get title attribute if available (more reliable)
            title_attr = elem.get_attribute('title')
            if title_attr:
                name = title_attr

            # Click the lead to navigate to detail page
            clickable = elem.query_selector(".lead-name") or elem
            clickable.click()
            time.sleep(2)  # Wait for navigation

            # Get the real URL with lead ID
            current_url = self.page.url
            lead_id = extract_lead_id(current_url)

            if lead_id:
                # Navigate back to list
                self.page.go_back()
                time.sleep(2)  # Wait for list to reload
                self.wait_for_angular_ready()

                return {
                    'planhub_id': lead_id,
                    'name': name,
                    'url': current_url,
                }

            # If we didn't get an ID, still go back
            self.page.go_back()
            time.sleep(2)
            return None

        except Exception as e:
            print(f"  Error extracting lead: {e}")
            # Try to go back to list
            try:
                self.page.go_back()
                time.sleep(2)
            except:
                pass
            return None

    def _is_lead_locked(self, container) -> bool:
        """Check if a lead container has the locked icon"""
        try:
            # Check for locked icon (mat-icon with svgicon="lead-locked")
            locked = container.query_selector(LEADS_LIST_SELECTORS["locked_icon"])
            if locked:
                return True

            # Also check for title="Locked" attribute
            locked_title = container.query_selector(LEADS_LIST_SELECTORS["locked_by_title"])
            if locked_title:
                return True

        except Exception:
            pass
        return False

    def _has_next_page(self) -> bool:
        """Check if there's a next page button that's enabled"""
        try:
            next_btn = self.page.query_selector(LEADS_LIST_SELECTORS["next_page"])
            if not next_btn:
                return False

            # Check if disabled
            is_disabled = next_btn.get_attribute('disabled')
            aria_disabled = next_btn.get_attribute('aria-disabled')

            if is_disabled is not None or aria_disabled == 'true':
                return False

            return True
        except Exception:
            return False

    def _click_next_page(self) -> bool:
        """Click the next page button and wait for content"""
        try:
            next_btn = self.page.query_selector(LEADS_LIST_SELECTORS["next_page"])
            if not next_btn:
                return False

            next_btn.click()
            time.sleep(1)
            self.wait_for_angular_ready()

            # Wait for new lead items
            self.page.wait_for_selector(
                LEADS_LIST_SELECTORS["lead_item"],
                timeout=ELEMENT_WAIT_TIMEOUT
            )
            return True
        except Exception as e:
            print(f"  Error clicking next page: {e}")
            return False

    # ==============================================
    # Project Detail Scraping
    # ==============================================

    def scrape_lead(self, lead: Lead) -> dict:
        """Scrape all tabs for a single lead"""
        print(f"\nScraping: {lead.name[:50]}...")
        print(f"  URL: {lead.url}")

        self.update_gui(
            current_title=lead.name[:60],
            action="Loading project..."
        )

        data = {}

        # Navigate to project info tab first
        project_info_url = get_project_tab_url(lead.planhub_id, 'project_info')
        self.safe_navigate(project_info_url)

        # Scrape Project Info tab
        try:
            data['project_info'] = self._scrape_project_info_tab()
            print(f"    Project Info: OK")
        except Exception as e:
            print(f"    Project Info: FAILED - {e}")
            data['project_info'] = {}

        # Scrape Project Files tab
        try:
            self.update_gui(action="Scraping files...")
            self._click_tab('project_files')
            data['project_files'] = self._scrape_project_files_tab()
            print(f"    Project Files: {len(data['project_files'])} files")
        except Exception as e:
            print(f"    Project Files: FAILED - {e}")
            data['project_files'] = []

        # Scrape General Contractors tab
        try:
            self.update_gui(action="Scraping contractors...")
            self._click_tab('general_contractors')
            data['contractors'] = self._scrape_contractors_tab()
            print(f"    Contractors: {len(data['contractors'])} GCs")
        except Exception as e:
            print(f"    Contractors: FAILED - {e}")
            data['contractors'] = []

        # Scrape Market Intelligence tab
        try:
            self.update_gui(action="Scraping market intel...")
            self._click_tab('market_intelligence')
            data['market_intel'] = self._scrape_market_intel_tab()
            print(f"    Market Intel: OK")
        except Exception as e:
            print(f"    Market Intel: FAILED - {e}")
            data['market_intel'] = {}

        # Scrape Q&A tab
        try:
            self.update_gui(action="Scraping Q&A...")
            self._click_tab('project_qa')
            data['qa'] = self._scrape_qa_tab()
            print(f"    Q&A: {len(data['qa'])} entries")
        except Exception as e:
            print(f"    Q&A: FAILED - {e}")
            data['qa'] = []

        # Scrape Material Estimates tab
        try:
            self.update_gui(action="Scraping estimates...")
            self._click_tab('material_estimates')
            data['material_estimates'] = self._scrape_material_estimates_tab()
            print(f"    Material Estimates: OK")
        except Exception as e:
            print(f"    Material Estimates: FAILED - {e}")
            data['material_estimates'] = {}

        return data

    def _click_tab(self, tab_name: str):
        """Click a tab and wait for content to load"""
        selector = TAB_SELECTORS.get(tab_name)
        if not selector:
            raise ValueError(f"Unknown tab: {tab_name}")

        try:
            self.page.wait_for_selector(selector, timeout=5000)
            self.page.click(selector)
            time.sleep(1)
            self.wait_for_angular_ready()
        except Exception:
            # Try direct navigation as fallback
            lead_id = extract_lead_id(self.page.url)
            if lead_id:
                url = get_project_tab_url(lead_id, tab_name)
                self.safe_navigate(url)
            else:
                raise

    def _scrape_project_info_tab(self) -> dict:
        """Extract project info using regex from page text.

        This is more reliable than CSS selectors for Angular SPAs.
        """
        import re as regex
        data = {}

        try:
            # Wait for content to load
            self.wait_for_content()
            time.sleep(1)

            # Get all text from page
            page_text = self.page.inner_text("body")

            # Bid date
            bid_match = regex.search(r'Bid Due Date\s*(\d{1,2}/\d{1,2}/\d{4})\s*at\s*(\d{1,2}:\d{2}\s*[AP]M)', page_text)
            if bid_match:
                data['bid_due_date'] = f"{bid_match.group(1)} {bid_match.group(2)}"

            # Location (address with state and zip)
            loc_match = regex.search(r'(\d+[^\n]+(?:MA|CT|NH|RI|VT|ME|NY|NJ|PA|FL|CA|TX|GA|OH|MI|IL|WA|OR|AZ|CO|NC|VA|MD|SC|TN|AL|KY|LA|MO|IN|WI|MN|OK|KS|AR|MS|NV|NM|WV|NE|ID|HI|DE|DC)\s*\d{5})', page_text)
            if loc_match:
                data['location'] = loc_match.group(1).strip()

            # Description
            desc_match = regex.search(r'(This project calls for[^\.]+\.)', page_text)
            if desc_match:
                data['description'] = desc_match.group(1).strip()

            # Project Size
            size_match = regex.search(r'([\d,]+\.?\d*)\s*SF\s*Project size', page_text)
            if size_match:
                data['project_size'] = f"{size_match.group(1)} SF"

            # Project Value
            value_match = regex.search(r'\$([\d,]+\.?\d*)\s*Project\s*value', page_text)
            if value_match:
                data['project_value'] = f"${value_match.group(1)}"

            # Start Date
            start_match = regex.search(r'([A-Z][a-z]+ \d{1,2}, \d{4})\s*Start Date', page_text)
            if start_match:
                data['start_date'] = start_match.group(1)

            # End Date
            end_match = regex.search(r'([A-Z][a-z]+ \d{1,2}, \d{4})\s*End date', page_text)
            if end_match:
                data['end_date'] = end_match.group(1)

            # Tags
            tags = []
            tag_patterns = ['GC Awarded', 'Sub Bidding', 'Commercial', 'Retail', 'Retail Store',
                            'Renovation', 'New Construction', 'Residential', 'Industrial']
            for tag in tag_patterns:
                if tag in page_text:
                    tags.append(tag)
            if tags:
                data['tags'] = tags

            # Project name from header (before star icons)
            lines = page_text.split('\n')
            for line in lines[:20]:
                line = line.strip()
                if len(line) > 10 and ' - ' in line:
                    # Remove star/grade icons from end
                    name = line.split('star')[0].split('grade')[0].strip()
                    if name:
                        data['project_name'] = name
                        break

        except Exception as e:
            self.log(f"Error extracting project info: {e}", 'error')

        return data

    def _scrape_project_files_tab(self) -> list:
        """Extract file metadata using page text parsing.

        More reliable than table parsing for Angular SPAs.
        """
        import re as regex
        files = []

        try:
            # Wait for content
            self.wait_for_content()
            time.sleep(1)

            page_text = self.page.inner_text("body")

            # Get total count
            total_count = 0
            count_match = regex.search(r'(\d+)\s*total', page_text, regex.I)
            if count_match:
                total_count = int(count_match.group(1))

            # Try to extract documents using pattern:
            # filename  size  type  date
            doc_matches = regex.findall(
                r'([A-Za-z0-9][^\n]{5,50})\s+(\d+\.?\d*\s*(?:kB|MB|GB))\s+(Specs|Plans|Addendums|Drawings|Other|[A-Za-z ]+)\s+(\d{1,2}/\d{1,2}/\d{4})',
                page_text
            )
            for match in doc_matches[:20]:  # First 20
                files.append({
                    'file_name': match[0].strip(),
                    'size': match[1],
                    'document_type': match[2],
                    'date_added': match[3]
                })

            # Fallback: try table parsing if regex found nothing
            if not files:
                try:
                    rows = self.page.query_selector_all("tr, mat-row, .file-row")
                    for row in rows[1:11]:  # Skip header, first 10
                        cells = row.query_selector_all("td, mat-cell")
                        if cells and len(cells) > 0:
                            file_data = {
                                'file_name': cells[0].inner_text().strip() if len(cells) > 0 else '',
                                'document_type': cells[1].inner_text().strip() if len(cells) > 1 else '',
                                'size': cells[2].inner_text().strip() if len(cells) > 2 else '',
                                'date_added': cells[3].inner_text().strip() if len(cells) > 3 else '',
                            }
                            if file_data['file_name']:
                                files.append(file_data)
                except Exception:
                    pass

            # Store total count in metadata
            if total_count and files:
                files.insert(0, {'_total_count': total_count})

        except Exception as e:
            self.log(f"Files extraction error: {e}", 'error')

        return files

    def _scrape_contractors_tab(self) -> list:
        """Extract general contractor information using href selectors.

        Uses the reliable approach of finding tel: and mailto: links.
        """
        contractors = []

        try:
            # Wait for content
            self.wait_for_content()
            time.sleep(1)

            # Get phone and email links directly (most reliable)
            phones = self.page.query_selector_all("a[href^='tel:']")
            emails = self.page.query_selector_all("a[href^='mailto:']")

            # Create contractors from phone/email pairs
            seen_phones = set()
            for i, phone in enumerate(phones[:10]):  # First 10
                phone_text = phone.inner_text().strip()

                # Skip duplicates
                if phone_text in seen_phones:
                    continue
                seen_phones.add(phone_text)

                gc = {
                    'phone': phone_text,
                    'email': ''
                }

                # Try to match with email
                if i < len(emails):
                    gc['email'] = emails[i].inner_text().strip()

                # Try to get company name from nearby elements
                try:
                    # Walk up to find container, then find company name
                    parent = phone.evaluate_handle("el => el.closest('mat-card, .connection, [class*=\"contractor\"]')")
                    if parent:
                        name_elem = parent.query_selector("h3, h4, .company-name, .contractor-name")
                        if name_elem:
                            gc['company_name'] = name_elem.inner_text().strip()
                except Exception:
                    pass

                if gc.get('phone') or gc.get('email'):
                    contractors.append(gc)

        except Exception as e:
            self.log(f"GC extraction error: {e}", 'error')

        return contractors

    def _scrape_market_intel_tab(self) -> dict:
        """Extract market intelligence data using regex.

        Finds download counts by trade/scope.
        """
        import re as regex
        intel = {
            'downloads_by_scope': []
        }

        try:
            # Wait for content
            self.wait_for_content()
            time.sleep(1)

            page_text = self.page.inner_text("body")

            # Trades we're interested in for Division 8 (and others)
            trades = [
                'Exterior Doors', 'Interior Doors', 'Glazing', 'Storefronts', 'Curtain Walls',
                'Glass and Mirrors', 'Shower Doors', 'Windows', 'Doors', 'Door Hardware',
                'Roofing', 'HVAC', 'Electrical', 'Plumbing', 'Masonry', 'Concrete',
                'Steel', 'Drywall', 'Painting', 'Flooring'
            ]

            for trade in trades:
                match = regex.search(rf'{trade}\s+(\d+)', page_text)
                if match:
                    intel['downloads_by_scope'].append({
                        'scope': trade,
                        'downloaded': int(match.group(1))
                    })

            # Also store any raw data for debugging
            intel['_raw_text'] = page_text[:500] if page_text else ''

        except Exception as e:
            self.log(f"Market intel error: {e}", 'error')

        return intel

    def _scrape_qa_tab(self) -> list:
        """Extract Q&A entries"""
        qa_list = []

        try:
            items = self.page.query_selector_all(QA_SELECTORS["qa_item"])

            for item in items:
                try:
                    qa = {}

                    q_elem = item.query_selector(QA_SELECTORS["question"])
                    if q_elem:
                        qa['question'] = q_elem.inner_text().strip()

                    a_elem = item.query_selector(QA_SELECTORS["answer"])
                    if a_elem:
                        qa['answer'] = a_elem.inner_text().strip()

                    if qa.get('question'):
                        qa_list.append(qa)
                except Exception:
                    continue

        except Exception as e:
            print(f"    Q&A error: {e}")

        return qa_list

    def _scrape_material_estimates_tab(self) -> dict:
        """Extract material estimates data"""
        estimates = {}

        try:
            container = self.page.query_selector(MATERIAL_SELECTORS["container"])
            if container:
                estimates['_raw_text'] = container.inner_text().strip()

                items = container.query_selector_all(MATERIAL_SELECTORS["estimate_item"])
                if items:
                    estimates['items'] = [item.inner_text().strip() for item in items]

        except Exception as e:
            print(f"    Estimates error: {e}")

        return estimates

    # ==============================================
    # Fallback HTML
    # ==============================================

    def save_fallback_html(self, lead: Lead) -> str:
        """Save raw HTML when scraping fails"""
        HTML_FALLBACK_DIR.mkdir(parents=True, exist_ok=True)

        filename = f"{lead.planhub_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
        filepath = HTML_FALLBACK_DIR / filename

        try:
            html_content = self.page.content()
            filepath.write_text(html_content, encoding='utf-8')
            print(f"  Saved fallback HTML: {filepath}")
            return str(filepath)
        except Exception as e:
            print(f"  Failed to save HTML: {e}")
            return ""

    # ==============================================
    # Main Run Loop
    # ==============================================

    def run(self):
        """Main scraping loop with resume support"""
        print("\n=== Starting PlanHub Scraper ===")
        self.log("Initializing...", 'info')

        self.db = Database()
        self.db.connect()
        self.db.create_tables()
        self.db.reset_in_progress()

        self.update_gui(action="Starting browser...")
        self.start(headless=HEADLESS)

        self.update_gui(action="Checking login...")
        if not self.is_logged_in():
            self.log("Not logged in! Run: python scraper.py login", 'error')
            self.update_gui(status="Not logged in")
            self.stop()
            self.db.close()
            return

        self.log("Session valid", 'success')

        # Phase 1: Discovery (if not complete)
        state = self.db.get_pagination_state()
        if not state or not state.get('discovery_complete'):
            self.update_gui(status="Discovering leads...")
            self.discover_all_leads()

        # Phase 2: Scrape individual leads
        self.update_gui(status="Running")
        self.log("Starting lead scraping...", 'info')

        processed = 0
        try:
            while self.running:
                self.wait_if_paused()
                if not self.running:
                    break

                # Get next lead
                lead = self.db.get_next_queued()
                if not lead:
                    self.log("All leads processed!", 'success')
                    self.update_gui(status="Complete!", action="")
                    break

                # Update GUI
                stats = self.db.get_stats()
                self.update_gui(
                    current_num=stats.get('done', 0) + 1,
                    total=stats.get('total_leads', 0),
                    progress=stats.get('progress_pct', 0),
                    action="Scraping lead..."
                )

                self.db.mark_in_progress(lead.id)

                try:
                    data = self.scrape_lead(lead)
                    self.db.save_lead_data(lead.id, data)

                    # Save file metadata
                    for file_data in data.get('project_files', []):
                        self.db.add_file(lead.id, file_data)

                    self.db.mark_done(lead.id)
                    processed += 1

                    self.update_gui(project_done=True)
                    self.log(f"Done: {lead.name[:50]}", 'success')

                except Exception as e:
                    error_msg = str(e)
                    self.log(f"ERROR: {error_msg}", 'error')

                    # Save fallback HTML
                    html_path = self.save_fallback_html(lead)
                    if html_path:
                        self.db.save_raw_html(lead.id, html_path)

                    self.db.mark_error(lead.id, error_msg)

                    if "session expired" in error_msg.lower() or "re-login" in error_msg.lower():
                        self.log("Session expired! Run: python scraper.py login", 'error')
                        self.update_gui(status="Session expired!")
                        break

                # Wait between requests
                self.update_gui(action=f"Waiting {REQUEST_DELAY}s...")
                for _ in range(REQUEST_DELAY * 2):
                    if not self.running:
                        break
                    self.wait_if_paused()
                    time.sleep(0.5)

        finally:
            self.stop()
            self.db.close()

        self.log(f"Session complete: {processed} leads processed", 'info')


# ==============================================
# CLI Entry Point
# ==============================================

def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    command = sys.argv[1].lower()

    if command == "login":
        scraper = PlanHubScraper()
        scraper.manual_login()

    elif command == "discover":
        scraper = PlanHubScraper()
        scraper.db = Database()
        scraper.db.connect()
        scraper.db.create_tables()
        scraper.start(headless=HEADLESS)
        if scraper.is_logged_in():
            scraper.discover_all_leads()
        else:
            print("Not logged in! Run: python scraper.py login")
        scraper.stop()
        scraper.db.close()

    elif command == "run":
        scraper = PlanHubScraper()
        scraper.run()

    elif command == "gui":
        from gui import run_gui
        run_gui()

    elif command == "status":
        init_database()
        show_stats()

    elif command == "reset":
        with Database() as db:
            db.create_tables()
            db.reset_discovery()
        print("Discovery state reset. Run 'python scraper.py discover' to start over.")

    elif command == "init":
        init_database()

    elif command == "vision":
        # Test vision functionality
        if not VISION_AVAILABLE:
            print("Vision helper not available! Check imports.")
            sys.exit(1)

        scraper = PlanHubScraper()
        scraper.start(headless=False)

        if scraper.is_logged_in():
            print("\n=== Vision Test Mode ===")
            print("Taking screenshot of lead list page...")

            # Navigate to leads
            scraper.safe_navigate(LEADS_LIST_URL)
            time.sleep(3)

            # Take various screenshots
            print("\n1. Full screenshot:")
            full_path = take_screenshot(scraper.page, "vision_full", crop_region='full')
            print(f"   Saved: {full_path}")

            print("\n2. Cropped to lead list area:")
            cropped_path = take_screenshot(scraper.page, "vision_cropped", crop_region='lead_list')
            print(f"   Saved: {cropped_path}")

            print("\n3. Analyzing with vision model...")
            result = analyze_lead_list(scraper.page, use_local=VISION_USE_LOCAL, crop=True)
            print(f"\n   Vision Analysis Results:")
            print(f"   - Lead count detected: {result.get('lead_count', 'unknown')}")
            print(f"   - Page loaded: {result.get('is_loaded', 'unknown')}")
            print(f"   - Has locked items: {result.get('has_locked', 'unknown')}")
            if result.get('raw_response'):
                print(f"\n   Raw response:\n   {result['raw_response'][:500]}...")

            print(f"\n   Screenshots saved to: {SCREENSHOT_DIR}")
        else:
            print("Not logged in! Run: python scraper.py login")

        scraper.stop()

    else:
        print(f"Unknown command: {command}")
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
