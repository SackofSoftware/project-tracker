"""
Estimate & Schedule Reader
Uses AI to analyze xlsx files and extract opening schedules
"""

import os
import re
import json
import sys
from pathlib import Path
from typing import Dict, List, Optional
import pandas as pd
import requests


def log(msg: str):
    """Print with flush for real-time output in Flask"""
    print(f"[EstimateReader] {msg}", flush=True)
    sys.stdout.flush()


class EstimateReader:
    """Uses AI to read and parse estimate/schedule spreadsheets"""

    API_URL = "https://openrouter.ai/api/v1/chat/completions"
    MODEL = "amazon/nova-lite-v1"  # Free tier

    # File patterns to look for
    SCHEDULE_PATTERNS = [
        '*estimate*.xlsx', '*schedule*.xlsx', '*counts*.xlsx',
        '*window*.xlsx', '*door*.xlsx', '*storefront*.xlsx',
        '*glass*.xlsx', '*opening*.xlsx'
    ]

    def __init__(self, project_folder: str, api_key: str = None):
        self.project_folder = Path(project_folder)
        self.api_key = api_key or os.getenv("OPENROUTER_API_KEY")
        self.spreadsheets = []
        self.openings = []
        log(f"Initialized for folder: {self.project_folder}")
        log(f"API key configured: {bool(self.api_key)}")

    def _call_ai(self, system_prompt: str, user_content: str) -> Optional[str]:
        """Make API call to OpenRouter"""
        if not self.api_key:
            log("ERROR: No API key available")
            return None

        log(f"Calling AI with {len(user_content)} chars of content...")
        try:
            response = requests.post(
                self.API_URL,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://project-tracker.local",
                },
                json={
                    "model": self.MODEL,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_content}
                    ],
                    "temperature": 0.1,
                    "max_tokens": 4000,
                },
                timeout=60
            )

            if response.status_code == 200:
                data = response.json()
                result = data['choices'][0]['message']['content']
                log(f"AI response received: {len(result)} chars")
                return result
            else:
                log(f"AI API error: {response.status_code} - {response.text[:200]}")
                return None

        except Exception as e:
            log(f"AI call failed: {e}")
            return None

    def find_spreadsheets(self) -> List[Path]:
        """Find all relevant spreadsheets in project folder"""
        log(f"Searching for spreadsheets in: {self.project_folder}")
        spreadsheets = []

        for pattern in self.SCHEDULE_PATTERNS:
            for f in self.project_folder.rglob(pattern):
                if f.name.startswith('~$'):
                    continue
                spreadsheets.append(f)
                log(f"  + Pattern match ({pattern}): {f.name}")

        # Also check root folder for any xlsx
        for f in self.project_folder.glob('*.xlsx'):
            if f.name.startswith('~$'):
                continue
            if f not in spreadsheets:
                spreadsheets.append(f)
                log(f"  + Root xlsx: {f.name}")

        self.spreadsheets = spreadsheets
        log(f"Total spreadsheets found: {len(spreadsheets)}")
        return spreadsheets

    def _spreadsheet_to_text(self, filepath: Path, max_rows: int = 50) -> str:
        """Convert spreadsheet to text for AI analysis"""
        log(f"Converting spreadsheet to text: {filepath.name}")
        try:
            xl = pd.ExcelFile(filepath)
            text_parts = [f"File: {filepath.name}"]
            log(f"  Sheets in file: {xl.sheet_names}")

            for sheet_name in xl.sheet_names:
                df = pd.read_excel(filepath, sheet_name=sheet_name, nrows=max_rows)
                if df.empty:
                    log(f"  Sheet '{sheet_name}' is empty, skipping")
                    continue

                text_parts.append(f"\n=== Sheet: {sheet_name} ===")
                log(f"  Sheet '{sheet_name}': {len(df)} rows, {len(df.columns)} cols")

                # Convert to CSV-like text (more compact)
                csv_text = df.to_csv(index=False)
                text_parts.append(csv_text)

            total_text = '\n'.join(text_parts)
            log(f"  Total text extracted: {len(total_text)} chars")
            return total_text

        except Exception as e:
            log(f"ERROR reading spreadsheet {filepath.name}: {e}")
            return f"Error reading {filepath.name}: {e}"

    def analyze_spreadsheet(self, filepath: Path) -> List[Dict]:
        """Use AI to analyze a spreadsheet and extract openings"""
        log(f"Analyzing spreadsheet: {filepath.name}")
        text_content = self._spreadsheet_to_text(filepath)

        if not text_content or len(text_content) < 50:
            log(f"  SKIP: Insufficient content ({len(text_content) if text_content else 0} chars)")
            return []

        system_prompt = """You are analyzing a construction estimate or schedule spreadsheet for a glazing contractor (windows, doors, storefronts).
Extract the openings/items and return ONLY valid JSON in this format:

{
    "file_type": "estimate" | "window_schedule" | "door_schedule" | "storefront_schedule" | "unknown",
    "openings": [
        {
            "mark": "window/door tag like A, 1-A, 101, etc",
            "qty": number (default 1 if not shown),
            "size": "width x height as shown (e.g. 3'-0\" x 7'-0\")",
            "type": "window" | "door" | "storefront" | "curtain_wall" | "glazing" | "frame",
            "description": "brief description from operation, material, comments columns",
            "manufacturer": "mfr name if shown",
            "unit_price": number or null,
            "total_price": number or null
        }
    ],
    "grand_total": number or null if there's an overall total
}

Rules:
- Extract ALL line items that represent individual openings
- Skip header rows, subtotal rows, and empty rows
- If qty column is empty or missing, use 1
- For size, keep the format as shown in spreadsheet (feet-inches, decimal, etc.)
- Type should be inferred from context (filename, column headers, item descriptions)
- Only include pricing if clearly shown as unit or total prices
- Return empty openings array if file doesn't contain opening schedule data"""

        result = self._call_ai(system_prompt, text_content[:8000])

        if not result:
            log(f"  No AI response for {filepath.name}")
            return []

        try:
            # Clean up JSON
            result = result.strip()
            if result.startswith("```"):
                result = re.sub(r'^```\w*\n?', '', result)
                result = re.sub(r'\n?```$', '', result)

            data = json.loads(result)

            openings = data.get('openings', [])
            file_type = data.get('file_type', 'unknown')

            # Add source info
            for opening in openings:
                opening['source_file'] = filepath.name
                opening['file_type'] = file_type

            log(f"  SUCCESS: Found {len(openings)} openings (type: {file_type})")
            if openings:
                types = {}
                for o in openings:
                    t = o.get('type', 'unknown')
                    types[t] = types.get(t, 0) + 1
                log(f"    Types breakdown: {types}")

            return openings

        except json.JSONDecodeError as e:
            log(f"JSON parse error for {filepath.name}: {e}")
            log(f"Raw result (first 500): {result[:500]}")
            return []

    def read_all(self, use_ai: bool = True) -> Dict:
        """Read all spreadsheets and return consolidated data with deduplication"""
        log("=== Starting read_all ===")
        log(f"use_ai={use_ai}, api_key={'set' if self.api_key else 'NOT SET'}")
        self.find_spreadsheets()

        raw_openings = []
        files_read = []
        errors = []

        for i, spreadsheet in enumerate(self.spreadsheets, 1):
            log(f"Processing spreadsheet {i}/{len(self.spreadsheets)}: {spreadsheet.name}")
            try:
                if use_ai and self.api_key:
                    openings = self.analyze_spreadsheet(spreadsheet)
                else:
                    log(f"  Using fallback (no AI)")
                    openings = self._fallback_read(spreadsheet)

                if openings:
                    raw_openings.extend(openings)
                    files_read.append(spreadsheet.name)
                    log(f"  Added {len(openings)} openings to results")
                else:
                    log(f"  No openings found")
            except Exception as e:
                errors.append(f"{spreadsheet.name}: {e}")
                log(f"  EXCEPTION: {e}")

        # Deduplicate openings - same mark+type = same opening
        # Keep the entry with most complete data (most non-null fields)
        log(f"Deduplicating {len(raw_openings)} raw openings...")
        deduplicated = self._deduplicate_openings(raw_openings)
        self.openings = deduplicated
        log(f"After dedup: {len(deduplicated)} unique openings")

        # Calculate totals by type
        totals = {}
        for opening in deduplicated:
            otype = opening.get('type', 'unknown')
            if otype not in totals:
                totals[otype] = {'count': 0, 'items': 0, 'total_price': 0}
            qty = opening.get('qty', 1) or 1
            totals[otype]['count'] += qty
            totals[otype]['items'] += 1
            if opening.get('total_price'):
                totals[otype]['total_price'] += opening['total_price']

        # Group by type
        by_type = {}
        for opening in deduplicated:
            otype = opening.get('type', 'unknown')
            if otype not in by_type:
                by_type[otype] = []
            by_type[otype].append(opening)

        total_count = sum(o.get('qty', 1) or 1 for o in deduplicated)
        unique_marks = len(set(o.get('mark', '') for o in deduplicated))

        log("=== Estimate Reading Complete ===")
        log(f"  Files read: {len(files_read)}")
        log(f"  Total openings: {total_count}")
        log(f"  Unique marks: {unique_marks}")
        log(f"  Duplicates removed: {len(raw_openings) - len(deduplicated)}")
        log(f"  Errors: {len(errors)}")
        log(f"  Totals by type: {totals}")
        if errors:
            for err in errors:
                log(f"    - {err}")

        return {
            'openings': deduplicated,
            'by_type': by_type,
            'totals': totals,
            'files_read': files_read,
            'errors': errors,
            'total_count': total_count,
            'unique_marks': unique_marks,
            'raw_count': len(raw_openings),
            'duplicates_removed': len(raw_openings) - len(deduplicated)
        }

    def _deduplicate_openings(self, openings: List[Dict]) -> List[Dict]:
        """
        Deduplicate openings based on mark + type combination.
        When duplicates found, keep the one with most complete data.
        """
        # Group by (mark, type)
        grouped = {}
        for opening in openings:
            mark = str(opening.get('mark', '')).strip().upper()
            otype = opening.get('type', 'unknown')
            key = (mark, otype)

            if key not in grouped:
                grouped[key] = []
            grouped[key].append(opening)

        # For each group, pick the best (most complete) entry
        deduplicated = []
        for key, group in grouped.items():
            if len(group) == 1:
                deduplicated.append(group[0])
            else:
                # Score each entry by completeness
                best = max(group, key=lambda o: self._completeness_score(o))
                # Merge data from other entries if they have data best doesn't
                merged = self._merge_opening_data(best, group)
                merged['sources'] = list(set(o.get('source_file', '') for o in group))
                deduplicated.append(merged)

        return deduplicated

    def _completeness_score(self, opening: Dict) -> int:
        """Score an opening by how complete its data is"""
        score = 0
        if opening.get('size'):
            score += 3
        if opening.get('description'):
            score += 2
        if opening.get('qty') and opening.get('qty') != 1:
            score += 2
        if opening.get('manufacturer'):
            score += 1
        if opening.get('unit_price'):
            score += 1
        if opening.get('total_price'):
            score += 1
        return score

    def _merge_opening_data(self, best: Dict, group: List[Dict]) -> Dict:
        """Merge data from multiple entries, preferring non-null values"""
        merged = dict(best)
        fields = ['size', 'description', 'manufacturer', 'qty', 'unit_price', 'total_price']

        for opening in group:
            for field in fields:
                if not merged.get(field) and opening.get(field):
                    merged[field] = opening[field]

        return merged

    def _fallback_read(self, filepath: Path) -> List[Dict]:
        """Fallback non-AI reader for when API is unavailable"""
        openings = []
        try:
            xl = pd.ExcelFile(filepath)
            for sheet_name in xl.sheet_names:
                df = pd.read_excel(filepath, sheet_name=sheet_name, nrows=100)
                if df.empty:
                    continue

                # Try to find mark-like column in first few columns
                for col in df.columns[:3]:
                    col_lower = str(col).lower()
                    if any(m in col_lower for m in ['mark', 'tag', 'type', 'door', 'window', '#']):
                        for _, row in df.iterrows():
                            mark = row[col]
                            if pd.notna(mark) and str(mark).strip():
                                openings.append({
                                    'mark': str(mark).strip(),
                                    'qty': 1,
                                    'size': None,
                                    'type': 'opening',
                                    'description': None,
                                    'source_file': filepath.name
                                })
                        break

        except Exception as e:
            print(f"Fallback read error for {filepath}: {e}")

        return openings


