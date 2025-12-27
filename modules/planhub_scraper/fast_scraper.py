#!/usr/bin/env python3
"""
Fast parallel scraper - scrapes multiple leads simultaneously.
Uses 4 parallel browser contexts for ~4x speedup.

Usage:
    python fast_scraper.py          # Scrape all queued leads
    python fast_scraper.py --limit 10   # Scrape first 10 leads
    python fast_scraper.py --workers 2  # Use 2 workers instead of 4
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
PAGE_WAIT = 4  # seconds
MAX_LEADS = None  # None = all


def extract_project_data(page, lead_id: str) -> dict:
    """Extract all key data from project-info page only (fastest)."""
    data = {
        'lead_id': lead_id,
        'scraped_at': time.strftime('%Y-%m-%d %H:%M:%S')
    }

    try:
        url = f'{BASE_URL}/leads/details/{lead_id}/project-info'
        page.goto(url, wait_until='domcontentloaded')
        time.sleep(PAGE_WAIT)

        page_text = page.inner_text('body')

        # Bid date
        match = re.search(r'Bid Due Date\s*(\d{1,2}/\d{1,2}/\d{4})\s*at\s*(\d{1,2}:\d{2}\s*[AP]M)', page_text)
        if match:
            data['bid_date'] = f"{match.group(1)} {match.group(2)}"

        # Location - find city/state/zip first, then look backwards for street
        lines = page_text.split('\n')
        states = r'(MA|CT|NH|RI|VT|ME|NY|NJ|PA|FL|CA|TX|GA|OH|MI|IL|WA|OR|AZ|CO|NC|VA|MD|SC|TN|AL|KY|LA|MO|IN|WI|MN)'

        # Skip these false positives
        skip_words = ['WORKSPACE', 'CHECKLIST', 'INFO@', 'PLANHUB', 'PROJECT INFO',
                      'BIDDING', 'MARKET INTEL', 'FILES', 'CONTRACTORS', 'SUBMIT BID']

        # Find city, state, zip line first
        for i, line in enumerate(lines):
            line = line.strip()

            # Skip navigation and false positives
            if len(line) < 8 or len(line) > 60:
                continue
            if any(x in line.upper() for x in skip_words):
                continue

            # Look for city, state ZIP pattern (must have zip code)
            city_match = re.search(rf'^\s*([A-Za-z][A-Za-z\s]+),?\s*{states}\s+(\d{{5}})\s*$', line)
            if city_match:
                city_line = line
                # Look backwards for street address (1-3 lines above)
                street_parts = []
                for j in range(i-1, max(i-4, -1), -1):
                    prev_line = lines[j].strip()
                    if len(prev_line) < 3 or len(prev_line) > 80:
                        break
                    if any(x in prev_line.upper() for x in skip_words):
                        break
                    # Check if it looks like address content (has numbers or common street words)
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
        for tag in ['GC Awarded', 'Sub Bidding', 'Commercial', 'Retail', 'Renovation', 'New Construction']:
            if tag in page_text:
                tags.append(tag)
        if tags:
            data['tags'] = tags

        # Quick GC check (same page might show primary GC)
        gc_url = f'{BASE_URL}/leads/details/{lead_id}/general-contractors'
        page.goto(gc_url, wait_until='domcontentloaded')
        time.sleep(2)

        phones = page.query_selector_all("a[href^='tel:']")
        emails = page.query_selector_all("a[href^='mailto:']")

        contractors = []
        seen = set()
        for i, phone in enumerate(phones[:5]):
            phone_text = phone.inner_text().strip()
            if phone_text and phone_text not in seen:
                seen.add(phone_text)
                gc = {'phone': phone_text}
                if i < len(emails):
                    gc['email'] = emails[i].inner_text().strip()
                contractors.append(gc)

        if contractors:
            data['contractors'] = contractors

        data['success'] = True

    except Exception as e:
        data['error'] = str(e)
        data['success'] = False

    return data


def scrape_worker(leads_batch: list, worker_id: int) -> list:
    """Worker function that scrapes a batch of leads."""
    results = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(storage_state=str(SESSION_FILE))
        page = context.new_page()

        for lead_id, name in leads_batch:
            print(f"  [W{worker_id}] {name[:40]}...")
            result = extract_project_data(page, lead_id)
            result['name'] = name
            results.append(result)

        context.close()
        browser.close()

    return results


def run_fast_scrape():
    """Main function to run parallel scraping."""
    print("=== Fast Parallel Scraper ===\n")

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
    print(f"Estimated time: {len(leads) * 6 / PARALLEL_WORKERS / 60:.1f} minutes\n")

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
                print(f"  Worker {worker_id} complete: {len(results)} leads")
            except Exception as e:
                print(f"  Worker {worker_id} error: {e}")

    elapsed = time.time() - start_time

    # Save results
    output_path = 'data/scraped_data.json'
    with open(output_path, 'w') as f:
        json.dump(all_results, f, indent=2, default=str)

    # Update database
    conn = sqlite3.connect('planhub.db')
    c = conn.cursor()

    success_count = 0
    for result in all_results:
        if result.get('success'):
            c.execute('''
                UPDATE leads SET
                    status = 'done',
                    bid_due_date = ?,
                    project_info_json = ?
                WHERE planhub_id = ?
            ''', (
                result.get('bid_date'),
                json.dumps(result),
                result['lead_id']
            ))
            success_count += 1

    conn.commit()
    conn.close()

    # Summary
    print(f"\n=== Complete ===")
    print(f"Time: {elapsed:.1f}s ({elapsed/60:.1f} min)")
    print(f"Leads scraped: {len(all_results)}")
    print(f"Successful: {success_count}")
    print(f"Speed: {len(all_results)/elapsed:.1f} leads/sec")
    print(f"Saved to: {output_path}")

    # Sample output
    if all_results:
        sample = next((r for r in all_results if r.get('bid_date')), all_results[0])
        print(f"\nSample result:")
        print(f"  Name: {sample.get('name', 'N/A')[:50]}")
        print(f"  Bid: {sample.get('bid_date', 'N/A')}")
        print(f"  Value: {sample.get('project_value', 'N/A')}")
        print(f"  GCs: {len(sample.get('contractors', []))}")


if __name__ == "__main__":
    # Parse simple CLI args
    args = sys.argv[1:]

    for i, arg in enumerate(args):
        if arg == '--limit' and i + 1 < len(args):
            MAX_LEADS = int(args[i + 1])
        elif arg == '--workers' and i + 1 < len(args):
            PARALLEL_WORKERS = int(args[i + 1])

    run_fast_scrape()
