"""
Hybrid Vision + HTML Website Scraper

Combines:
1. Vision models to understand page layout and extract visible text
2. HTML parsing to find navigation structure, dropdowns, and links
3. Recursive exploration of important pages (team members, projects)

Cost: ~$0.002-0.005/company depending on site depth
"""

import os
import asyncio
import base64
import requests
import logging
import tempfile
import re
from typing import Dict, List, Optional, Any, Set
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup
from pathlib import Path

logger = logging.getLogger(__name__)

# API Config
OPENROUTER_API_KEY = os.getenv('OPENROUTER_API_KEY')
GOOGLE_API_KEY = os.getenv('GOOGLE_API_KEY')
GOOGLE_CX = os.getenv('GOOGLE_CX')

# Vision models (in preference order)
VISION_MODELS = [
    "google/gemma-3-4b-it:free",
    "google/gemma-3-12b-it:free",
    "google/gemini-2.0-flash-lite-001",
]

# Skip these domains when searching for official website
SKIP_DOMAINS = [
    'yelp.com', 'linkedin.com', 'facebook.com', 'yellowpages.com',
    'bbb.org', 'glassdoor.com', 'indeed.com', 'buildzoom.com',
    # Legal/court sites
    'mass.gov', 'masscourts.org', 'trellis.law', 'casetext.com',
    'justia.com', 'leagle.com', 'courtlistener.com', 'docketbird.com',
    'pacermonitor.com', 'law.com', 'findlaw.com',
    # Government news sites
    'boston.gov', 'cityofboston.gov', 'state.ma.us', 'usa.gov',
    # Other non-company sites
    'wikipedia.org', 'bloomberg.com', 'crunchbase.com', 'manta.com',
    'dnb.com', 'zoominfo.com', 'hoovers.com', 'opencorporates.com',
    # News/media sites
    'bostonglobe.com', 'boston.com', 'wbur.org', 'wcvb.com',
    'patch.com', 'prnewswire.com', 'businesswire.com',
    'mvtimes.com', 'capecodtimes.com', 'wickedlocal.com',
    'legacy.com', 'tributes.com',  # Obituaries
]

# URL patterns that indicate news/articles (not company homepages)
NEWS_URL_PATTERNS = [
    '/news/', '/article/', '/story/', '/obituar', '/2024/', '/2023/', '/2022/',
    '/blog/', '/press-release/', '/announcement/',
]

# Keywords for categorizing nav links (ORDER MATTERS - more specific first!)
# Using list of tuples to maintain order
NAV_CATEGORIES_ORDERED = [
    ('team', ['team', 'people', 'staff', 'leadership', 'our-team', 'employees', 'meet-the-team']),
    ('contact', ['contact', 'get-in-touch', 'reach-us', 'locations']),
    ('portfolio', ['portfolio', 'projects', 'work', 'case-studies', 'gallery', 'our-work', 'featured']),
    ('services', ['services', 'what-we-do', 'capabilities', 'solutions', 'expertise', 'offerings']),
    ('careers', ['careers', 'jobs', 'employment', 'join-us', 'opportunities', 'hiring']),
    ('news', ['news', 'blog', 'updates', 'press', 'media', 'articles']),
    ('about', ['about', 'company', 'who-we-are', 'our-story', 'history', 'mission']),  # Last - most generic
]

NAV_CATEGORIES = {cat: kws for cat, kws in NAV_CATEGORIES_ORDERED}

# Request headers
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
}


def google_search(query: str, num_results: int = 5) -> List[Dict]:
    """Search Google Custom Search API."""
    if not GOOGLE_API_KEY or not GOOGLE_CX:
        logger.error("Google API key or CX not configured")
        return []
    try:
        response = requests.get(
            'https://www.googleapis.com/customsearch/v1',
            params={'key': GOOGLE_API_KEY, 'cx': GOOGLE_CX, 'q': query, 'num': min(num_results, 10)},
            timeout=10
        )
        if response.status_code != 200:
            return []
        return [
            {'title': item.get('title', ''), 'link': item.get('link', ''), 'snippet': item.get('snippet', '')}
            for item in response.json().get('items', [])
        ]
    except Exception as e:
        logger.error(f"Google search error: {e}")
        return []


