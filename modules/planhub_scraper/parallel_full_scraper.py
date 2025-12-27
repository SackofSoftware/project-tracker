#!/usr/bin/env python3
"""
Parallel Full Scraper - Fast + Complete
Combines parallel workers (4x speed) with full tab scraping (all data).

Usage:
    python3 parallel_full_scraper.py          # Scrape all queued leads
    python3 parallel_full_scraper.py --limit 10   # Scrape first 10 leads
    python3 parallel_full_scraper.py --workers 2  # Use 2 workers instead of 4
"""
import sys
import time
import json
import re
import sqlite3
from concurrent.futures import ThreadPoolExecutor, as_completed
from playwright.sync_api import sync_playwright
from .config import SESSION_FILE, BASE_URL

# Default settings
PARALLEL_WORKERS = 4
PAGE_WAIT = 5  # seconds between tabs (Angular needs time to load)
MAX_LEADS = None  # None = all


def wait_for_angular_content(page, timeout=15):
    """Wait for Angular content to load (no spinners, has content)."""
    start = time.time()
    while time.time() - start < timeout:
        # Check if loading spinner is gone
        spinner = page.query_selector("mat-spinner, .mat-progress-spinner, .loading, .spinner")
        if not spinner:
            # Check for actual content
            content = page.query_selector("h1, .project-title, table, .card, mat-card, .details, p")
            if content:
                return True
        time.sleep(0.5)
    return False


