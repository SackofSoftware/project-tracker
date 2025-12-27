"""
Stage 8: Quote Analysis
Identifies and analyzes vendor quotes from PDFs in the project folder.
"""

import re
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime

try:
    import pdfplumber
    PDFPLUMBER_AVAILABLE = True
except ImportError:
    PDFPLUMBER_AVAILABLE = False
    logging.warning("pdfplumber not available - quote analysis will be limited")


@dataclass
class StageResult:
    success: bool
    data: Dict
    error: Optional[str] = None


# Comprehensive vendor signatures for identification
VENDOR_SIGNATURES = {
    'kawneer': ['KAWNEER', 'ALCOA KAWNEER', '1600 WALL SYSTEM', '451 ENTRANCES'],
    'oldcastle': ['OLDCASTLE', 'CRL', 'OLDCASTLE BUILDINGENVELOPE'],
    'ykk': ['YKK', 'YKK AP', 'YKKAP'],
    'marvin': ['MARVIN', 'MARVIN WINDOWS', 'INTEGRITY BY MARVIN'],
    'andersen': ['ANDERSEN', 'ANDERSEN WINDOWS', 'RENEWAL BY ANDERSEN'],
    'pella': ['PELLA', 'PELLA WINDOWS'],
    'alpen': ['ALPEN', 'ALPEN HPP', 'ALPEN HIGH PERFORMANCE'],
    'milgard': ['MILGARD', 'MILGARD WINDOWS'],
    'allegion': ['ALLEGION', 'SCHLAGE', 'VON DUPRIN', 'LCN'],
    'assa_abloy': ['ASSA ABLOY', 'NORTON', 'SARGENT', 'CORBIN RUSSWIN'],
    'dormakaba': ['DORMAKABA', 'DORMA', 'KABA'],
    'twi': ['TWI', 'THERMAL WINDOWS', 'THERMAL WINDOWS INC'],
    'efco': ['EFCO', 'EFCO CORPORATION'],
    'vistawall': ['VISTAWALL', 'APOGEE'],
    'trulite': ['TRULITE', 'TRULITE GLASS'],
    'vitro': ['VITRO', 'VITRO GLASS', 'SOLARBAN'],
    'guardian': ['GUARDIAN', 'GUARDIAN GLASS'],
    'viracon': ['VIRACON'],
    'wausau': ['WAUSAU', 'WAUSAU WINDOW'],
    'tubelite': ['TUBELITE'],
    'ceco': ['CECO', 'CECO DOOR'],
    'steelcraft': ['STEELCRAFT'],
    'curries': ['CURRIES'],
    'republic': ['REPUBLIC', 'REPUBLIC DOOR'],
}

# Quote-related keywords for file identification
QUOTE_KEYWORDS = [
    'quote', 'proposal', 'pricing', 'bid', 'estimate',
    'quotation', 'price', 'cost', 'budgetary'
]