def is_likely_company_homepage(url: str) -> bool:
    """Check if URL looks like a company homepage vs news article."""
    url_lower = url.lower()

    # Skip URLs with news article patterns
    if any(pattern in url_lower for pattern in NEWS_URL_PATTERNS):
        return False

    # Prefer root URLs or simple paths
    parsed = urlparse(url)
    path = parsed.path.strip('/')

    # Root domain or simple paths like /about, /contact are good
    if not path or path.count('/') == 0:
        return True

    # Deep paths with dates are likely articles
    if path.count('/') > 2:
        return False

    return True


def find_company_website(company_name: str, location: str = None) -> Optional[str]:
    """Find a company's official website via Google search."""

    def filter_and_rank(results: List[Dict]) -> Optional[str]:
        """Filter results and return best company website."""
        filtered = []
        for result in results:
            url = result.get('link', '')
            domain = urlparse(url).netloc.lower()

            # Skip bad domains
            if any(skip in domain for skip in SKIP_DOMAINS):
                continue

            # Skip news article URLs
            if not is_likely_company_homepage(url):
                continue

            filtered.append(result)

        if not filtered:
            return None

        # Prefer .com/.net domains (likely company websites)
        company_tlds = ['.com', '.net', '.co', '.construction', '.build']
        for result in filtered:
            url = result.get('link', '')
            domain = urlparse(url).netloc.lower()
            if any(domain.endswith(tld) for tld in company_tlds):
                return url

        return filtered[0].get('link')

    # Try multiple query strategies
    queries = []

    # 1. Simpler version without "Corp", "Inc", etc (often returns better results)
    simple_name = company_name
    for suffix in [' Corp', ' Inc', ' LLC', ' Ltd', ' Company', ' Co']:
        simple_name = simple_name.replace(suffix, '').replace(suffix.lower(), '')
    simple_name = simple_name.strip()

    if simple_name != company_name:
        queries.append(simple_name)  # Try without suffix first

    queries.append(company_name)  # Then full name

    for query in queries:
        logger.info(f"Searching: {query}")
        results = google_search(query, num_results=10)

        if not results:
            continue

        logger.info(f"  Got {len(results)} results")
        for i, r in enumerate(results[:3]):
            logger.info(f"    {i+1}. {r.get('link', '')}")

        best = filter_and_rank(results)
        if best:
            logger.info(f"Found website: {best}")
            return best

    # Fallback: return first result from any search
    logger.warning("No good candidates found")
    return None


def fetch_html(url: str, timeout: int = 15) -> Optional[str]:
    """Fetch page HTML."""
    try:
        response = requests.get(url, headers=HEADERS, timeout=timeout, allow_redirects=True)
        if response.status_code == 200:
            return response.text
    except Exception as e:
        logger.debug(f"Failed to fetch {url}: {e}")
    return None


def parse_nav_structure(html: str, base_url: str) -> Dict[str, List[Dict]]:
    """
    Parse navigation structure including dropdown menus.

    Returns dict of categorized links:
    {
        'about': [{'text': 'About Us', 'href': '/about'}, ...],
        'team': [{'text': 'Our Team', 'href': '/team'}, ...],
        ...
        'uncategorized': [...]
    }
    """
    soup = BeautifulSoup(html, 'html.parser')

    result = {cat: [] for cat in NAV_CATEGORIES}
    result['uncategorized'] = []
    seen_hrefs = set()

    # Find all nav-related elements
    nav_selectors = [
        'nav', 'header nav', '[role="navigation"]',
        '.navbar', '.nav', '.navigation', '.main-nav', '.primary-nav',
        '.menu', '.main-menu', '#menu', '#nav',
        'header', '.header', '#header',
    ]

    for selector in nav_selectors:
        try:
            for nav in soup.select(selector):
                # Find all links, including those in dropdowns
                for a in nav.find_all('a', href=True):
                    href = a.get('href', '').strip()
                    if not href or href == '#' or href.startswith('javascript:') or href.startswith('mailto:') or href.startswith('tel:'):
                        continue

                    full_url = urljoin(base_url, href)

                    # Skip external links
                    if urlparse(full_url).netloc != urlparse(base_url).netloc:
                        continue

                    if full_url in seen_hrefs:
                        continue
                    seen_hrefs.add(full_url)

                    text = a.get_text(strip=True)
                    href_lower = href.lower()
                    text_lower = text.lower()

                    # Categorize the link (using ordered list for priority)
                    categorized = False
                    for category, keywords in NAV_CATEGORIES_ORDERED:
                        if any(kw in href_lower or kw in text_lower for kw in keywords):
                            result[category].append({
                                'text': text,
                                'href': full_url,
                                'path': urlparse(full_url).path
                            })
                            categorized = True
                            break

                    if not categorized and text:
                        result['uncategorized'].append({
                            'text': text,
                            'href': full_url,
                            'path': urlparse(full_url).path
                        })
        except Exception as e:
            logger.debug(f"Error parsing nav with selector {selector}: {e}")

    return result