def extract_full_project_data(page, lead_id: str, lead_name: str) -> dict:
    """Extract ALL data from ALL tabs for a single lead."""
    data = {
        'lead_id': lead_id,
        'name': lead_name,
        'scraped_at': time.strftime('%Y-%m-%d %H:%M:%S')
    }

    try:
        # ===== TAB 1: PROJECT INFO =====
        url = f'{BASE_URL}/leads/details/{lead_id}/project-info'
        page.goto(url, wait_until='domcontentloaded')
        wait_for_angular_content(page)
        time.sleep(PAGE_WAIT)

        page_text = page.inner_text('body')

        # Bid date
        match = re.search(r'Bid Due Date\s*(\d{1,2}/\d{1,2}/\d{4})\s*at\s*(\d{1,2}:\d{2}\s*[AP]M)', page_text)
        if match:
            data['bid_date'] = f"{match.group(1)} {match.group(2)}"

        # Location
        lines = page_text.split('\n')
        states = r'(MA|CT|NH|RI|VT|ME|NY|NJ|PA|FL|CA|TX|GA|OH|MI|IL|WA|OR|AZ|CO|NC|VA|MD|SC|TN|AL|KY|LA|MO|IN|WI|MN|OK|KS|AR|MS|NV|NM|WV|NE|ID|HI|DE|DC)'
        skip_words = ['WORKSPACE', 'CHECKLIST', 'INFO@', 'PLANHUB', 'PROJECT INFO',
                      'BIDDING', 'MARKET INTEL', 'FILES', 'CONTRACTORS', 'SUBMIT BID']

        for i, line in enumerate(lines):
            line = line.strip()
            if len(line) < 8 or len(line) > 60:
                continue
            if any(x in line.upper() for x in skip_words):
                continue

            city_match = re.search(rf'^\s*([A-Za-z][A-Za-z\s]+),?\s*{states}\s+(\d{{5}})\s*$', line)
            if city_match:
                city_line = line
                street_parts = []
                for j in range(i-1, max(i-4, -1), -1):
                    prev_line = lines[j].strip()
                    if len(prev_line) < 3 or len(prev_line) > 80:
                        break
                    if any(x in prev_line.upper() for x in skip_words):
                        break
                    if re.search(r'\d+|Street|St|Road|Rd|Ave|Avenue|Drive|Dr|Way|Lane|Ln|Blvd|Hwy|Square|Circle', prev_line, re.I):
                        street_parts.insert(0, prev_line)
                    else:
                        break

                if street_parts:
                    data['location'] = f"{' '.join(street_parts)}, {city_line}"
                else:
                    data['location'] = city_line
                break

        # Project Value
        match = re.search(r'\$([\d,]+\.?\d*)\s*Project\s*value', page_text)
        if match:
            data['project_value'] = f"${match.group(1)}"

        # Project Size
        match = re.search(r'([\d,]+\.?\d*)\s*SF\s*Project size', page_text)
        if match:
            data['project_size'] = f"{match.group(1)} SF"

        # Description
        match = re.search(r'(This project calls for[^\.]+\.)', page_text)
        if match:
            data['description'] = match.group(1).strip()

        # Start/End dates
        match = re.search(r'([A-Z][a-z]+ \d{1,2}, \d{4})\s*Start Date', page_text)
        if match:
            data['start_date'] = match.group(1)

        match = re.search(r'([A-Z][a-z]+ \d{1,2}, \d{4})\s*End date', page_text)
        if match:
            data['end_date'] = match.group(1)

        # Tags
        tags = []
        for tag in ['GC Awarded', 'Sub Bidding', 'Commercial', 'Retail', 'Renovation', 'New Construction', 'Residential', 'Industrial']:
            if tag in page_text:
                tags.append(tag)
        if tags:
            data['tags'] = tags

        # ===== TAB 2: PROJECT FILES =====
        files_url = f'{BASE_URL}/leads/details/{lead_id}/project-files'
        page.goto(files_url, wait_until='domcontentloaded')
        wait_for_angular_content(page)
        time.sleep(PAGE_WAIT)

        page_text = page.inner_text('body')
        files = []

        # Get total count
        count_match = re.search(r'(\d+)\s*total', page_text, re.I)
        if count_match:
            total_count = int(count_match.group(1))

        # Extract file data
        doc_matches = re.findall(
            r'([A-Za-z0-9][^\n]{5,50})\s+(\d+\.?\d*\s*(?:kB|MB|GB))\s+(Specs|Plans|Addendums|Drawings|Other|[A-Za-z ]+)\s+(\d{1,2}/\d{1,2}/\d{4})',
            page_text
        )
        for match in doc_matches[:20]:
            files.append({
                'file_name': match[0].strip(),
                'size': match[1],
                'document_type': match[2],
                'date_added': match[3]
            })

        if files:
            data['files'] = files
            data['files_count'] = len(files)

        # ===== TAB 3: GENERAL CONTRACTORS =====
        gc_url = f'{BASE_URL}/leads/details/{lead_id}/general-contractors'
        page.goto(gc_url, wait_until='domcontentloaded')
        wait_for_angular_content(page)
        time.sleep(PAGE_WAIT)

        phones = page.query_selector_all("a[href^='tel:']")
        emails = page.query_selector_all("a[href^='mailto:']")

        contractors = []
        seen = set()
        for i, phone in enumerate(phones[:10]):
            phone_text = phone.inner_text().strip()
            if phone_text and phone_text not in seen:
                seen.add(phone_text)
                gc = {'phone': phone_text}
                if i < len(emails):
                    gc['email'] = emails[i].inner_text().strip()

                # Try to get company name
                try:
                    parent = phone.evaluate_handle("el => el.closest('mat-card, .connection, [class*=\"contractor\"]')")
                    if parent:
                        name_elem = parent.as_element().query_selector("h3, h4, .company-name, .contractor-name")
                        if name_elem:
                            gc['company_name'] = name_elem.inner_text().strip()
                except:
                    pass

                contractors.append(gc)

        if contractors:
            data['contractors'] = contractors
            data['contractors_count'] = len(contractors)

        # ===== TAB 4: MARKET INTELLIGENCE =====
        intel_url = f'{BASE_URL}/leads/details/{lead_id}/market-intelligence'
        page.goto(intel_url, wait_until='domcontentloaded')
        wait_for_angular_content(page)
        time.sleep(PAGE_WAIT)

        page_text = page.inner_text('body')
        market_intel = {'downloads_by_scope': []}

        trades = [
            'Exterior Doors', 'Interior Doors', 'Glazing', 'Storefronts', 'Curtain Walls',
            'Glass and Mirrors', 'Shower Doors', 'Windows', 'Doors', 'Door Hardware',
            'Roofing', 'HVAC', 'Electrical', 'Plumbing', 'Masonry', 'Concrete',
            'Steel', 'Drywall', 'Painting', 'Flooring'
        ]

        for trade in trades:
            match = re.search(rf'{trade}\s+(\d+)', page_text)
            if match:
                market_intel['downloads_by_scope'].append({
                    'scope': trade,
                    'downloaded': int(match.group(1))
                })

        if market_intel['downloads_by_scope']:
            data['market_intel'] = market_intel

        # ===== TAB 5: Q&A =====
        qa_url = f'{BASE_URL}/leads/details/{lead_id}/project-qa'
        page.goto(qa_url, wait_until='domcontentloaded')
        wait_for_angular_content(page)
        time.sleep(PAGE_WAIT)

        qa_list = []
        try:
            qa_items = page.query_selector_all(".qa-item, mat-expansion-panel, .question-card")
            for item in qa_items[:10]:
                try:
                    q_elem = item.query_selector(".question, h3, h4, [class*='question']")
                    a_elem = item.query_selector(".answer, p, [class*='answer']")

                    if q_elem and a_elem:
                        qa_list.append({
                            'question': q_elem.inner_text().strip(),
                            'answer': a_elem.inner_text().strip()
                        })
                except:
                    continue
        except:
            pass

        if qa_list:
            data['qa'] = qa_list
            data['qa_count'] = len(qa_list)

        # ===== TAB 6: MATERIAL ESTIMATES =====
        estimates_url = f'{BASE_URL}/leads/details/{lead_id}/material-estimates'
        page.goto(estimates_url, wait_until='domcontentloaded')
        wait_for_angular_content(page)
        time.sleep(2)

        try:
            page_text = page.inner_text('body')
            if len(page_text) > 50:  # Has some content
                data['material_estimates'] = {
                    'raw_text': page_text[:500]
                }
        except:
            pass

        data['success'] = True

    except Exception as e:
        data['error'] = str(e)
        data['success'] = False

    return data


