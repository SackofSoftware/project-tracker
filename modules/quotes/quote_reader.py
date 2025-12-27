"""
Quote Reader
Uses AI to analyze vendor quote PDFs and extract pricing data
"""

import os
import re
import json
import sys
from pathlib import Path
from typing import Dict, List, Optional
import requests
import PyPDF2


def log(msg: str):
    """Print with flush for real-time output in Flask"""
    print(f"[QuoteReader] {msg}", flush=True)
    sys.stdout.flush()


class QuoteReader:
    """Uses AI to read and parse vendor quote PDFs"""

    API_URL = "https://openrouter.ai/api/v1/chat/completions"
    MODEL = "amazon/nova-lite-v1"  # Free tier

    # File patterns to look for vendor quotes
    QUOTE_PATTERNS = [
        '*quote*.pdf', '*pricing*.pdf', '*proposal*.pdf',
        '*estimate*.pdf', '*bid*.pdf', '*supply*.pdf',
        '*rebid*.pdf'
    ]

    # Known vendor patterns for better detection (glazing industry)
    VENDOR_PATTERNS = [
        # Aluminum/Storefront manufacturers
        'kawneer', 'oldcastle', 'tubelite', 'ykk', 'hope',
        'efco', 'arcadia', 'traco', 'vistawall', 'manko',
        # Door/Hardware manufacturers
        'doormerica', 'graham', 'allegion', 'assa', 'stanley',
        'von duprin', 'schlage', 'corbin', 'sargent',
        # Glass manufacturers
        'crl', 'viracon', 'ppg', 'guardian', 'vitro', 'pilkington',
        # Window manufacturers (wood, fiberglass, vinyl)
        'pella', 'marvin', 'andersen', 'milgard', 'weathershield',
        'alpen', 'zenith', 'thomas', 'twi', 'sierra pacific',
        'kolbe', 'loewen', 'eagle', 'windsor', 'integrity',
        # uPVC/Vinyl specialists
        'upvc', '4500', 'vinyl', 'simonton', 'ply gem',
        # European/High-performance
        'schuco', 'reynaers', 'wicona', 'schueco'
    ]

    def __init__(self, project_folder: str, api_key: str = None):
        self.project_folder = Path(project_folder)
        self.api_key = api_key or os.getenv("OPENROUTER_API_KEY")
        self.quote_pdfs = []
        self.quotes = []
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

    def find_quote_pdfs(self) -> List[Path]:
        """Find all likely quote PDFs in project folder"""
        log(f"Searching for quote PDFs in: {self.project_folder}")
        quote_files = []

        # First, check Quotes subfolder if it exists
        quotes_folder = self.project_folder / "Quotes"
        if quotes_folder.exists() and quotes_folder.is_dir():
            log(f"Found Quotes subfolder: {quotes_folder}")
            for f in quotes_folder.glob("*.pdf"):
                if not f.name.startswith('.'):
                    quote_files.append(f)
                    log(f"  + Found in Quotes/: {f.name}")

        # Also check for pattern-matched files in root and subfolders
        for pattern in self.QUOTE_PATTERNS:
            for f in self.project_folder.rglob(pattern):
                if f.name.startswith('.') or f.name.startswith('~$'):
                    continue
                if f not in quote_files:
                    quote_files.append(f)
                    log(f"  + Pattern match ({pattern}): {f.name}")

        # Check for vendor names in filenames
        for f in self.project_folder.rglob("*.pdf"):
            if f.name.startswith('.') or f in quote_files:
                continue

            filename_lower = f.name.lower()
            if any(vendor in filename_lower for vendor in self.VENDOR_PATTERNS):
                quote_files.append(f)
                log(f"  + Vendor match: {f.name}")

        self.quote_pdfs = quote_files
        log(f"Total quote PDFs found: {len(quote_files)}")
        return quote_files

    def _pdf_to_text(self, filepath: Path, max_pages: int = 10) -> str:
        """Extract text from PDF for AI analysis"""
        log(f"Extracting text from PDF: {filepath.name}")
        try:
            text_parts = []
            with open(filepath, 'rb') as f:
                reader = PyPDF2.PdfReader(f)
                num_pages = min(len(reader.pages), max_pages)
                log(f"  PDF has {len(reader.pages)} pages, reading {num_pages}")

                for page_num in range(num_pages):
                    page = reader.pages[page_num]
                    text = page.extract_text()
                    if text:
                        text_parts.append(text)

            total_text = '\n'.join(text_parts)
            log(f"  Extracted {len(total_text)} chars from {len(text_parts)} pages")
            return total_text

        except Exception as e:
            log(f"ERROR reading PDF {filepath.name}: {e}")
            return ""

    def _parse_alpen_quote(self, text_content: str, filepath: Path) -> Optional[Dict]:
        """Parse Alpen/Zenith quote using regex (more reliable than AI for this format)"""
        log(f"  Using Alpen-specific parser")

        line_items = []

        # Find all page blocks with window configs
        # Pattern: "{qty} {line#}   Line" followed by "Room/Comment:\n{Mark}{Size}"

        # Split by pages (each page has "Line         |  Qty  |")
        pages = re.split(r'(\d+)\s+(\d+)\s+Line\s+\|\s+Qty\s+\|', text_content)

        # Process in groups of 3: prefix, qty, line_num, content
        i = 1
        while i < len(pages) - 2:
            qty_str = pages[i]
            line_num = pages[i+1]
            content = pages[i+2] if i+2 < len(pages) else ""

            try:
                qty = int(qty_str)
            except:
                qty = 1

            # Extract mark and size from "Room/Comment:\n{Mark}{Size}"
            room_match = re.search(r'Room/Comment:\s*\n?([A-Z])\s*(\d+)["\']?\s*[xX]\s*(\d+)', content)
            if room_match:
                mark = room_match.group(1)
                width = int(room_match.group(2))
                height = int(room_match.group(3))

                # Get product description
                prod_match = re.search(r'PRODUCT\s*\n(.+?)(?:DIMENSIONS|$)', content, re.DOTALL)
                description = prod_match.group(1).strip()[:100] if prod_match else ""
                description = ' '.join(description.split())  # Normalize whitespace

                line_items.append({
                    'mark': mark,
                    'qty': qty,
                    'width': width,
                    'height': height,
                    'description': description,
                    'product_type': 'window',
                    'operation': 'awning' if 'awning' in description.lower() else 'fixed',
                    'frame_material': 'fiberglass',
                    'glazing': 'triple',
                    'unit_price': None,
                    'total_price': None
                })
                log(f"    Found: Mark {mark}, Qty {qty}, Size {width}x{height}")

            i += 3

        if not line_items:
            log(f"  Alpen parser found no items, falling back to AI")
            return None

        # Extract totals from page 1
        total_match = re.search(r'TOTAL\s+\$\s*([\d,]+\.?\d*)', text_content)
        grand_total = float(total_match.group(1).replace(',', '')) if total_match else None

        units_match = re.search(r'Units\s+(\d+)\s+\$\s*([\d,]+\.?\d*)', text_content)
        total_units = int(units_match.group(1)) if units_match else sum(item['qty'] for item in line_items)

        # Calculate unit prices if we have total
        if grand_total and total_units > 0:
            avg_unit_price = grand_total / total_units
            for item in line_items:
                item['unit_price'] = round(avg_unit_price, 2)
                item['total_price'] = round(avg_unit_price * item['qty'], 2)

        log(f"  Alpen parser SUCCESS: {len(line_items)} items, total ${grand_total:,.2f}")

        return {
            'vendor_name': 'ALPEN WINDOWS',
            'vendor_type': 'window_manufacturer',
            'quote_number': None,
            'quote_date': None,
            'line_items': line_items,
            'total_units': total_units,
            'grand_total': grand_total,
            'source_file': filepath.name,
            'file_path': str(filepath)
        }

    def _parse_twi_quote(self, text_content: str, filepath: Path) -> Optional[Dict]:
        """Parse Thomas Windows/TWI quote using regex"""
        log(f"  Using TWI-specific parser")

        line_items = []

        # TWI format has tables like:
        # Type  QTY  Type  QTY
        # G 6  N 22
        # H 13  O1 2

        # Find all type-qty pairs in SCOPE OF WORK section
        # Pattern: single letter or letter+number followed by space and number
        scope_match = re.search(r'SCOPE OF WORK.*?(?:TOTAL PRICE|Qualifications)', text_content, re.DOTALL | re.IGNORECASE)
        if scope_match:
            scope_text = scope_match.group(0)
            # Find all Type QTY pairs
            pairs = re.findall(r'\b([A-Z]\d?)\s+(\d+)\b', scope_text)
            for mark, qty in pairs:
                if mark not in ['QTY', 'SF']:  # Skip header words
                    line_items.append({
                        'mark': mark,
                        'qty': int(qty),
                        'width': None,
                        'height': None,
                        'description': 'uPVC Window',
                        'product_type': 'window',
                        'operation': None,
                        'frame_material': 'upvc',
                        'glazing': 'double',
                        'unit_price': None,
                        'total_price': None
                    })
                    log(f"    Found: Mark {mark}, Qty {qty}")

        # Also check for Option sections (additional scope)
        option_matches = re.finditer(r'Option.*?Window Scope.*?(?:ADD|Please)', text_content, re.DOTALL | re.IGNORECASE)
        for opt_match in option_matches:
            opt_text = opt_match.group(0)
            pairs = re.findall(r'\b([A-Z]\d?)\s+(\d+)\b', opt_text)
            for mark, qty in pairs:
                if mark not in ['QTY', 'SF']:
                    # Check if already exists
                    existing = [i for i in line_items if i['mark'] == mark]
                    if not existing:
                        line_items.append({
                            'mark': mark,
                            'qty': int(qty),
                            'width': None,
                            'height': None,
                            'description': 'uPVC Window (Option)',
                            'product_type': 'window',
                            'operation': None,
                            'frame_material': 'upvc',
                            'glazing': 'double',
                            'unit_price': None,
                            'total_price': None
                        })
                        log(f"    Found (Option): Mark {mark}, Qty {qty}")

        if not line_items:
            log(f"  TWI parser found no items, falling back to AI")
            return None

        # Extract total price
        total_match = re.search(r'TOTAL PRICE:\s*\$\s*([\d,]+\.?\d*)', text_content)
        grand_total = float(total_match.group(1).replace(',', '')) if total_match else None

        # Calculate unit prices
        total_units = sum(item['qty'] for item in line_items)
        if grand_total and total_units > 0:
            avg_unit_price = grand_total / total_units
            for item in line_items:
                item['unit_price'] = round(avg_unit_price, 2)
                item['total_price'] = round(avg_unit_price * item['qty'], 2)

        # Extract square footage if available
        sqft_match = re.search(r'Approx\.?\s*([\d,]+)\s*SF', text_content)
        total_sqft = int(sqft_match.group(1).replace(',', '')) if sqft_match else None

        log(f"  TWI parser SUCCESS: {len(line_items)} items, total ${grand_total:,.2f}" if grand_total else f"  TWI parser SUCCESS: {len(line_items)} items")

        return {
            'vendor_name': 'Thomas Windows, Inc.',
            'vendor_type': 'window_manufacturer',
            'quote_number': re.search(r'Quote#\s*:\s*(\d+)', text_content).group(1) if re.search(r'Quote#\s*:\s*(\d+)', text_content) else None,
            'quote_date': None,
            'line_items': line_items,
            'total_units': total_units,
            'total_sqft': total_sqft,
            'grand_total': grand_total,
            'source_file': filepath.name,
            'file_path': str(filepath)
        }

    def _parse_pella_quote(self, text_content: str, filepath: Path) -> Optional[Dict]:
        """Parse Pella quote using regex"""
        log(f"  Using Pella-specific parser")

        line_items = []

        # Pella format: Each item starts with qty+mark pattern like "2A" or "1D1"
        # Look for pattern: {qty}{mark}\n{rough opening}...Frame Size: {W} X {H}...\n${unit} ${extended}

        # More flexible pattern - find all qty+mark combinations first
        # Then extract frame size and prices nearby
        qty_mark_pattern = re.compile(r'^(\d+)([A-Z]\d?)\s*$', re.MULTILINE)

        for match in qty_mark_pattern.finditer(text_content):
            qty_str = match.group(1)
            mark = match.group(2)
            start_pos = match.end()

            # Look for Frame Size within next 2000 chars
            section = text_content[start_pos:start_pos + 2000]

            # Extract Frame Size
            frame_match = re.search(r'Frame Size:\s*(\d+)\s*(?:1/2)?\s*X\s*(\d+)', section)
            if not frame_match:
                continue

            width = int(frame_match.group(1))
            height = int(frame_match.group(2))

            # Extract prices - pattern: $unit $extended at start of price section
            price_match = re.search(r'\$([\d,]+\.\d+)\s+\$([\d,]+\.\d+)', section)
            if not price_match:
                continue

            try:
                qty = int(qty_str)
                unit_price = float(price_match.group(1).replace(',', ''))
                total_price = float(price_match.group(2).replace(',', ''))

                # Determine operation type from description
                operation = 'fixed'
                if 'Double Hung' in section:
                    operation = 'double_hung'
                elif 'Casement' in section:
                    operation = 'casement'
                elif 'Direct Set' in section or 'Fixed Frame' in section:
                    operation = 'fixed'

                line_items.append({
                    'mark': mark,
                    'qty': qty,
                    'width': width,
                    'height': height,
                    'description': f'Pella Reserve {operation.replace("_", " ").title()}',
                    'product_type': 'window',
                    'operation': operation,
                    'frame_material': 'wood_clad',
                    'glazing': 'double',
                    'unit_price': unit_price,
                    'total_price': total_price
                })
                log(f"    Found: Mark {mark}, Qty {qty}, Size {width}x{height}, ${unit_price:,.2f}/ea")

            except (ValueError, IndexError) as e:
                log(f"    Error parsing: {e}")
                continue

        if not line_items:
            log(f"  Pella parser found no items, falling back to AI")
            return None

        # Calculate totals
        total_units = sum(item['qty'] for item in line_items)
        grand_total = sum(item['total_price'] for item in line_items)

        # Extract quote number
        quote_num_match = re.search(r'Quote Number:\s*(\d+)', text_content)
        quote_number = quote_num_match.group(1) if quote_num_match else None

        log(f"  Pella parser SUCCESS: {len(line_items)} items, total ${grand_total:,.2f}")

        return {
            'vendor_name': 'Pella Window and Door',
            'vendor_type': 'window_manufacturer',
            'quote_number': quote_number,
            'quote_date': None,
            'line_items': line_items,
            'total_units': total_units,
            'grand_total': grand_total,
            'source_file': filepath.name,
            'file_path': str(filepath)
        }

    def analyze_quote_pdf(self, filepath: Path) -> Optional[Dict]:
        """Use AI to analyze a quote PDF and extract pricing data"""
        log(f"Analyzing quote PDF: {filepath.name}")
        text_content = self._pdf_to_text(filepath)

        if not text_content or len(text_content) < 50:
            log(f"  SKIP: Insufficient text content ({len(text_content) if text_content else 0} chars)")
            return None

        # Check for vendor-specific formats and use dedicated parsers

        # Alpen/Zenith - complex multi-page format with Room/Comment markers
        is_alpen = ('ALPEN' in text_content.upper() or 'ZENITH' in text_content.upper()) and 'Room/Comment:' in text_content
        if is_alpen:
            result = self._parse_alpen_quote(text_content, filepath)
            if result:
                return result
            log(f"  Alpen parser failed, falling back to AI")

        # Thomas Windows / TWI - simple type-qty table format
        is_twi = ('THOMAS WINDOWS' in text_content.upper() or 'TWI' in text_content.upper()) and 'SCOPE OF WORK' in text_content.upper()
        if is_twi:
            result = self._parse_twi_quote(text_content, filepath)
            if result:
                return result
            log(f"  TWI parser failed, falling back to AI")

        # Pella - detailed line item format with Frame Size
        is_pella = 'PELLA' in text_content.upper() and 'Frame Size:' in text_content
        if is_pella:
            result = self._parse_pella_quote(text_content, filepath)
            if result:
                return result
            log(f"  Pella parser failed, falling back to AI")

        system_prompt = """You are analyzing a vendor quote/pricing document for a glazing construction project (windows, doors, storefronts).
Extract the quote information and return ONLY valid JSON in this format:

{
    "vendor_name": "Company name providing the quote",
    "vendor_type": "window_manufacturer|door_manufacturer|glass_supplier|hardware_supplier|storefront",
    "quote_number": "Quote/proposal number if shown",
    "quote_date": "Date in YYYY-MM-DD format if possible, or as shown",
    "contact_person": "Sales rep name if shown",
    "contact_email": "Email if shown",
    "contact_phone": "Phone if shown",
    "line_items": [
        {
            "mark": "item reference/mark (like A, 1-A, W101, G, H, etc.)",
            "description": "brief description of the item",
            "product_type": "window|door|storefront|curtain_wall|skylight|hardware|glass",
            "operation": "fixed|casement|awning|double_hung|sliding|pivot|null",
            "width": number in inches or null,
            "height": number in inches or null,
            "u_factor": number or null,
            "shgc": number or null,
            "glazing": "single|double|triple|quad or description",
            "frame_material": "aluminum|wood|fiberglass|vinyl|upvc|clad|null",
            "qty": number (default 1 if not shown),
            "unit_price": number or null,
            "total_price": number or null
        }
    ],
    "total_units": number of total windows/doors quoted,
    "total_sqft": total square footage if mentioned,
    "subtotal": number or null,
    "tax": number or null,
    "shipping": number or null,
    "grand_total": number or null,
    "terms": "payment terms if shown",
    "lead_time": "delivery/lead time if shown",
    "inclusions": ["list of what's included"],
    "exclusions": ["list of what's excluded"],
    "notes": "any special notes or conditions"
}

Vendor-specific guidance:

ALPEN/ZENITH QUOTES (CRITICAL - read VERY carefully):
- Each page shows ONE window configuration
- Pattern to find: "{QTY} {LINE#}   Line         |  Qty  |..." where FIRST number is QUANTITY
- Examples from actual quote:
  * "6 1   Line" = Qty 6, Line 1
  * "13 2   Line" = Qty 13, Line 2
  * "1 3   Line" = Qty 1, Line 3
- The MARK is found at "Room/Comment:" followed immediately by a letter (G, H, J, K, L, M, N, etc.)
- The SIZE is on same line as mark, like "H39" X 103"" means mark=H, size=39x103
- Each page is ONE complete unit - extract: mark from Room/Comment, qty (FIRST number), size
- CRITICAL: The first number before "Line" is the QUANTITY - do NOT confuse with line number!
- Expected output example: {"mark": "H", "qty": 13, "width": 39, "height": 103}

THOMAS WINDOWS/TWI:
- Simple format with Type codes (A, B, C, G, H etc.) and quantities
- Usually lump-sum pricing without per-unit breakdown
- Calculate unit_price = grand_total / sum(quantities) if no unit prices shown

PELLA:
- Has detailed line items with explicit unit pricing
- Usually includes performance specs (U-factor, SHGC)
- Marks often include room identifiers (2A, 2B, 4C, etc.)

Rules:
- Extract ALL line items with pricing - even if just type codes and counts
- If no mark/tag shown, use description or sequential numbering (1, 2, 3...)
- Prices should be numeric (no $, commas)
- If qty not shown, use 1
- Include subtotal and tax breakdown if shown
- Extract terms (NET 30, etc.) and lead time (6-8 weeks, etc.)
- Return null for any fields not found in the document
"""

        result = self._call_ai(system_prompt, text_content[:12000])

        if not result:
            log(f"  No AI response for {filepath.name}")
            return None

        try:
            # Clean up JSON
            result = result.strip()
            if result.startswith("```"):
                result = re.sub(r'^```\w*\n?', '', result)
                result = re.sub(r'\n?```$', '', result)

            # Try to parse, with fallback to repair
            data = self._parse_json_with_repair(result)

            if not data:
                log(f"  FAILED: Could not parse JSON for {filepath.name}")
                return None

            # Add metadata
            data['source_file'] = filepath.name
            data['file_path'] = str(filepath)
            data['parsed_date'] = None  # Can add timestamp if needed

            # Log extracted data summary
            vendor = data.get('vendor_name', 'Unknown')
            total = data.get('grand_total', 0) or 0
            items = len(data.get('line_items', []))
            log(f"  SUCCESS: {vendor} - ${total:,.2f} ({items} line items)")

            return data

        except Exception as e:
            log(f"Unexpected error parsing {filepath.name}: {e}")
            return None

    def _parse_json_with_repair(self, text: str) -> Optional[Dict]:
        """Try to parse JSON, with repair attempts for common issues"""
        # First, try direct parse
        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            log(f"  Initial JSON parse failed: {e}")

        # Attempt repairs
        repaired = text

        # Fix trailing commas before } or ]
        repaired = re.sub(r',\s*([}\]])', r'\1', repaired)

        # Fix missing commas between objects in arrays
        repaired = re.sub(r'}\s*{', '},{', repaired)

        # Fix arithmetic expressions in values (e.g., "unit_price": 83971.84 / 65)
        def eval_arithmetic(match):
            expr = match.group(1)
            try:
                # Only allow basic arithmetic
                result = eval(expr, {"__builtins__": {}}, {})
                return str(round(result, 2))
            except:
                return "null"
        repaired = re.sub(r':\s*(\d+\.?\d*\s*[/\*\+\-]\s*\d+\.?\d*)', lambda m: ': ' + eval_arithmetic(m), repaired)

        # Try again
        try:
            return json.loads(repaired)
        except json.JSONDecodeError as e:
            log(f"  Repair attempt 1 failed: {e}")

        # Try to extract just the JSON object (in case there's extra text)
        match = re.search(r'\{[\s\S]*\}', text)
        if match:
            try:
                extracted = match.group(0)
                extracted = re.sub(r',\s*([}\]])', r'\1', extracted)
                extracted = re.sub(r':\s*(\d+\.?\d*\s*[/\*\+\-]\s*\d+\.?\d*)', lambda m: ': ' + eval_arithmetic(m), extracted)
                return json.loads(extracted)
            except json.JSONDecodeError as e:
                log(f"  Repair attempt 2 (extraction) failed: {e}")

        log(f"  All JSON repair attempts failed")
        log(f"  Raw result (first 800 chars): {text[:800]}")
        return None

    def read_all_quotes(self, use_ai: bool = True) -> Dict:
        """Read all quote PDFs and return consolidated data"""
        log("=== Starting read_all_quotes ===")
        log(f"use_ai={use_ai}, api_key={'set' if self.api_key else 'NOT SET'}")
        self.find_quote_pdfs()

        quotes = []
        files_read = []
        errors = []

        for i, pdf_file in enumerate(self.quote_pdfs, 1):
            log(f"Processing quote {i}/{len(self.quote_pdfs)}: {pdf_file.name}")
            try:
                if use_ai and self.api_key:
                    quote_data = self.analyze_quote_pdf(pdf_file)
                    if quote_data:
                        quotes.append(quote_data)
                        files_read.append(pdf_file.name)
                        log(f"  Added to results")
                    else:
                        errors.append(f"{pdf_file.name}: No data extracted")
                        log(f"  FAILED: No data extracted")
                else:
                    # Fallback: just record file existence
                    log(f"  Using fallback (no AI)")
                    quotes.append({
                        'vendor_name': pdf_file.stem,
                        'source_file': pdf_file.name,
                        'file_path': str(pdf_file),
                        'line_items': [],
                        'grand_total': None
                    })
                    files_read.append(pdf_file.name)

            except Exception as e:
                errors.append(f"{pdf_file.name}: {e}")
                log(f"  EXCEPTION: {e}")

        self.quotes = quotes

        # Calculate summary stats
        total_quotes = len(quotes)
        quotes_with_pricing = len([q for q in quotes if q.get('grand_total')])
        total_value = sum(q.get('grand_total', 0) or 0 for q in quotes)
        vendors = list(set(q.get('vendor_name', 'Unknown') for q in quotes))

        log("=== Quote Reading Complete ===")
        log(f"  Total quotes: {total_quotes}")
        log(f"  With pricing: {quotes_with_pricing}")
        log(f"  Total value: ${total_value:,.2f}")
        log(f"  Vendors: {vendors}")
        log(f"  Errors: {len(errors)}")
        if errors:
            for err in errors:
                log(f"    - {err}")

        return {
            'quotes': quotes,
            'files_read': files_read,
            'errors': errors,
            'total_quotes': total_quotes,
            'quotes_with_pricing': quotes_with_pricing,
            'total_value': total_value,
            'vendors': vendors,
            'vendor_count': len(vendors)
        }

    def compare_with_estimate(self, estimate_data: Dict) -> Dict:
        """Compare quotes with internal estimate data"""
        # Build lookup of estimate items by mark
        estimate_by_mark = {}
        if estimate_data and 'openings' in estimate_data:
            for item in estimate_data['openings']:
                mark = str(item.get('mark', '')).strip().upper()
                if mark:
                    estimate_by_mark[mark] = item

        # Compare each quote's line items
        comparisons = []
        for quote in self.quotes:
            vendor_name = quote.get('vendor_name', 'Unknown')
            comparison = {
                'vendor_name': vendor_name,
                'quote_total': quote.get('grand_total'),
                'items': []
            }

            for line_item in quote.get('line_items', []):
                mark = str(line_item.get('mark', '')).strip().upper()
                quote_price = line_item.get('total_price') or line_item.get('unit_price')

                item_comparison = {
                    'mark': mark,
                    'description': line_item.get('description'),
                    'quote_price': quote_price,
                    'estimate_price': None,
                    'variance': None,
                    'variance_percent': None
                }

                # Find matching estimate item
                if mark and mark in estimate_by_mark:
                    est_item = estimate_by_mark[mark]
                    est_price = est_item.get('total_price') or est_item.get('unit_price')

                    if est_price and quote_price:
                        item_comparison['estimate_price'] = est_price
                        item_comparison['variance'] = quote_price - est_price
                        item_comparison['variance_percent'] = ((quote_price - est_price) / est_price) * 100

                comparison['items'].append(item_comparison)

            comparisons.append(comparison)

        return {
            'comparisons': comparisons,
            'quote_count': len(comparisons)
        }


def read_project_quotes(project_folder: str, api_key: str = None) -> Dict:
    """Convenience function to read all quotes from a project folder"""
    reader = QuoteReader(project_folder, api_key)
    return reader.read_all_quotes()


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

    result = read_project_quotes(test_folder)

    print(f"\nFiles read: {result['files_read']}")
    print(f"Total quotes: {result['total_quotes']}")
    print(f"Vendors: {result['vendors']}")
    print(f"Total value: ${result['total_value']:,.2f}")

    print(f"\nQuotes:")
    for quote in result['quotes']:
        print(f"  {quote.get('vendor_name')}: ${quote.get('grand_total', 0):,.2f} ({len(quote.get('line_items', []))} items)")