def parse_team_page_links(html: str, base_url: str) -> List[Dict]:
    """
    Parse a team page to find individual staff member links.

    Returns list of staff links: [{'name': '...', 'href': '...'}]
    """
    soup = BeautifulSoup(html, 'html.parser')
    staff_links = []
    seen = set()

    # Common patterns for team member cards/links
    team_selectors = [
        '.team-member a', '.staff-member a', '.person a', '.employee a',
        '[class*="team"] a', '[class*="staff"] a', '[class*="member"] a',
        '.leadership a', '.management a', '.bio a',
        'article a', '.card a',
    ]

    for selector in team_selectors:
        try:
            for a in soup.select(selector):
                href = a.get('href', '').strip()
                if not href or href == '#' or not href.startswith(('/', 'http')):
                    continue

                full_url = urljoin(base_url, href)

                # Skip external and already seen
                if urlparse(full_url).netloc != urlparse(base_url).netloc:
                    continue
                if full_url in seen:
                    continue

                # Check if this looks like a person page
                path_lower = urlparse(full_url).path.lower()
                if any(x in path_lower for x in ['/team/', '/staff/', '/people/', '/about/', '/leadership/']):
                    seen.add(full_url)

                    # Try to get name from link text or nearby heading
                    name = a.get_text(strip=True)
                    if not name or len(name) < 3:
                        # Try to find name in parent
                        parent = a.find_parent(['div', 'article', 'li'])
                        if parent:
                            heading = parent.find(['h2', 'h3', 'h4', 'h5'])
                            if heading:
                                name = heading.get_text(strip=True)

                    if name and len(name) > 2:
                        staff_links.append({
                            'name': name,
                            'href': full_url
                        })
        except Exception as e:
            logger.debug(f"Error with team selector {selector}: {e}")

    return staff_links


def extract_contact_from_html(html: str) -> Dict:
    """Extract contact info using regex patterns on HTML/text."""
    soup = BeautifulSoup(html, 'html.parser')
    text = soup.get_text(separator=' ')

    # Patterns
    phone_pattern = re.compile(r'[\(]?\d{3}[\)\-\.\s]?\s?\d{3}[\-\.\s]?\d{4}')
    email_pattern = re.compile(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}')

    phones = list(set(phone_pattern.findall(text)))
    emails = [e for e in set(email_pattern.findall(text))
              if not any(x in e.lower() for x in ['example', 'test', 'sentry', 'wix'])]

    # Try to find address in footer or contact sections
    address = None
    for section in soup.select('footer, .contact, .address, [class*="contact"], [class*="address"]'):
        section_text = section.get_text(separator=' ')
        # Look for address patterns
        addr_match = re.search(r'\d+\s+[\w\s]+(?:Street|St|Avenue|Ave|Road|Rd|Boulevard|Blvd|Drive|Dr|Way|Lane|Ln)[,.\s]+[\w\s]+,?\s*[A-Z]{2}\s*\d{5}', section_text, re.IGNORECASE)
        if addr_match:
            address = addr_match.group().strip()
            break

    # Social links
    social = {}
    for a in soup.find_all('a', href=True):
        href = a.get('href', '').lower()
        if 'linkedin.com' in href:
            social['linkedin'] = a.get('href')
        elif 'facebook.com' in href:
            social['facebook'] = a.get('href')
        elif 'instagram.com' in href:
            social['instagram'] = a.get('href')
        elif 'twitter.com' in href or 'x.com' in href:
            social['twitter'] = a.get('href')

    return {
        'phones': phones[:3],  # Limit
        'emails': emails[:3],
        'address': address,
        'social': social
    }