def scrape_worker(leads_batch: list, worker_id: int) -> list:
    """Worker function that scrapes a batch of leads with FULL data."""
    results = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(storage_state=str(SESSION_FILE))
        page = context.new_page()
        page.set_default_timeout(30000)

        for lead_id, name in leads_batch:
            print(f"  [W{worker_id}] {name[:50]}...")
            result = extract_full_project_data(page, lead_id, name)
            results.append(result)

            # Brief pause between leads
            time.sleep(1)

        context.close()
        browser.close()

    return results


def save_to_database(results: list):
    """Save all scraped data to database."""
    conn = sqlite3.connect('planhub.db')
    c = conn.cursor()

    for result in results:
        if result.get('success'):
            # Prepare JSON data
            project_info = {
                'bid_date': result.get('bid_date'),
                'location': result.get('location'),
                'project_value': result.get('project_value'),
                'project_size': result.get('project_size'),
                'description': result.get('description'),
                'start_date': result.get('start_date'),
                'end_date': result.get('end_date'),
                'tags': result.get('tags', [])
            }

            c.execute('''
                UPDATE leads SET
                    status = 'done',
                    bid_due_date = ?,
                    project_info_json = ?,
                    contractors_json = ?,
                    market_intel_json = ?,
                    qa_json = ?,
                    material_estimates_json = ?
                WHERE planhub_id = ?
            ''', (
                result.get('bid_date'),
                json.dumps(project_info),
                json.dumps(result.get('contractors', [])),
                json.dumps(result.get('market_intel', {})),
                json.dumps(result.get('qa', [])),
                json.dumps(result.get('material_estimates', {})),
                result['lead_id']
            ))

            # Save files to project_files table
            if result.get('files'):
                for file_data in result['files']:
                    # Get lead internal ID
                    c.execute('SELECT id FROM leads WHERE planhub_id = ?', (result['lead_id'],))
                    lead_row = c.fetchone()
                    if lead_row:
                        lead_internal_id = lead_row[0]
                        c.execute('''
                            INSERT INTO project_files
                            (lead_id, file_name, file_type, file_size, upload_date)
                            VALUES (?, ?, ?, ?, ?)
                        ''', (
                            lead_internal_id,
                            file_data.get('file_name'),
                            file_data.get('document_type'),
                            file_data.get('size'),
                            file_data.get('date_added')
                        ))

    conn.commit()
    conn.close()


