"""
ProjectDog.com scraper for Division 8 public work projects
Uses Selenium to handle JS-based authentication and navigation
Enhanced to capture detailed project information including DCAM, RFQ status, etc.

Version 2.0 - December 2025
- Full table parsing for all projects (Code + GO)
- Document download workflow with legal notice acceptance
- Project folder creation in bidding directory
- Document recipients tracking
"""

import os
import json
import time
import re
import requests
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from urllib.parse import urlparse, parse_qs

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from webdriver_manager.chrome import ChromeDriverManager


def sanitize_filename(name: str) -> str:
    """Sanitize a string for use as a filename"""
    # Remove or replace invalid characters
    invalid_chars = '<>:"/\\|?*'
    for char in invalid_chars:
        name = name.replace(char, '-')
    # Remove leading/trailing spaces and dots
    name = name.strip(' .')
    # Limit length
    if len(name) > 100:
        name = name[:100]
    return name


class ProjectDogScraper:
    """Enhanced scraper for ProjectDog.com Division 8 projects"""

    BASE_URL = "https://projectdog.com"
    LOGIN_URL = "https://projectdog.com/Login.aspx"
    SEARCH_URL = "https://projectdog.com/SearchDatabase.aspx"
    PROJECT_URL = "https://projectdog.com/ProjectLeadsDisplayProject.aspx?ProjectCode={}"
    RECIPIENTS_URL = "https://projectdog.com/ProjectDocBidders.aspx?ProjectID={}"
    LEGAL_NOTICE_URL = "https://projectdog.com/LegalNotice.aspx?ProjectID={}"
    FILE_DOWNLOAD_URL = "https://projectdog.com/FileDownload.aspx"

    def __init__(self, email: str, password: str, headless: bool = True):
        self.email = email
        self.password = password
        self.headless = headless
        self.driver = None
        self.projects = []
        self.logged_in = False
        self.session_cookies = None  # For requests library

    def _init_driver(self):
        """Initialize Chrome WebDriver"""
        options = Options()
        if self.headless:
            options.add_argument("--headless=new")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument("--window-size=1920,1080")
        # Use a more complete user agent to avoid detection
        options.add_argument("--user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
        # Disable automation detection
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option('useAutomationExtension', False)

        # Try to find chromedriver - webdriver_manager has a bug with path detection
        chromedriver_path = None

        # First, try the known cached location
        wdm_path = Path.home() / ".wdm/drivers/chromedriver"
        if wdm_path.exists():
            # Find the actual chromedriver binary
            for driver_file in wdm_path.rglob("chromedriver"):
                if driver_file.is_file() and driver_file.name == "chromedriver":
                    chromedriver_path = str(driver_file)
                    # Make sure it's executable
                    driver_file.chmod(0o755)
                    break

        if chromedriver_path:
            service = Service(chromedriver_path)
        else:
            # Fallback to webdriver_manager
            service = Service(ChromeDriverManager().install())

        self.driver = webdriver.Chrome(service=service, options=options)
        self.driver.implicitly_wait(10)

    def _close_driver(self):
        """Close the WebDriver"""
        if self.driver:
            self.driver.quit()
            self.driver = None
            self.logged_in = False

    def login(self) -> bool:
        """Login to ProjectDog"""
        try:
            # New site has login form on main page
            self.driver.get(self.BASE_URL)
            time.sleep(2)

            # Try new simplified IDs first (current site)
            try:
                email_field = WebDriverWait(self.driver, 5).until(
                    EC.presence_of_element_located((By.ID, "Email"))
                )
                email_field.clear()
                email_field.send_keys(self.email)

                password_field = self.driver.find_element(By.ID, "Password")
                password_field.clear()
                password_field.send_keys(self.password)

                # Find login button - look for submit button or button with login text
                login_button = None
                buttons = self.driver.find_elements(By.TAG_NAME, "button")
                for btn in buttons:
                    btn_type = btn.get_attribute("type")
                    btn_text = btn.text.lower()
                    if btn_type == "submit" or "login" in btn_text or "sign in" in btn_text:
                        login_button = btn
                        break

                if not login_button:
                    # Try input type submit
                    login_button = self.driver.find_element(By.CSS_SELECTOR, "input[type='submit']")

                login_button.click()

            except Exception:
                # Fallback to old ASP.NET IDs
                self.driver.get(self.LOGIN_URL)
                time.sleep(2)

                email_field = WebDriverWait(self.driver, 10).until(
                    EC.presence_of_element_located((By.ID, "ctl00_ContentPlaceHolder1_txtEmail"))
                )
                email_field.clear()
                email_field.send_keys(self.email)

                password_field = self.driver.find_element(By.ID, "ctl00_ContentPlaceHolder1_txtPassword")
                password_field.clear()
                password_field.send_keys(self.password)

                login_button = self.driver.find_element(By.ID, "ctl00_ContentPlaceHolder1_btnLogin")
                login_button.click()

            # Wait for redirect/page load
            time.sleep(3)

            # Check if logged in by looking for logout link or user menu
            page_source = self.driver.page_source.lower()
            if "logout" in page_source or "sign out" in page_source or "my account" in page_source or "dashboard" in page_source:
                print("Login successful!")
                self.logged_in = True
                return True
            elif "invalid" in page_source or "incorrect" in page_source:
                print("Login failed - invalid credentials")
                return False
            else:
                # Might still be successful, continue anyway
                print("Login status unclear, continuing...")
                self.logged_in = True
                return True

        except Exception as e:
            print(f"Login failed: {e}")
            return False

    def search_division8(self) -> List[Dict]:
        """Search for Division 8 projects and return basic list"""
        try:
            self.driver.get(self.SEARCH_URL)
            time.sleep(2)

            # Wait for page
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.ID, "ctl00_ContentPlaceHolder1_tabProject_tab1_Division8"))
            )

            # Check Division 8 checkbox
            div8_checkbox = self.driver.find_element(
                By.ID, "ctl00_ContentPlaceHolder1_tabProject_tab1_Division8"
            )
            if not div8_checkbox.is_selected():
                div8_checkbox.click()
                print("Division 8 checkbox checked")
                time.sleep(0.5)

            # Click search button using native Selenium click
            search_button = self.driver.find_element(
                By.ID, "ctl00_ContentPlaceHolder1_tabProject_tab1_Search"
            )
            print("Clicking search button...")

            # Scroll to button to ensure it's visible
            self.driver.execute_script("arguments[0].scrollIntoView(true);", search_button)
            time.sleep(0.5)

            # Use native click
            search_button.click()

            # Wait for page to update
            print("Waiting for results...")
            time.sleep(5)

            # Check for error page
            if 'GenericErrorPage' in self.driver.current_url or 'Error' in self.driver.title:
                print("Error page detected, going back and retrying...")
                self.driver.back()
                time.sleep(2)

                # Re-navigate to search page fresh
                self.driver.get(self.SEARCH_URL)
                time.sleep(2)

                # Re-check Division 8
                div8_checkbox = self.driver.find_element(
                    By.ID, "ctl00_ContentPlaceHolder1_tabProject_tab1_Division8"
                )
                if not div8_checkbox.is_selected():
                    div8_checkbox.click()
                    time.sleep(0.5)

                # Click Search ALL Projects button instead
                print("Trying 'Search ALL Projects' button...")
                search_all_btn = self.driver.find_element(
                    By.ID, "ctl00_ContentPlaceHolder1_tabProject_tab1_Submit1"
                )
                search_all_btn.click()
                time.sleep(5)

            # Check if we now have results
            results_found = False
            for attempt in range(3):
                try:
                    links = self.driver.find_elements(By.CSS_SELECTOR, "a[href*='ProjectCode=']")
                    if links:
                        print(f"Found {len(links)} project links with codes!")
                        results_found = True
                        break
                except:
                    pass

                try:
                    go_links = self.driver.find_elements(By.CSS_SELECTOR, "a[href*='InterestList=']")
                    if go_links:
                        print(f"Found {len(go_links)} GO project links!")
                        results_found = True
                        break
                except:
                    pass

                if not results_found and attempt < 2:
                    print(f"No results yet, waiting... (attempt {attempt + 1}/3)")
                    time.sleep(3)

            # Additional wait for content to fully render
            time.sleep(2)

            # Debug: Save current page source
            print(f"Current URL: {self.driver.current_url}")

            # Save page for debugging
            try:
                with open('/tmp/projectdog_after_search.html', 'w') as f:
                    f.write(self.driver.page_source)
                print("Saved page source to /tmp/projectdog_after_search.html")
            except Exception as e:
                print(f"Could not save debug file: {e}")

            print("Parsing results...")
            return self._parse_search_results()

        except Exception as e:
            print(f"Search failed: {e}")
            import traceback
            traceback.print_exc()
            return []

    def _parse_search_results(self) -> List[Dict]:
        """Parse the search results page for project listings - full table extraction"""
        projects = []

        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(self.driver.page_source, 'html.parser')

            # Debug: Check what IDs we have
            all_tables = soup.find_all('table', id=True)
            table_ids = [t.get('id', '') for t in all_tables]
            print(f"Found {len(all_tables)} tables with IDs")
            grid_tables = [tid for tid in table_ids if 'Grid' in tid or 'Project' in tid]
            if grid_tables:
                print(f"Grid/Project tables: {grid_tables}")

            # Find the results table by ID
            results_table = soup.find('table', id='ctl00_ContentPlaceHolder1_tabProject_tab1_ProjectSearchDGrid')

            if not results_table:
                # Try partial match
                for table in all_tables:
                    table_id = table.get('id', '')
                    if 'ProjectSearch' in table_id or 'DGrid' in table_id:
                        print(f"Found potential table: {table_id}")
                        results_table = table
                        break

            if not results_table:
                print("Could not find results table, trying alternative parsing...")
                return self._parse_results_alternative()

            # Get all rows (skip header row)
            rows = results_table.find_all('tr')

            for row in rows[1:]:  # Skip header
                cells = row.find_all('td')
                if len(cells) < 7:
                    continue

                try:
                    # Extract cell text - columns are:
                    # 0: Bid Date, 1: Sub Bid Date, 2: Est., 3: Project Title, 4: City, 5: State, 6: Code
                    bid_date_raw = cells[0].get_text(strip=True)
                    sub_bid_date_raw = cells[1].get_text(strip=True)
                    estimated_value = cells[2].get_text(strip=True)
                    title = cells[3].get_text(strip=True)
                    city = cells[4].get_text(strip=True)
                    state = cells[5].get_text(strip=True)

                    # Parse the Code cell - can be a link with ProjectCode or GO
                    code_cell = cells[6]
                    code_link = code_cell.find('a')

                    if not code_link or not title:
                        continue

                    href = code_link.get('href', '')
                    link_text = code_link.get_text(strip=True)

                    # Determine project type
                    project_code = None
                    interest_list_id = None
                    has_documents = False

                    if 'ProjectLeadsDisplayProject.aspx?ProjectCode=' in href:
                        # Has documents - extract project code
                        project_code = self._extract_project_code(href)
                        has_documents = True
                    elif 'ProjectLeadsLitePayment.aspx?InterestList=' in href:
                        # GO project - no documents hosted
                        match = re.search(r'InterestList=([A-Za-z0-9]+)', href)
                        if match:
                            interest_list_id = match.group(1)
                        has_documents = False

                    # Check if E-Bid icon is present
                    has_ebid = code_cell.find('img', src=lambda x: x and 'Ebid' in x) is not None

                    # Detect RFQ from title
                    is_rfq = title.upper().startswith('RFQ ')

                    # Parse dates
                    bid_date = self._parse_date(bid_date_raw)
                    sub_bid_date = self._parse_date(sub_bid_date_raw)

                    # Build project object
                    project = {
                        "source": "projectdog",
                        "project_code": project_code,
                        "interest_list_id": interest_list_id,
                        "title": title,
                        "is_rfq": is_rfq,
                        "is_dcam": False,  # Will be determined from detail page
                        "bid_date": bid_date,
                        "sub_bid_date": sub_bid_date,
                        "estimated_value": estimated_value,
                        "city": city,
                        "state": state.strip(),
                        "location": {
                            "city": city,
                            "state": state.strip(),
                            "raw": f"{city}, {state.strip()}"
                        },
                        "has_documents": has_documents,
                        "has_ebid": has_ebid,
                        "documents_acquired": False,
                        "documents": [],
                        "document_recipients": [],
                        "url": href if href.startswith('http') else f"{self.BASE_URL}/{href}",
                        "scraped_at": datetime.now().isoformat()
                    }

                    # Avoid duplicates based on project_code or interest_list_id
                    identifier = project_code or interest_list_id
                    if identifier and not any(
                        (p.get('project_code') == project_code and project_code) or
                        (p.get('interest_list_id') == interest_list_id and interest_list_id)
                        for p in projects
                    ):
                        projects.append(project)

                except Exception as e:
                    print(f"Error parsing row: {e}")
                    continue

            print(f"Found {len(projects)} projects in search results ({sum(1 for p in projects if p['has_documents'])} with documents)")

        except Exception as e:
            print(f"Error parsing search results: {e}")
            import traceback
            traceback.print_exc()

        return projects

    def _parse_date(self, date_str: str) -> Optional[str]:
        """Parse date string to ISO format"""
        if not date_str:
            return None
        try:
            # Try MM/DD/YYYY format
            dt = datetime.strptime(date_str, "%m/%d/%Y")
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            pass
        try:
            # Try MM/DD/YY format
            dt = datetime.strptime(date_str, "%m/%d/%y")
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            pass
        return date_str  # Return original if can't parse

    def _extract_project_code(self, url: str) -> Optional[str]:
        """Extract project code from URL"""
        match = re.search(r'ProjectCode=(\d+)', url)
        if match:
            return match.group(1)
        match = re.search(r'ProjectID=(\d+)', url)
        if match:
            return match.group(1)
        return None

    def _parse_results_alternative(self) -> List[Dict]:
        """Alternative parsing using BeautifulSoup"""
        from bs4 import BeautifulSoup
        projects = []

        try:
            soup = BeautifulSoup(self.driver.page_source, 'html.parser')

            # Debug: Count all links
            all_links = soup.find_all('a', href=True)
            print(f"Total links on page: {len(all_links)}")

            # Find all links that might be project links
            code_links = []
            go_links = []

            for link in all_links:
                href = link['href']
                title = link.get_text(strip=True)

                # Code projects with documents
                if 'ProjectLeadsDisplayProject.aspx?ProjectCode=' in href:
                    project_code = self._extract_project_code(href)
                    if project_code and title and len(title) > 3:
                        full_url = href if href.startswith('http') else f"{self.BASE_URL}/{href}"
                        code_links.append({
                            "source": "projectdog",
                            "project_code": project_code,
                            "interest_list_id": None,
                            "title": title,
                            "is_rfq": title.upper().startswith('RFQ '),
                            "has_documents": True,
                            "url": full_url,
                            "scraped_at": datetime.now().isoformat()
                        })

                # GO projects without documents
                elif 'ProjectLeadsLitePayment.aspx?InterestList=' in href:
                    match = re.search(r'InterestList=([A-Za-z0-9]+)', href)
                    if match and title and len(title) > 3:
                        interest_id = match.group(1)
                        full_url = href if href.startswith('http') else f"{self.BASE_URL}/{href}"
                        go_links.append({
                            "source": "projectdog",
                            "project_code": None,
                            "interest_list_id": interest_id,
                            "title": title,
                            "is_rfq": title.upper().startswith('RFQ '),
                            "has_documents": False,
                            "url": full_url,
                            "scraped_at": datetime.now().isoformat()
                        })

            print(f"Found {len(code_links)} Code project links (with documents)")
            print(f"Found {len(go_links)} GO project links (no documents)")

            # Deduplicate by project_code/interest_list_id
            seen_codes = set()
            seen_go_ids = set()

            for p in code_links:
                if p['project_code'] not in seen_codes:
                    seen_codes.add(p['project_code'])
                    projects.append(p)

            for p in go_links:
                if p['interest_list_id'] not in seen_go_ids:
                    seen_go_ids.add(p['interest_list_id'])
                    projects.append(p)

            print(f"After deduplication: {len(projects)} projects")

        except Exception as e:
            print(f"Alternative parsing failed: {e}")
            import traceback
            traceback.print_exc()

        return projects

    def get_project_details(self, project_code: str) -> Dict:
        """Fetch detailed info for a single project"""
        details = {
            "project_code": project_code,
            "is_dcam": False,
            "is_rfq": False,
            "project_type": "regular",  # regular, rfq, dcam
            "bid_date": None,
            "location": {},
            "owner": None,
            "architect": None,
            "contract_value": None,
            "prequalification_required": False,
            "documents_available": False,
            "document_recipients_url": None,
            "gc_ebid_available": False,
            "sub_ebid_available": False,
            "description": None,
            "divisions": [],
            "detail_scraped_at": datetime.now().isoformat()
        }

        try:
            url = self.PROJECT_URL.format(project_code)
            self.driver.get(url)
            time.sleep(2)

            # Parse page content
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(self.driver.page_source, 'html.parser')
            page_text = soup.get_text().lower()

            # Detect DCAM
            if 'dcam' in page_text or 'dcamm' in page_text or 'division of capital' in page_text:
                details["is_dcam"] = True
                details["project_type"] = "dcam"

            # Detect RFQ
            if 'rfq' in page_text or 'request for qualifications' in page_text:
                details["is_rfq"] = True
                details["project_type"] = "rfq"

            # Detect prequalification requirement
            if 'prequalification' in page_text or 'pre-qualification' in page_text:
                details["prequalification_required"] = True

            # Look for bid date
            bid_date_patterns = [
                r'bid\s*(?:date|due|opening)[:\s]*(\d{1,2}/\d{1,2}/\d{2,4})',
                r'bids?\s*due[:\s]*(\d{1,2}/\d{1,2}/\d{2,4})',
                r'(\d{1,2}/\d{1,2}/\d{2,4})\s*(?:bid|due)',
            ]
            for pattern in bid_date_patterns:
                match = re.search(pattern, page_text)
                if match:
                    details["bid_date"] = match.group(1)
                    break

            # Look for contract value
            value_patterns = [
                r'\$[\d,]+(?:\.\d{2})?',
                r'estimated\s*(?:cost|value)[:\s]*\$?([\d,]+)',
                r'contract\s*(?:amount|value)[:\s]*\$?([\d,]+)',
            ]
            for pattern in value_patterns:
                match = re.search(pattern, page_text)
                if match:
                    details["contract_value"] = match.group(0)
                    break

            # Check for document links
            acquire_docs = soup.find('a', href=lambda x: x and 'LegalNotice' in x)
            if acquire_docs:
                details["documents_available"] = True

            # Check for recipients link
            recipients_link = soup.find('a', href=lambda x: x and 'ProjectDocBidders' in x)
            if recipients_link:
                href = recipients_link.get('href', '')
                details["document_recipients_url"] = href if href.startswith('http') else f"{self.BASE_URL}/{href}"

            # Check for E-Bid options
            if 'DisplayGCEBidSecuredProject' in self.driver.page_source:
                details["gc_ebid_available"] = True
            if 'DisplaySubBidSecuredProject' in self.driver.page_source:
                details["sub_ebid_available"] = True

            # Try to extract specific fields from page structure
            details.update(self._parse_project_page_fields(soup))

        except Exception as e:
            print(f"Error getting project details for {project_code}: {e}")

        return details

    def _parse_project_page_fields(self, soup) -> Dict:
        """Parse specific fields from project detail page"""
        fields = {}

        try:
            # Look for common field patterns in ProjectDog pages
            # These use ASP.NET control IDs

            # Owner
            owner_elem = soup.find(id=lambda x: x and 'Owner' in str(x))
            if owner_elem:
                fields["owner"] = owner_elem.get_text(strip=True)

            # Location/Address
            location_elem = soup.find(id=lambda x: x and ('Location' in str(x) or 'Address' in str(x)))
            if location_elem:
                loc_text = location_elem.get_text(strip=True)
                fields["location"] = {"raw": loc_text}
                # Try to parse city/state
                state_match = re.search(r',\s*([A-Z]{2})\s*\d{5}', loc_text)
                if state_match:
                    fields["location"]["state"] = state_match.group(1)

            # Architect
            arch_elem = soup.find(id=lambda x: x and 'Architect' in str(x))
            if arch_elem:
                fields["architect"] = arch_elem.get_text(strip=True)

            # Description
            desc_elem = soup.find(id=lambda x: x and 'Description' in str(x))
            if desc_elem:
                fields["description"] = desc_elem.get_text(strip=True)[:500]

            # Look for tables with project info
            tables = soup.find_all('table')
            for table in tables:
                rows = table.find_all('tr')
                for row in rows:
                    cells = row.find_all(['td', 'th'])
                    if len(cells) >= 2:
                        label = cells[0].get_text(strip=True).lower()
                        value = cells[1].get_text(strip=True)

                        if 'owner' in label and not fields.get('owner'):
                            fields["owner"] = value
                        elif 'architect' in label and not fields.get('architect'):
                            fields["architect"] = value
                        elif 'location' in label or 'address' in label:
                            if not fields.get('location'):
                                fields["location"] = {"raw": value}
                        elif 'bid' in label and 'date' in label:
                            fields["bid_date"] = value

        except Exception as e:
            print(f"Error parsing project page fields: {e}")

        return fields

    def get_document_recipients(self, project_code: str) -> List[Dict]:
        """Get list of companies that have viewed/downloaded documents"""
        recipients = []

        try:
            url = self.RECIPIENTS_URL.format(project_code)
            self.driver.get(url)
            time.sleep(2)

            from bs4 import BeautifulSoup
            soup = BeautifulSoup(self.driver.page_source, 'html.parser')

            # Look for recipient table by ID
            recipients_table = soup.find('table', id='ctl00_ContentPlaceHolder1_ProjectBiddersDGrid')
            if recipients_table:
                rows = recipients_table.find_all('tr')
                for row in rows[1:]:  # Skip header
                    cells = row.find_all('td')
                    if len(cells) >= 8:
                        # Columns: Company, Name, Address, City, State, Zip, Phone, Fax, Type
                        company = cells[0].get_text(strip=True)
                        if company and company.lower() not in ['company', 'name', '']:
                            recipient = {
                                "company": company,
                                "contact_name": cells[1].get_text(strip=True) if len(cells) > 1 else "",
                                "address": cells[2].get_text(strip=True) if len(cells) > 2 else "",
                                "city": cells[3].get_text(strip=True) if len(cells) > 3 else "",
                                "state": cells[4].get_text(strip=True) if len(cells) > 4 else "",
                                "zip": cells[5].get_text(strip=True) if len(cells) > 5 else "",
                                "phone": cells[6].get_text(strip=True) if len(cells) > 6 else "",
                                "fax": cells[7].get_text(strip=True) if len(cells) > 7 else "",
                                "type": cells[8].get_text(strip=True) if len(cells) > 8 else ""
                            }
                            recipients.append(recipient)
            else:
                # Fallback to generic table parsing
                tables = soup.find_all('table')
                for table in tables:
                    rows = table.find_all('tr')
                    for row in rows[1:]:
                        cells = row.find_all('td')
                        if len(cells) >= 2:
                            company = cells[0].get_text(strip=True)
                            if company and company.lower() not in ['company', 'name', '']:
                                recipient = {
                                    "company": company,
                                    "raw_data": [c.get_text(strip=True) for c in cells]
                                }
                                recipients.append(recipient)

        except Exception as e:
            print(f"Error getting document recipients for {project_code}: {e}")

        return recipients

    def _get_session_cookies(self):
        """Get cookies from Selenium session for use with requests library"""
        if self.driver:
            selenium_cookies = self.driver.get_cookies()
            self.session_cookies = {cookie['name']: cookie['value'] for cookie in selenium_cookies}
        return self.session_cookies

    def accept_legal_notice(self, project_code: str) -> bool:
        """Accept the legal notice to access documents"""
        try:
            url = self.LEGAL_NOTICE_URL.format(project_code)
            self.driver.get(url)
            time.sleep(2)

            # Click the Accept button
            try:
                accept_button = WebDriverWait(self.driver, 10).until(
                    EC.element_to_be_clickable((By.ID, "ctl00_ContentPlaceHolder1_Accept"))
                )
                accept_button.click()
                time.sleep(2)

                # Verify we're on the file download page
                if 'FileDownload' in self.driver.current_url or 'Download' in self.driver.page_source:
                    print(f"Legal notice accepted for project {project_code}")
                    return True

            except TimeoutException:
                # Button might not exist if already accepted
                print(f"Accept button not found for {project_code} - may already be accepted")
                return True

        except Exception as e:
            print(f"Error accepting legal notice for {project_code}: {e}")

        return False

    def get_document_links(self, project_code: str) -> List[Dict]:
        """Get list of available documents with download URLs"""
        documents = []

        try:
            # First accept legal notice
            if not self.accept_legal_notice(project_code):
                print(f"Could not access documents for {project_code}")
                return []

            from bs4 import BeautifulSoup
            soup = BeautifulSoup(self.driver.page_source, 'html.parser')

            # Find all FileDownload links
            download_links = soup.find_all('a', href=lambda x: x and 'FileDownload.aspx' in x)

            for link in download_links:
                href = link.get('href', '')
                description = link.get_text(strip=True)

                if not description:
                    continue

                # Parse URL parameters
                parsed = urlparse(href)
                params = parse_qs(parsed.query)

                doc_id = params.get('ID', [None])[0]
                table_name = params.get('TableName', ['Unknown'])[0]

                # Try to find size from parent row
                size_kb = None
                parent_row = link.find_parent('tr')
                if parent_row:
                    cells = parent_row.find_all('td')
                    for cell in cells:
                        cell_text = cell.get_text(strip=True)
                        # Size is usually last column, numeric with K suffix
                        if re.match(r'^\d+$', cell_text):
                            size_kb = cell_text

                full_url = href if href.startswith('http') else f"{self.BASE_URL}/{href}"

                doc = {
                    "id": doc_id,
                    "type": table_name,  # "Specifications" or "Addenda"
                    "description": description,
                    "url": full_url,
                    "size_kb": size_kb,
                    "downloaded": False,
                    "filename": None
                }
                documents.append(doc)

            print(f"Found {len(documents)} documents for project {project_code}")

        except Exception as e:
            print(f"Error getting document links for {project_code}: {e}")
            import traceback
            traceback.print_exc()

        return documents

    def download_document(self, doc: Dict, output_folder: Path) -> Tuple[bool, Optional[str]]:
        """Download a single document using requests with Selenium cookies"""
        try:
            # Get session cookies if we don't have them
            if not self.session_cookies:
                self._get_session_cookies()

            # Make request with cookies
            response = requests.get(
                doc['url'],
                cookies=self.session_cookies,
                stream=True,
                timeout=60
            )

            if response.status_code != 200:
                print(f"Failed to download {doc['description']}: HTTP {response.status_code}")
                return False, None

            # Determine filename from Content-Disposition header or description
            filename = None
            content_disposition = response.headers.get('Content-Disposition', '')
            if 'filename=' in content_disposition:
                match = re.search(r'filename[^;=\n]*=(([\'"]).*?\2|[^;\n]*)', content_disposition)
                if match:
                    filename = match.group(1).strip('"\'')

            if not filename:
                # Use description as filename
                filename = sanitize_filename(doc['description'])
                # Add extension based on content type
                content_type = response.headers.get('Content-Type', '')
                if 'pdf' in content_type.lower():
                    if not filename.lower().endswith('.pdf'):
                        filename += '.pdf'
                elif 'zip' in content_type.lower():
                    if not filename.lower().endswith('.zip'):
                        filename += '.zip'

            # Ensure output folder exists
            output_folder.mkdir(parents=True, exist_ok=True)

            # Save file
            filepath = output_folder / filename
            with open(filepath, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)

            print(f"Downloaded: {filename}")
            return True, filename

        except Exception as e:
            print(f"Error downloading {doc['description']}: {e}")
            return False, None

    def download_project_documents(self, project_code: str, output_folder: Path) -> Dict:
        """Download all documents for a project"""
        result = {
            "project_code": project_code,
            "success": False,
            "documents": [],
            "error": None
        }

        try:
            # Get document links
            documents = self.get_document_links(project_code)

            if not documents:
                result["error"] = "No documents found"
                return result

            # Create subfolders for Specs and Addenda
            specs_folder = output_folder / "Specs"
            addenda_folder = output_folder / "Addenda"

            downloaded_docs = []
            for doc in documents:
                # Choose folder based on document type
                if doc['type'] == 'Addenda':
                    folder = addenda_folder
                else:
                    folder = specs_folder

                success, filename = self.download_document(doc, folder)
                doc['downloaded'] = success
                doc['filename'] = filename
                downloaded_docs.append(doc)

                # Rate limiting
                time.sleep(1)

            result["success"] = any(d['downloaded'] for d in downloaded_docs)
            result["documents"] = downloaded_docs

        except Exception as e:
            result["error"] = str(e)
            print(f"Error downloading documents for {project_code}: {e}")

        return result

    def make_project_folder_name(self, project: Dict) -> str:
        """Generate standardized folder name for a project"""
        title = project.get('title', 'Unknown Project')
        code = project.get('project_code')

        if not code and project.get('interest_list_id'):
            code = f"GO-{project['interest_list_id']}"

        # Truncate title if too long
        title = sanitize_filename(title)
        if len(title) > 50:
            title = title[:50]

        if code:
            return f"{title} - {code}"
        return title

    def scrape(self, include_details: bool = True, max_details: int = 50,
               include_recipients: bool = False, include_documents: bool = False) -> List[Dict]:
        """Full scrape workflow

        Args:
            include_details: Fetch detail page info for projects with codes
            max_details: Maximum number of projects to fetch details for
            include_recipients: Fetch document recipients list (slower)
            include_documents: Fetch document download links (requires accepting legal notice)
        """
        try:
            self._init_driver()

            if not self.login():
                print("Failed to login, aborting scrape")
                return []

            # Get search results - now captures ALL projects (Code + GO)
            projects = self.search_division8()

            # Count projects with documents
            projects_with_docs = [p for p in projects if p.get('has_documents') and p.get('project_code')]

            if include_details and projects_with_docs:
                print(f"Fetching details for up to {max_details} projects with documents...")
                for i, project in enumerate(projects_with_docs[:max_details]):
                    project_code = project.get('project_code')
                    if project_code:
                        print(f"  [{i+1}/{min(len(projects_with_docs), max_details)}] Getting details for {project_code}: {project.get('title', '')[:40]}")
                        details = self.get_project_details(project_code)
                        project.update(details)

                        # Get recipients if requested
                        if include_recipients:
                            recipients = self.get_document_recipients(project_code)
                            project['document_recipients'] = recipients
                            print(f"    Found {len(recipients)} document recipients")

                        # Get document links if requested
                        if include_documents:
                            documents = self.get_document_links(project_code)
                            project['documents'] = documents
                            print(f"    Found {len(documents)} downloadable documents")

                        time.sleep(1)  # Rate limiting

            self.projects = projects
            print(f"\nScrape complete: {len(projects)} Division 8 projects total")
            print(f"  - {len(projects_with_docs)} with documents (code)")
            print(f"  - {len(projects) - len(projects_with_docs)} without documents (GO)")
            print(f"  - {sum(1 for p in projects if p.get('is_rfq'))} RFQ projects")
            return projects

        finally:
            self._close_driver()

    def scrape_with_downloads(self, bidding_folder: Path, max_projects: int = 10) -> List[Dict]:
        """Full scrape workflow that also downloads documents to project folders

        Args:
            bidding_folder: Base folder to create project subfolders in
            max_projects: Maximum number of projects to download documents for
        """
        try:
            self._init_driver()

            if not self.login():
                print("Failed to login, aborting scrape")
                return []

            # Get search results
            projects = self.search_division8()

            # Get details and download documents for projects with codes
            projects_with_docs = [p for p in projects if p.get('has_documents') and p.get('project_code')]

            print(f"\nProcessing {min(len(projects_with_docs), max_projects)} projects for download...")

            for i, project in enumerate(projects_with_docs[:max_projects]):
                project_code = project.get('project_code')
                print(f"\n[{i+1}/{min(len(projects_with_docs), max_projects)}] {project.get('title', '')[:50]}")

                # Get detail page info
                details = self.get_project_details(project_code)
                project.update(details)

                # Get document recipients
                recipients = self.get_document_recipients(project_code)
                project['document_recipients'] = recipients
                print(f"  Found {len(recipients)} document recipients")

                # Create project folder
                folder_name = self.make_project_folder_name(project)
                project_folder = bidding_folder / folder_name
                project_folder.mkdir(parents=True, exist_ok=True)

                # Download documents
                result = self.download_project_documents(project_code, project_folder)
                project['documents'] = result.get('documents', [])
                project['documents_acquired'] = result.get('success', False)
                project['documents_folder'] = folder_name

                # Save metadata file
                metadata = {
                    "source": "projectdog",
                    "project_code": project_code,
                    "title": project.get('title'),
                    "scraped_at": datetime.now().isoformat(),
                    "bid_date": project.get('bid_date'),
                    "estimated_value": project.get('estimated_value'),
                    "location": project.get('location'),
                    "owner": project.get('owner'),
                    "architect": project.get('architect'),
                    "is_rfq": project.get('is_rfq'),
                    "is_dcam": project.get('is_dcam'),
                    "documents": project.get('documents', []),
                    "document_recipients": recipients
                }
                metadata_path = project_folder / "projectdog_metadata.json"
                with open(metadata_path, 'w') as f:
                    json.dump(metadata, f, indent=2)

                print(f"  Saved metadata to {folder_name}/projectdog_metadata.json")
                time.sleep(2)  # Rate limiting between projects

            self.projects = projects
            print(f"\nScrape complete: {len(projects)} Division 8 projects")
            return projects

        finally:
            self._close_driver()

    def save_results(self, filepath: str):
        """Save scraped results to JSON file"""
        # Calculate statistics
        projects_with_docs = sum(1 for p in self.projects if p.get('has_documents'))
        rfq_count = sum(1 for p in self.projects if p.get('is_rfq'))
        dcam_count = sum(1 for p in self.projects if p.get('is_dcam'))

        data = {
            "scraped_at": datetime.now().isoformat(),
            "source": "projectdog.com",
            "search_criteria": "Division 8",
            "project_count": len(self.projects),
            "projects_with_documents": projects_with_docs,
            "rfq_count": rfq_count,
            "dcam_count": dcam_count,
            "projects": self.projects
        }

        Path(filepath).parent.mkdir(parents=True, exist_ok=True)
        with open(filepath, 'w') as f:
            json.dump(data, f, indent=2)

        print(f"Saved {len(self.projects)} projects to {filepath}")