async def screenshot_page(url: str, output_path: str, full_page: bool = False) -> bool:
    """Take a screenshot using Playwright.

    Args:
        url: Page URL
        output_path: Where to save screenshot
        full_page: If True, captures full scrollable page (includes footer)
    """
    try:
        from playwright.async_api import async_playwright

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page(viewport={'width': 1280, 'height': 900})
            try:
                await page.goto(url, wait_until='domcontentloaded', timeout=20000)
                await page.wait_for_timeout(2000)
                await page.screenshot(path=output_path, full_page=full_page)
                return True
            except Exception as e:
                logger.debug(f"Screenshot failed for {url}: {e}")
                return False
            finally:
                await browser.close()
    except ImportError:
        logger.error("Playwright not installed")
        return False


def call_vision_model(image_path: str, prompt: str) -> Optional[Dict]:
    """Call vision model and return parsed JSON."""
    if not OPENROUTER_API_KEY:
        return None

    with open(image_path, 'rb') as f:
        img_base64 = base64.b64encode(f.read()).decode('utf-8')

    for model in VISION_MODELS:
        try:
            response = requests.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                    "HTTP-Referer": "https://project-tracker.local",
                },
                json={
                    "model": model,
                    "messages": [{
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img_base64}"}}
                        ]
                    }],
                    "temperature": 0.2,
                    "max_tokens": 1500
                },
                timeout=60
            )

            if response.status_code == 200:
                content = response.json()['choices'][0]['message']['content']
                import json
                json_match = re.search(r'\{[\s\S]*\}', content)
                if json_match:
                    try:
                        return json.loads(json_match.group())
                    except:
                        return {'raw': content}
                return {'raw': content}
            elif response.status_code == 404:
                continue
        except Exception as e:
            logger.debug(f"Vision error with {model}: {e}")
            continue
    return None


# Vision prompts - FLEXIBLE: model can add any relevant fields it finds
HOMEPAGE_PROMPT = """Analyze this company website homepage. Extract ALL visible information about the company.

Required fields (use null if not found):
- company_name: Name shown in logo/header
- tagline: Any slogan or tagline
- description: Brief description if visible
- founded: Year founded if mentioned
- headquarters: Address if shown (check footer!)
- phone: Phone number if visible
- email: Email if visible

Many homepages contain "About Us" info - look for:
- History/founding story
- Company values/mission
- Certifications (WBE, LEED, MBE, etc)
- Leadership names
- Employee count/team size

IMPORTANT: Check the FOOTER area for address, phone, and contact info.

Return as JSON with all information found. Add any additional fields that are relevant."""

ABOUT_PROMPT = """Analyze this company About/Company page. Extract ALL information about the company.

Look for (use null if not found):
- founded: Year founded
- description: Company description/mission
- leadership: People mentioned with their titles
- headquarters: Address/location
- employee_count: Team size
- certifications: Any certifications (WBE, LEED, MBE, etc)

Also extract ANY other information visible - history, specialties, awards, values, etc. Add as additional fields.

Return as JSON. Include everything you find, nesting related data logically."""

STAFF_PROMPT = """Analyze this staff member's page. Extract ALL information about this person.

Look for:
- name: Full name
- title: Job title/position
- bio: Biography text
- email: Email address
- phone: Phone number

Also extract ANY other info: education, certifications, years of experience, specialties, projects they've worked on, professional affiliations, etc.

Return as JSON with all information found."""

TEAM_LIST_PROMPT = """Analyze this team/staff page. List ALL people shown with as much detail as possible.

For each person, extract:
- name: Full name
- title: Job title/position
- And any other visible info (email, phone, department, bio snippet, certifications)

Return JSON: {"people": [...], "departments": [...if visible], "total_count": X}

Include any organizational structure or groupings you observe."""

PORTFOLIO_PROMPT = """Analyze this portfolio/projects page. Extract information about ALL projects shown.

For each project, extract:
- name: Project name
- type: Project type (healthcare, education, commercial, residential, etc.)
- location: City/state if shown
- size: Square footage or other size metrics
- client: Client/owner name if shown
- status: Completed, in-progress, etc.
- year: Completion year if shown
- description: Brief description

Return JSON: {"projects": [...], "specialties": ["healthcare", "education", ...based on projects], "total_projects_shown": X}"""