class QuoteAnalysisStage:
    """Stage 8: Analyzes vendor quotes from project PDFs."""

    def __init__(self, project_folder: Path, ai_provider=None):
        """
        Initialize the quote analysis stage.

        Args:
            project_folder: Path to the project folder
            ai_provider: Optional AI provider (not used currently)
        """
        self.project_folder = Path(project_folder)
        self.logger = logging.getLogger(__name__)
        self.stage_name = "Quote Analysis"

    async def run(self) -> StageResult:
        """
        Run quote analysis on project folder.

        Returns:
            StageResult with quote analysis data
        """
        self.logger.info(f"Starting {self.stage_name} for {self.project_folder}")

        try:
            if not PDFPLUMBER_AVAILABLE:
                return StageResult(
                    success=False,
                    data={},
                    error="pdfplumber not available - install with: pip install pdfplumber"
                )

            # Find potential quote files
            quote_files = self._find_quote_files(self.project_folder)
            self.logger.info(f"Found {len(quote_files)} potential quote files")

            # Analyze each quote file
            quotes = []
            for pdf_path in quote_files:
                quote_data = self._analyze_quote_pdf(pdf_path)
                if quote_data:
                    quotes.append(quote_data)

            # Compile results
            result_data = {
                'quotes_found': len(quotes),
                'quote_files': [str(q['file_path']) for q in quotes],
                'quotes': quotes,
                'vendors_identified': list(set(q['vendor'] for q in quotes if q.get('vendor'))),
                'total_quote_value': sum(q.get('total_price', 0) for q in quotes if q.get('total_price')),
            }

            self.logger.info(f"Quote analysis complete: {len(quotes)} quotes from {len(result_data['vendors_identified'])} vendors")

            return StageResult(
                success=True,
                data=result_data
            )

        except Exception as e:
            self.logger.error(f"Error in {self.stage_name}: {str(e)}", exc_info=True)
            return StageResult(
                success=False,
                data={},
                error=str(e)
            )

    def _find_quote_files(self, project_folder: Path) -> List[Path]:
        """
        Find potential quote PDFs in project folder.

        Args:
            project_folder: Path to project folder

        Returns:
            List of PDF file paths
        """
        quote_files = []

        # Check for Quotes subfolder
        quotes_folder = project_folder / "Quotes"
        if quotes_folder.exists() and quotes_folder.is_dir():
            self.logger.info(f"Found Quotes folder: {quotes_folder}")
            quote_files.extend(quotes_folder.glob("*.pdf"))

        # Search for PDFs with quote-related keywords in filename
        for pdf_file in project_folder.rglob("*.pdf"):
            filename_lower = pdf_file.name.lower()

            # Check for quote keywords
            if any(keyword in filename_lower for keyword in QUOTE_KEYWORDS):
                if pdf_file not in quote_files:
                    quote_files.append(pdf_file)
                continue

            # Check for vendor names in filename
            for vendor_id, signatures in VENDOR_SIGNATURES.items():
                if any(sig.lower().replace(' ', '') in filename_lower.replace(' ', '')
                       for sig in signatures):
                    if pdf_file not in quote_files:
                        quote_files.append(pdf_file)
                    break

        return sorted(quote_files)

    def _analyze_quote_pdf(self, pdf_path: Path) -> Optional[Dict]:
        """
        Analyze a single PDF for quote information.

        Args:
            pdf_path: Path to PDF file

        Returns:
            Dictionary with quote data or None if analysis failed
        """
        try:
            self.logger.info(f"Analyzing quote PDF: {pdf_path.name}")

            # Extract text from PDF
            text = self._extract_pdf_text(pdf_path)
            if not text:
                self.logger.warning(f"No text extracted from {pdf_path.name}")
                return None

            # Identify vendor
            vendor = self._identify_vendor(text)

            # Extract quote metadata
            quote_date = self._extract_date(text)
            project_ref = self._extract_project_reference(text)
            total_price = self._extract_total_price(text)
            line_items = self._extract_line_items(text)

            quote_data = {
                'file_path': str(pdf_path),
                'filename': pdf_path.name,
                'vendor': vendor,
                'quote_date': quote_date,
                'project_reference': project_ref,
                'total_price': total_price,
                'line_items_count': len(line_items) if line_items else 0,
                'line_items': line_items[:10] if line_items else [],  # Limit to first 10 items
                'text_length': len(text),
            }

            self.logger.info(f"Quote analyzed: {pdf_path.name} - Vendor: {vendor}, Price: ${total_price or 'N/A'}")

            return quote_data

        except Exception as e:
            self.logger.error(f"Error analyzing {pdf_path.name}: {str(e)}")
            return None

    def _extract_pdf_text(self, pdf_path: Path) -> str:
        """
        Extract text from PDF using pdfplumber.

        Args:
            pdf_path: Path to PDF file

        Returns:
            Extracted text
        """
        try:
            text_parts = []
            with pdfplumber.open(pdf_path) as pdf:
                # Extract text from first 5 pages (most quotes have key info early)
                for page in pdf.pages[:5]:
                    page_text = page.extract_text()
                    if page_text:
                        text_parts.append(page_text)

            return '\n'.join(text_parts)

        except Exception as e:
            self.logger.error(f"Error extracting text from {pdf_path.name}: {str(e)}")
            return ""

    def _identify_vendor(self, text: str) -> Optional[str]:
        """
        Identify vendor from PDF text using signature patterns.

        Args:
            text: PDF text content

        Returns:
            Vendor identifier or None
        """
        text_upper = text.upper()

        # Check each vendor's signatures
        for vendor_id, signatures in VENDOR_SIGNATURES.items():
            for signature in signatures:
                if signature in text_upper:
                    return vendor_id

        return None

    def _extract_date(self, text: str) -> Optional[str]:
        """
        Extract quote date from text.

        Args:
            text: PDF text content

        Returns:
            Date string or None
        """
        # Common date patterns
        date_patterns = [
            r'(?:quote\s+date|date)[:\s]+(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})',
            r'(?:date)[:\s]+([A-Za-z]+\s+\d{1,2},?\s+\d{4})',
            r'(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})',
        ]

        for pattern in date_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(1)

        return None

    def _extract_project_reference(self, text: str) -> Optional[str]:
        """
        Extract project reference/name from text.

        Args:
            text: PDF text content

        Returns:
            Project reference or None
        """
        # Common project reference patterns
        ref_patterns = [
            r'(?:project|job|ref)[:\s#]+([A-Z0-9-]+)',
            r'(?:project\s+name|job\s+name)[:\s]+([^\n]+)',
            r'(?:re|regarding)[:\s]+([^\n]+)',
        ]

        for pattern in ref_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                ref = match.group(1).strip()
                if len(ref) > 3 and len(ref) < 100:  # Reasonable length
                    return ref

        return None

    def _extract_total_price(self, text: str) -> Optional[float]:
        """
        Extract total price from text.

        Args:
            text: PDF text content

        Returns:
            Total price as float or None
        """
        # Price patterns - look for totals
        price_patterns = [
            r'(?:total|grand\s+total|total\s+price|total\s+amount)[:\s]+\$?\s*([\d,]+\.?\d*)',
            r'(?:total)[:\s]+\$\s*([\d,]+\.?\d*)',
            r'\$\s*([\d,]+\.?\d*)\s*(?:total)',
        ]

        for pattern in price_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                price_str = match.group(1).replace(',', '')
                try:
                    price = float(price_str)
                    if price > 0 and price < 100000000:  # Reasonable range
                        return price
                except ValueError:
                    continue

        return None

    def _extract_line_items(self, text: str) -> Optional[List[Dict]]:
        """
        Extract line items from text.

        Args:
            text: PDF text content

        Returns:
            List of line item dictionaries or None
        """
        line_items = []

        # Look for tabular data with prices
        # This is a simplified extraction - could be enhanced
        lines = text.split('\n')

        for line in lines:
            # Look for lines with dollar amounts
            price_match = re.search(r'\$\s*([\d,]+\.?\d*)', line)
            if price_match:
                # Try to extract quantity and description
                qty_match = re.search(r'^(\d+)', line.strip())

                item = {
                    'description': line.strip()[:100],  # First 100 chars
                    'price': None,
                    'quantity': None,
                }

                try:
                    price_str = price_match.group(1).replace(',', '')
                    item['price'] = float(price_str)
                except ValueError:
                    pass

                if qty_match:
                    try:
                        item['quantity'] = int(qty_match.group(1))
                    except ValueError:
                        pass

                if item['price'] and item['price'] > 0:
                    line_items.append(item)

        return line_items if line_items else None


# Convenience function for standalone usage
async def analyze_quotes(project_folder: Path, context: Dict = None) -> StageResult:
    """
    Standalone function to run quote analysis.

    Args:
        project_folder: Path to project folder
        context: Optional pipeline context

    Returns:
        StageResult with quote analysis data
    """
    stage = QuoteAnalysisStage()
    return await stage.run(project_folder, context or {})