def run_parallel_full_scrape():
    """Main function to run parallel scraping with FULL data extraction."""
    print("=== Parallel Full Scraper (Fast + Complete) ===\n")

    # Get queued leads from database
    conn = sqlite3.connect('planhub.db')
    c = conn.cursor()

    query = 'SELECT planhub_id, name FROM leads WHERE status = "queued"'
    if MAX_LEADS:
        query += f' LIMIT {MAX_LEADS}'

    c.execute(query)
    leads = c.fetchall()
    conn.close()

    print(f"Found {len(leads)} leads to scrape")
    print(f"Using {PARALLEL_WORKERS} parallel workers")
    print(f"Extracting: Project Info + Files + Contractors + Market Intel + Q&A + Materials")
    print(f"Estimated time: {len(leads) * 15 / PARALLEL_WORKERS / 60:.1f} minutes\n")

    if not leads:
        print("No leads to scrape!")
        return

    # Split leads into batches for workers
    batch_size = (len(leads) + PARALLEL_WORKERS - 1) // PARALLEL_WORKERS
    batches = [leads[i:i+batch_size] for i in range(0, len(leads), batch_size)]

    start_time = time.time()
    all_results = []

    # Run workers in parallel
    with ThreadPoolExecutor(max_workers=PARALLEL_WORKERS) as executor:
        futures = {
            executor.submit(scrape_worker, batch, i): i
            for i, batch in enumerate(batches)
        }

        for future in as_completed(futures):
            worker_id = futures[future]
            try:
                results = future.result()
                all_results.extend(results)
                print(f"✓ Worker {worker_id} complete: {len(results)} leads")
            except Exception as e:
                print(f"✗ Worker {worker_id} error: {e}")

    elapsed = time.time() - start_time

    # Save to database
    print("\nSaving to database...")
    save_to_database(all_results)

    # Save JSON backup
    output_path = 'data/parallel_scraped_data.json'
    with open(output_path, 'w') as f:
        json.dump(all_results, f, indent=2, default=str)

    # Summary
    success_count = sum(1 for r in all_results if r.get('success'))
    total_files = sum(r.get('files_count', 0) for r in all_results)
    total_contractors = sum(r.get('contractors_count', 0) for r in all_results)
    total_market_intel = sum(1 for r in all_results if r.get('market_intel'))
    total_qa = sum(r.get('qa_count', 0) for r in all_results)

    print(f"\n=== Complete ===")
    print(f"Time: {elapsed:.1f}s ({elapsed/60:.1f} min)")
    print(f"Leads scraped: {len(all_results)}")
    print(f"Successful: {success_count}")
    print(f"Speed: {len(all_results)/elapsed:.2f} leads/sec")
    print(f"\nData Captured:")
    print(f"  Files: {total_files}")
    print(f"  Contractors: {total_contractors}")
    print(f"  Market Intel: {total_market_intel} projects")
    print(f"  Q&A entries: {total_qa}")
    print(f"\nSaved to:")
    print(f"  Database: planhub.db")
    print(f"  JSON: {output_path}")

    # Sample output
    if all_results and success_count > 0:
        sample = next((r for r in all_results if r.get('success')), None)
        if sample:
            print(f"\nSample result:")
            print(f"  Name: {sample.get('name', 'N/A')[:60]}")
            print(f"  Bid: {sample.get('bid_date', 'N/A')}")
            print(f"  Location: {sample.get('location', 'N/A')[:60]}")
            print(f"  Value: {sample.get('project_value', 'N/A')}")
            print(f"  Files: {sample.get('files_count', 0)}")
            print(f"  GCs: {sample.get('contractors_count', 0)}")
            print(f"  Market Intel: {'Yes' if sample.get('market_intel') else 'No'}")


if __name__ == "__main__":
    # Parse simple CLI args
    args = sys.argv[1:]

    for i, arg in enumerate(args):
        if arg == '--limit' and i + 1 < len(args):
            MAX_LEADS = int(args[i + 1])
        elif arg == '--workers' and i + 1 < len(args):
            PARALLEL_WORKERS = int(args[i + 1])

    run_parallel_full_scrape()