PROJECT_DETAIL_PROMPT = """Analyze this individual project page. Extract ALL details about this project.

Look for:
- name: Project name
- type: Project type/category
- client: Client/owner
- location: Full address or city
- size: Square footage, beds, units, etc.
- scope: Description of work
- completion: Year completed
- value: Project value if shown
- architect: Architect name
- awards: Any awards won

Return JSON with all details found. Include any additional relevant information."""

CONTACT_PROMPT = """Analyze this contact page. Extract ALL contact information visible.

Look for:
- address: Full street address (street, city, state, zip)
- headquarters: Main office location
- phone: Phone number(s)
- email: Email address(es)
- fax: Fax number if shown
- office_hours: Business hours if shown
- branches: Any additional office locations

IMPORTANT: Check the footer area carefully for address information.

Return JSON with all contact details found."""


async def scrape_company_deep(
    company_name: str,
    location: str = None,
    website_url: str = None,
    max_staff_pages: int = 10,
    explore_portfolio: bool = False,
    progress_callback: callable = None,
    screenshot_dir: str = None
) -> Dict[str, Any]:
    """
    Deep scrape a company website using vision + HTML parsing.

    Args:
        company_name: Company name
        location: Optional location hint
        website_url: Optional known URL (skips search)
        max_staff_pages: Max individual staff pages to visit
        explore_portfolio: Whether to explore project pages
        progress_callback: Optional callback for progress updates
        screenshot_dir: Optional directory to save screenshots for UI display

    Returns:
        Comprehensive company data dictionary
    """
    def emit(event_type: str, **kwargs):
        """Helper to emit progress events."""
        if progress_callback:
            try:
                progress_callback({'type': event_type, **kwargs})
            except Exception as e:
                logger.debug(f"Progress callback error: {e}")

    result = {
        'company_name': company_name,
        'website': None,
        'nav_structure': {},
        'homepage_data': {},
        'about_data': {},
        'team_data': {'list': [], 'individuals': []},
        'contact_data': {},
        'portfolio_data': [],
        'pages_visited': [],
        'aggregated': {}
    }

    # Helper to copy screenshots for UI
    import shutil
    page_index = 0
    total_pages = 6  # Estimate

    def save_screenshot_for_ui(src_path: str, page_name: str) -> str:
        """Copy screenshot to UI-accessible folder and return URL."""
        nonlocal page_index
        page_index += 1
        if screenshot_dir and os.path.exists(src_path):
            try:
                os.makedirs(screenshot_dir, exist_ok=True)
                dest_name = f"{page_index:02d}_{page_name}.png"
                dest_path = os.path.join(screenshot_dir, dest_name)
                shutil.copy2(src_path, dest_path)
                # Return relative URL for frontend
                return f"/static/research_screenshots/{os.path.basename(screenshot_dir)}/{dest_name}"
            except Exception as e:
                logger.debug(f"Failed to save screenshot: {e}")
        return None

    # Step 1: Find website
    emit('agent.step', step_name='find', state='running', detail=f'Searching for {company_name}...')
    if not website_url:
        logger.info(f"Searching for {company_name} website...")
        website_url = find_company_website(company_name, location)

    if not website_url:
        logger.warning(f"Could not find website for {company_name}")
        emit('agent.step', step_name='find', state='failed', detail='Could not find website')
        return result

    emit('agent.step', step_name='find', state='done', detail=f'Found: {website_url}')
    result['website'] = website_url
    base_url = f"{urlparse(website_url).scheme}://{urlparse(website_url).netloc}"

    with tempfile.TemporaryDirectory() as tmpdir:

        # Step 2: Fetch and parse homepage HTML for nav structure
        logger.info(f"Fetching homepage: {website_url}")
        emit('agent.step', step_name='screenshot', state='running', detail='Fetching homepage...')
        html = fetch_html(website_url)

        if html:
            nav_structure = parse_nav_structure(html, base_url)
            result['nav_structure'] = nav_structure
            contact_info = extract_contact_from_html(html)
            result['contact_data'] = contact_info

            logger.info(f"Found nav categories: {[k for k, v in nav_structure.items() if v]}")

        # Step 3: Screenshot homepage + vision analysis (full page to capture footer with address)
        homepage_path = f"{tmpdir}/homepage.png"
        if await screenshot_page(website_url, homepage_path, full_page=True):
            result['pages_visited'].append(website_url)
            thumb_url = save_screenshot_for_ui(homepage_path, 'homepage')
            emit('viewer.frame', label='LOOKING AT: Homepage', page_index=page_index, page_total=total_pages,
                 source_kind='website', thumb_url=thumb_url, banner='Scanning homepage for company info...')
            emit('agent.step', step_name='extract', state='running', detail='Analyzing homepage with vision model...')
            homepage_data = call_vision_model(homepage_path, HOMEPAGE_PROMPT)
            if homepage_data:
                result['homepage_data'] = homepage_data
                emit('viewer.caption', text=f"Found: {homepage_data.get('company_name', company_name)}")

        # Step 4: Visit About page (full page for footer)
        about_links = result['nav_structure'].get('about', [])
        for link in about_links[:1]:  # First about link
            about_url = link['href']
            logger.info(f"Visiting about page: {about_url}")

            about_path = f"{tmpdir}/about.png"
            if await screenshot_page(about_url, about_path, full_page=True):
                result['pages_visited'].append(about_url)
                thumb_url = save_screenshot_for_ui(about_path, 'about')
                emit('viewer.frame', label='LOOKING AT: About', page_index=page_index, page_total=total_pages,
                     source_kind='about', thumb_url=thumb_url, banner='Looking for founding date, mission...')
                about_data = call_vision_model(about_path, ABOUT_PROMPT)
                if about_data:
                    result['about_data'] = about_data
                    emit('viewer.caption', text=f"Founded: {about_data.get('founded', 'unknown')}")

        # Step 5: Visit Team page and explore individual staff
        team_links = result['nav_structure'].get('team', [])
        for link in team_links[:1]:  # First team link
            team_url = link['href']
            logger.info(f"Visiting team page: {team_url}")

            team_html = fetch_html(team_url)
            team_path = f"{tmpdir}/team.png"

            if await screenshot_page(team_url, team_path):
                result['pages_visited'].append(team_url)
                thumb_url = save_screenshot_for_ui(team_path, 'team')
                emit('viewer.frame', label='LOOKING AT: Team', page_index=page_index, page_total=total_pages,
                     source_kind='team', thumb_url=thumb_url, banner='Extracting team members...')

                # Vision: Get visible team members
                team_vision = call_vision_model(team_path, TEAM_LIST_PROMPT)
                if team_vision and team_vision.get('people'):
                    result['team_data']['list'] = team_vision['people']
                    emit('viewer.caption', text=f"Found {len(team_vision['people'])} team members")

                # HTML: Find individual staff page links
                if team_html:
                    staff_links = parse_team_page_links(team_html, base_url)
                    logger.info(f"Found {len(staff_links)} staff page links")

                    # Visit individual staff pages (limited)
                    for i, staff in enumerate(staff_links[:max_staff_pages]):
                        staff_url = staff['href']
                        logger.info(f"  Visiting staff page ({i+1}/{min(len(staff_links), max_staff_pages)}): {staff['name']}")

                        staff_path = f"{tmpdir}/staff_{i}.png"
                        if await screenshot_page(staff_url, staff_path):
                            result['pages_visited'].append(staff_url)
                            thumb_url = save_screenshot_for_ui(staff_path, f'staff_{i}')
                            emit('viewer.frame', label=f'LOOKING AT: {staff["name"][:20]}', page_index=page_index, page_total=total_pages,
                                 source_kind='staff', thumb_url=thumb_url, banner=f'Extracting bio for {staff["name"]}...')
                            staff_data = call_vision_model(staff_path, STAFF_PROMPT)
                            if staff_data:
                                result['team_data']['individuals'].append(staff_data)

        # Step 6: Visit Contact page for more contact info (full page for addresses in footer)
        contact_links = result['nav_structure'].get('contact', [])
        for link in contact_links[:1]:
            contact_url = link['href']
            logger.info(f"Visiting contact page: {contact_url}")

            contact_html = fetch_html(contact_url)
            contact_path = f"{tmpdir}/contact.png"

            # Screenshot contact page with vision analysis for address extraction
            if await screenshot_page(contact_url, contact_path, full_page=True):
                result['pages_visited'].append(contact_url)
                thumb_url = save_screenshot_for_ui(contact_path, 'contact')
                emit('viewer.frame', label='LOOKING AT: Contact', page_index=page_index, page_total=total_pages,
                     source_kind='contact', thumb_url=thumb_url, banner='Extracting contact information...')
                contact_vision = call_vision_model(contact_path, CONTACT_PROMPT)
                if contact_vision:
                    result['contact_vision'] = contact_vision
                    # Merge address from vision into contact_data
                    if contact_vision.get('address'):
                        addr = contact_vision['address']
                        # Convert dict to string if needed
                        if isinstance(addr, dict):
                            addr = addr.get('address') or addr.get('full') or str(addr)
                        result['contact_data']['address'] = addr
                        emit('viewer.caption', text=f"Address found: {str(addr)[:50]}...")
                    if contact_vision.get('headquarters') and not result['contact_data'].get('address'):
                        result['contact_data']['address'] = contact_vision['headquarters']

            # Also extract from HTML
            if contact_html:
                page_contact = extract_contact_from_html(contact_html)
                # Merge with existing contact data
                for key, val in page_contact.items():
                    if val and not result['contact_data'].get(key):
                        result['contact_data'][key] = val

        # Step 7: Explore portfolio (always do this - valuable data)
        portfolio_links = result['nav_structure'].get('portfolio', [])
        if portfolio_links:
            # Visit main portfolio page
            portfolio_url = portfolio_links[0]['href']
            logger.info(f"Visiting portfolio page: {portfolio_url}")

            portfolio_html = fetch_html(portfolio_url)
            portfolio_path = f"{tmpdir}/portfolio.png"

            if await screenshot_page(portfolio_url, portfolio_path):
                result['pages_visited'].append(portfolio_url)
                thumb_url = save_screenshot_for_ui(portfolio_path, 'portfolio')
                emit('viewer.frame', label='LOOKING AT: Portfolio', page_index=page_index, page_total=total_pages,
                     source_kind='portfolio', thumb_url=thumb_url, banner='Extracting project portfolio...')

                # Vision: Extract project list
                portfolio_vision = call_vision_model(portfolio_path, PORTFOLIO_PROMPT)
                if portfolio_vision:
                    result['portfolio_data'] = portfolio_vision
                    proj_count = len(portfolio_vision.get('projects', []))
                    emit('viewer.caption', text=f"Found {proj_count} projects in portfolio")

                # Find individual project links
                if portfolio_html and explore_portfolio:
                    soup = BeautifulSoup(portfolio_html, 'html.parser')
                    project_links = []

                    # Common patterns for project cards
                    for a in soup.select('a[href*="project"], a[href*="portfolio"], .project a, .portfolio-item a, article a'):
                        href = a.get('href', '')
                        if href and '/portfolio/' in href or '/project/' in href or '/work/' in href:
                            full_url = urljoin(base_url, href)
                            if full_url not in [l.get('href') for l in project_links]:
                                project_links.append({'href': full_url, 'text': a.get_text(strip=True)})

                    # Visit top 3 project detail pages
                    for i, proj in enumerate(project_links[:3]):
                        proj_url = proj['href']
                        logger.info(f"  Visiting project ({i+1}/3): {proj['text'][:30]}...")

                        proj_path = f"{tmpdir}/project_{i}.png"
                        if await screenshot_page(proj_url, proj_path):
                            result['pages_visited'].append(proj_url)
                            thumb_url = save_screenshot_for_ui(proj_path, f'project_{i}')
                            emit('viewer.frame', label=f'LOOKING AT: {proj["text"][:20]}', page_index=page_index, page_total=total_pages,
                                 source_kind='project', thumb_url=thumb_url, banner=f'Extracting project details...')
                            proj_data = call_vision_model(proj_path, PROJECT_DETAIL_PROMPT)
                            if proj_data:
                                if 'project_details' not in result:
                                    result['project_details'] = []
                                result['project_details'].append(proj_data)

        # Mark screenshot step done
        emit('agent.step', step_name='screenshot', state='done', detail=f'Visited {len(result["pages_visited"])} pages')
        emit('agent.step', step_name='extract', state='done', detail='Vision analysis complete')

    # Step 8: Aggregate all data
    emit('agent.step', step_name='summarize', state='running', detail='Aggregating all data...')
    result['aggregated'] = aggregate_all_data(result)
    emit('agent.step', step_name='summarize', state='done', detail='Profile complete')

    logger.info(f"Completed! Visited {len(result['pages_visited'])} pages")

    return result