def scrape_projectdog(email: str, password: str, output_file: str = None,
                      headless: bool = True, include_details: bool = True,
                      include_recipients: bool = False, include_documents: bool = False) -> List[Dict]:
    """Convenience function to run the scraper

    Args:
        email: ProjectDog login email
        password: ProjectDog login password
        output_file: Path to save JSON results
        headless: Run browser in headless mode
        include_details: Fetch detail page info for projects with codes
        include_recipients: Fetch document recipients list
        include_documents: Fetch document download links
    """
    scraper = ProjectDogScraper(email, password, headless=headless)
    projects = scraper.scrape(
        include_details=include_details,
        include_recipients=include_recipients,
        include_documents=include_documents
    )

    if output_file and projects:
        scraper.save_results(output_file)

    return projects


def scrape_and_download(email: str, password: str, bidding_folder: str,
                        output_file: str = None, headless: bool = True,
                        max_projects: int = 10) -> List[Dict]:
    """Scrape ProjectDog and download documents to bidding folder

    Args:
        email: ProjectDog login email
        password: ProjectDog login password
        bidding_folder: Path to bidding folder for creating project subfolders
        output_file: Path to save JSON results
        headless: Run browser in headless mode
        max_projects: Maximum number of projects to download
    """
    scraper = ProjectDogScraper(email, password, headless=headless)
    projects = scraper.scrape_with_downloads(
        bidding_folder=Path(bidding_folder),
        max_projects=max_projects
    )

    if output_file and projects:
        scraper.save_results(output_file)

    return projects


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()

    email = os.getenv("PROJECTDOG_EMAIL")
    password = os.getenv("PROJECTDOG_PASSWORD")
    bidding_folder = os.getenv("BIDDING_FOLDER")

    if email and password:
        print("Starting ProjectDog scraper...")
        print(f"Bidding folder: {bidding_folder or 'Not set'}")

        projects = scrape_projectdog(
            email,
            password,
            output_file="static/data/projectdog_projects.json",
            headless=False,  # Set to False for debugging
            include_details=True,
            include_recipients=True,
            include_documents=True
        )

        print(f"\n{'='*60}")
        print(f"Scraped {len(projects)} projects")
        print(f"{'='*60}")

        # Show summary by type
        projects_with_docs = [p for p in projects if p.get('has_documents')]
        go_projects = [p for p in projects if not p.get('has_documents')]
        rfq_projects = [p for p in projects if p.get('is_rfq')]

        print(f"\nProjects with documents ({len(projects_with_docs)}):")
        for p in projects_with_docs[:5]:
            doc_count = len(p.get('documents', []))
            print(f"  - [{p.get('project_code')}] {p.get('title')[:40]} ({doc_count} docs)")

        print(f"\nGO Projects - no documents ({len(go_projects)}):")
        for p in go_projects[:5]:
            print(f"  - [GO-{p.get('interest_list_id')}] {p.get('title')[:40]}")

        print(f"\nRFQ Projects ({len(rfq_projects)}):")
        for p in rfq_projects[:5]:
            code = p.get('project_code') or f"GO-{p.get('interest_list_id')}"
            print(f"  - [{code}] {p.get('title')[:40]}")
    else:
        print("Missing PROJECTDOG_EMAIL or PROJECTDOG_PASSWORD in environment")
