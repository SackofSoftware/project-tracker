"""
Smart Notes Processor
Uses AI to parse notes and documents, extracting structured data
"""

import os
import re
import json
import shutil
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Tuple
import requests


class SmartNotesProcessor:
    """Processes notes and documents with AI to extract structured data"""

    # OpenRouter API config
    API_URL = "https://openrouter.ai/api/v1/chat/completions"
    MODEL = "amazon/nova-lite-v1"  # Free tier

    # Document type patterns for quick classification
    DOC_PATTERNS = {
        'quote': [r'quot', r'proposal', r'price', r'estimate', r'bid\s*price'],
        'addendum': [r'addend', r'revision', r'change\s*order'],
        'rfi': [r'rfi', r'request\s*for\s*information', r'clarification'],
        'submittal': [r'submittal', r'shop\s*drawing', r'product\s*data'],
        'spec': [r'specification', r'section\s*\d{5,6}', r'division\s*\d'],
        'contract': [r'contract', r'agreement', r'terms'],
        'insurance': [r'insurance', r'certificate', r'coi', r'liability'],
    }

    def __init__(self, api_key: str = None):
        self.api_key = api_key or os.getenv("OPENROUTER_API_KEY")

    def _call_ai(self, system_prompt: str, user_content: str) -> Optional[str]:
        """Make API call to OpenRouter"""
        if not self.api_key:
            return None

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
                    "max_tokens": 1000,
                },
                timeout=30
            )

            if response.status_code == 200:
                data = response.json()
                return data['choices'][0]['message']['content']
            else:
                print(f"AI API error: {response.status_code} - {response.text}")
                return None

        except Exception as e:
            print(f"AI call failed: {e}")
            return None

    def parse_note_text(self, note_text: str) -> Dict:
        """
        Parse free-form note text and extract structured data.
        Returns dict with extracted fields and actions to take.
        """
        system_prompt = """You are a construction project data extractor for a glazing/windows contractor.
Parse the note and extract any relevant information. Return ONLY valid JSON with these fields:

{
    "note_summary": "brief summary of the note",
    "extracted": {
        "vendor_name": "company name if mentioned",
        "quote_amount": null or number (just the number, no $ or commas),
        "quote_date": "YYYY-MM-DD if mentioned",
        "quote_valid_until": "YYYY-MM-DD if mentioned",
        "scope_items": ["list of items/products quoted"],
        "bid_decision": "bid" or "no_bid" or null if mentioned,
        "decision_reason": "reason if mentioned",
        "due_date": "YYYY-MM-DD if a deadline mentioned",
        "contact_name": "person name if mentioned",
        "contact_phone": "phone if mentioned",
        "contact_email": "email if mentioned",
        "tags": ["relevant tags like 'priority', 'followup', 'aluminum', 'storefront']"
    },
    "actions": ["list of suggested actions like 'update_estimate', 'add_vendor_quote', 'set_bid_decision'"]
}

If a field is not found in the text, use null. Extract dollar amounts as plain numbers."""

        result = self._call_ai(system_prompt, note_text)

        if result:
            try:
                # Clean up potential markdown code blocks
                result = result.strip()
                if result.startswith("```"):
                    result = re.sub(r'^```\w*\n?', '', result)
                    result = re.sub(r'\n?```$', '', result)
                return json.loads(result)
            except json.JSONDecodeError:
                pass

        # Fallback to regex parsing if AI fails
        return self._regex_parse_note(note_text)

    def _regex_parse_note(self, note_text: str) -> Dict:
        """Fallback regex-based parsing"""
        extracted = {
            "vendor_name": None,
            "quote_amount": None,
            "quote_date": None,
            "scope_items": [],
            "tags": []
        }

        # Extract dollar amounts
        money_match = re.search(r'\$[\d,]+(?:\.\d{2})?', note_text)
        if money_match:
            amount = money_match.group().replace('$', '').replace(',', '')
            try:
                extracted['quote_amount'] = float(amount)
            except:
                pass

        # Extract dates
        date_match = re.search(r'\d{1,2}[-/]\d{1,2}[-/]\d{2,4}', note_text)
        if date_match:
            extracted['quote_date'] = date_match.group()

        return {
            "note_summary": note_text[:100] + "..." if len(note_text) > 100 else note_text,
            "extracted": extracted,
            "actions": []
        }

    def classify_document(self, filename: str, text_content: str = None) -> Tuple[str, float]:
        """
        Classify a document based on filename and optional text content.
        Returns (doc_type, confidence)
        """
        filename_lower = filename.lower()

        # Check filename patterns first
        for doc_type, patterns in self.DOC_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, filename_lower, re.IGNORECASE):
                    return (doc_type, 0.8)

        # If we have text content, use AI
        if text_content and self.api_key:
            system_prompt = """Classify this construction document. Return ONLY JSON:
{
    "document_type": "quote" | "addendum" | "rfi" | "submittal" | "spec" | "contract" | "insurance" | "drawing" | "unknown",
    "confidence": 0.0 to 1.0,
    "vendor": "vendor name if this is a quote",
    "key_info": "one line summary of the document"
}"""

            # Only send first 2000 chars to save tokens
            result = self._call_ai(system_prompt, text_content[:2000])
            if result:
                try:
                    result = result.strip()
                    if result.startswith("```"):
                        result = re.sub(r'^```\w*\n?', '', result)
                        result = re.sub(r'\n?```$', '', result)
                    data = json.loads(result)
                    return (data.get('document_type', 'unknown'), data.get('confidence', 0.5))
                except:
                    pass

        return ('unknown', 0.3)

    def process_quote_pdf(self, pdf_path: Path, project_path: Path) -> Dict:
        """
        Process a quote PDF - extract info and suggest filing location.
        """
        # Try to extract text from PDF
        text_content = self._extract_pdf_text(pdf_path)

        if not text_content:
            return {
                "status": "error",
                "message": "Could not extract text from PDF"
            }

        # Use AI to parse quote
        system_prompt = """You are parsing a vendor quote/proposal for a glazing contractor.
Extract the following and return ONLY valid JSON:

{
    "vendor_name": "company name",
    "quote_number": "quote/proposal number if present",
    "quote_date": "YYYY-MM-DD",
    "valid_until": "YYYY-MM-DD or null",
    "total_amount": number or null,
    "line_items": [
        {"description": "item", "quantity": 1, "unit_price": 100, "total": 100}
    ],
    "scope_summary": "brief summary of what's included",
    "exclusions": ["list of exclusions if mentioned"],
    "lead_time": "delivery/lead time if mentioned",
    "contact": {
        "name": "sales rep name",
        "phone": "phone",
        "email": "email"
    },
    "notes": "any other important notes"
}"""

        result = self._call_ai(system_prompt, text_content[:4000])

        if result:
            try:
                result = result.strip()
                if result.startswith("```"):
                    result = re.sub(r'^```\w*\n?', '', result)
                    result = re.sub(r'\n?```$', '', result)
                quote_data = json.loads(result)

                # Determine filing location
                vendor = quote_data.get('vendor_name', 'Unknown')
                safe_vendor = re.sub(r'[^\w\s-]', '', vendor).strip().replace(' ', '_')

                quotes_folder = project_path / "Quotes"
                quotes_folder.mkdir(exist_ok=True)

                # Rename and move file
                new_filename = f"{safe_vendor}_Quote_{datetime.now().strftime('%Y%m%d')}.pdf"
                dest_path = quotes_folder / new_filename

                return {
                    "status": "success",
                    "quote_data": quote_data,
                    "suggested_path": str(dest_path),
                    "vendor": vendor,
                    "total": quote_data.get('total_amount'),
                    "summary": quote_data.get('scope_summary')
                }
            except json.JSONDecodeError as e:
                pass

        return {
            "status": "partial",
            "message": "Could not fully parse quote",
            "text_preview": text_content[:500]
        }

    def _extract_pdf_text(self, pdf_path: Path) -> Optional[str]:
        """Extract text from PDF using pdftotext"""
        try:
            import subprocess
            result = subprocess.run(
                ['pdftotext', '-layout', str(pdf_path), '-'],
                capture_output=True,
                text=True,
                timeout=30
            )
            if result.returncode == 0:
                return result.stdout
        except Exception as e:
            print(f"PDF text extraction failed: {e}")
        return None

    def suggest_folder_structure(self, project_path: Path) -> Dict[str, Path]:
        """Suggest standard folder structure for a project"""
        folders = {
            'quotes': project_path / 'Quotes',
            'addenda': project_path / 'Addenda',
            'drawings': project_path / 'Drawings',
            'specs': project_path / 'Specs',
            'submittals': project_path / 'Submittals',
            'rfis': project_path / 'RFIs',
            'contracts': project_path / 'Contracts',
            'correspondence': project_path / 'Correspondence',
        }
        return folders

    def file_document(self, source_path: Path, project_path: Path, doc_type: str) -> Path:
        """Move/copy document to appropriate project subfolder"""
        folders = self.suggest_folder_structure(project_path)

        # Map doc types to folders
        folder_map = {
            'quote': 'quotes',
            'addendum': 'addenda',
            'drawing': 'drawings',
            'spec': 'specs',
            'submittal': 'submittals',
            'rfi': 'rfis',
            'contract': 'contracts',
        }

        target_folder = folders.get(folder_map.get(doc_type, 'correspondence'))
        target_folder.mkdir(parents=True, exist_ok=True)

        dest_path = target_folder / source_path.name

        # Handle duplicate names
        counter = 1
        while dest_path.exists():
            stem = source_path.stem
            suffix = source_path.suffix
            dest_path = target_folder / f"{stem}_{counter}{suffix}"
            counter += 1

        shutil.copy2(source_path, dest_path)
        return dest_path


# Module-level singleton
_processor = None


def get_processor() -> SmartNotesProcessor:
    """Get or create the global processor"""
    global _processor
    if _processor is None:
        _processor = SmartNotesProcessor()
    return _processor