def aggregate_all_data(result: Dict) -> Dict:
    """Combine all extracted data into final profile."""
    agg = {
        'company_name': None,
        'website': result.get('website'),
        'founded': None,
        'headquarters': None,
        'phone': None,
        'email': None,
        'description': None,
        'tagline': None,
        'employee_count': None,
        'certifications': [],
        'leadership': [],
        'staff': [],
        'services': [],
        'social_links': {},
    }

    # From homepage (often has lots of info including footer data)
    hp = result.get('homepage_data', {})
    agg['company_name'] = hp.get('company_name') or result.get('company_name')
    agg['tagline'] = hp.get('tagline')
    if hp.get('description'):
        agg['description'] = hp['description']
    if hp.get('founded'):
        agg['founded'] = hp['founded']
    if hp.get('headquarters'):
        agg['headquarters'] = hp['headquarters']
    if hp.get('phone'):
        agg['phone'] = hp['phone']
    if hp.get('email'):
        agg['email'] = hp['email']
    if hp.get('certifications'):
        agg['certifications'].extend(hp['certifications'])
    if hp.get('leadership'):
        for person in hp['leadership']:
            if isinstance(person, dict) and person.get('name'):
                agg['leadership'].append(person)
            elif isinstance(person, str):
                agg['leadership'].append({'name': person})

    # From about page
    about = result.get('about_data', {})
    if about.get('founded'):
        agg['founded'] = about['founded']
    if about.get('description') and not agg['description']:
        agg['description'] = about['description']
    if about.get('headquarters'):
        agg['headquarters'] = about['headquarters']
    if about.get('employee_count'):
        agg['employee_count'] = about['employee_count']
    if about.get('certifications'):
        for c in about['certifications']:
            if c not in agg['certifications']:
                agg['certifications'].append(c)
    if about.get('leadership'):
        agg['leadership'].extend(about['leadership'])

    # From team data
    team = result.get('team_data', {})

    # Add individuals (more detailed)
    for person in team.get('individuals', []):
        if person.get('name'):
            # Check if this person is leadership
            title = (person.get('title') or '').lower()
            is_leader = any(t in title for t in ['president', 'ceo', 'coo', 'cfo', 'founder', 'principal', 'owner', 'chairman', 'director'])

            entry = {
                'name': person['name'],
                'title': person.get('title'),
                'bio': person.get('bio'),
                'email': person.get('email'),
                'phone': person.get('phone')
            }

            if is_leader:
                agg['leadership'].append(entry)
            else:
                agg['staff'].append(entry)

    # Add from list (less detailed) if not already present
    known_names = {p['name'] for p in agg['leadership'] + agg['staff']}
    for person in team.get('list', []):
        if person.get('name') and person['name'] not in known_names:
            agg['staff'].append({
                'name': person['name'],
                'title': person.get('title')
            })

    # From contact data
    contact = result.get('contact_data', {})
    if contact.get('phones'):
        agg['phone'] = contact['phones'][0]
    if contact.get('emails'):
        agg['email'] = contact['emails'][0]
    if contact.get('address') and not agg['headquarters']:
        agg['headquarters'] = contact['address']
    if contact.get('social'):
        agg['social_links'].update(contact['social'])

    return agg


# Sync wrapper
def scrape_company_sync(
    company_name: str,
    location: str = None,
    website_url: str = None,
    max_staff_pages: int = 10
) -> Dict:
    """Synchronous wrapper."""
    return asyncio.run(scrape_company_deep(
        company_name, location, website_url, max_staff_pages
    ))


if __name__ == "__main__":
    import json
    logging.basicConfig(level=logging.INFO, format='%(message)s')

    result = scrape_company_sync("Kaplan Construction", "Brookline, MA")
    print(json.dumps(result['aggregated'], indent=2, default=str))