def read_project_estimate(project_folder: str, api_key: str = None) -> Dict:
    """Convenience function to read estimate data from a project folder"""
    reader = EstimateReader(project_folder, api_key)
    return reader.read_all()


if __name__ == "__main__":
    import sys
    from dotenv import load_dotenv
    load_dotenv()

    # Test with a project - get folder from args or env
    if len(sys.argv) > 1:
        test_folder = sys.argv[1]
    else:
        bidding_folder = os.getenv("BIDDING_FOLDER", "")
        if not bidding_folder:
            print("Error: Provide folder path as argument or set BIDDING_FOLDER in .env")
            sys.exit(1)
        # Use first project in bidding folder
        test_folder = str(next(Path(bidding_folder).iterdir()))

    result = read_project_estimate(test_folder)

    print(f"\nFiles read: {result['files_read']}")
    print(f"Total openings: {result['total_count']}")
    print(f"Unique marks: {result['unique_marks']}")
    print(f"\nTotals by type: {json.dumps(result['totals'], indent=2)}")

    print(f"\nSample openings:")
    for opening in result['openings'][:10]:
        print(f"  {opening.get('mark')}: {opening.get('qty', 1)}x {opening.get('size') or 'N/A'} - {opening.get('type')} - {opening.get('description', '')[:50] if opening.get('description') else ''}")
