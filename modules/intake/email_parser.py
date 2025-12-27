"""
Email Parser Module

LLM-powered parsing of bid invitation emails (.eml files).
Handles various email formats from PlanHub, BuildingConnected, direct GC emails, etc.
"""

import email
from email import policy
from pathlib import Path
import json
import re
import os
from typing import Optional
from bs4 import BeautifulSoup
import requests


class EmailParser:
    """LLM-powered email parsing for bid invitations."""

    EXTRACTION_PROMPT = """You are extracting bid invitation details from a construction industry email.

Return ONLY valid JSON with these fields (use null if not found):

{{
    "project_name": "Full project name",
    "location": "Project address (street, city, state, zip)",
    "bid_date": "Bid due date in YYYY-MM-DD format",
    "bid_time": "Bid due time (e.g., '2:00 PM EST')",
    "gc_name": "General contractor company name",
    "gc_contact": "GC contact person name",
    "gc_email": "GC contact email",
    "gc_phone": "GC contact phone",
    "owner": "Project owner/client name",
    "architect": "Architect firm name",
    "trade_scope": "Trade/scope requested (e.g., 'Division 8', 'Glazing', 'Windows & Doors')",
    "project_type": "Type (renovation, new construction, addition, etc.)",
    "estimated_value": "Project value if mentioned",
    "prebid_meeting": "Prebid meeting date/time if mentioned",
    "notes": "Any other important details"
}}

EMAIL SUBJECT: {subject}
EMAIL FROM: {from_addr}
EMAIL DATE: {date}

EMAIL BODY:
{body}

Return ONLY the JSON object, no other text."""

    def __init__(self, llm_provider: str = 'auto'):
        """
        Initialize email parser.

        Args:
            llm_provider: 'lm_studio', 'openrouter', or 'auto' (tries LM Studio first)
        """
        self.llm_provider = llm_provider
        self.openrouter_api_key = os.getenv('OPENROUTER_API_KEY')

    def parse_eml(self, eml_path: Path) -> dict:
        """
        Parse an .eml file and extract bid invitation details using LLM.

        Args:
            eml_path: Path to the .eml file

        Returns:
            Dict with 'raw' email data and 'extracted' structured fields
        """
        eml_path = Path(eml_path)

        # Extract raw email content
        with open(eml_path, 'rb') as f:
            msg = email.message_from_binary_file(f, policy=policy.default)

        subject = str(msg['Subject'] or '')
        from_addr = str(msg['From'] or '')
        date = str(msg['Date'] or '')
        body = self._get_body(msg)

        # Use LLM to extract structured data
        extracted = self._extract_with_llm(subject, from_addr, date, body)

        return {
            'raw': {
                'subject': subject,
                'from': from_addr,
                'date': date,
                'body_preview': body[:1000] if body else ''
            },
            'extracted': extracted,
            'source_file': str(eml_path),
            'filename': eml_path.name
        }

    def _get_body(self, msg) -> str:
        """Extract plain text body from email, handling multipart MIME."""
        body_text = ''

        if msg.is_multipart():
            # Try to get plain text first
            for part in msg.walk():
                content_type = part.get_content_type()
                if content_type == 'text/plain':
                    try:
                        content = part.get_content()
                        if isinstance(content, str):
                            body_text = content
                            break
                    except:
                        pass

            # If no plain text, try HTML and strip tags
            if not body_text:
                for part in msg.walk():
                    content_type = part.get_content_type()
                    if content_type == 'text/html':
                        try:
                            content = part.get_content()
                            if isinstance(content, str):
                                body_text = self._strip_html(content)
                                break
                        except:
                            pass
        else:
            # Single part message
            try:
                content = msg.get_content()
                if isinstance(content, str):
                    content_type = msg.get_content_type()
                    if content_type == 'text/html':
                        body_text = self._strip_html(content)
                    else:
                        body_text = content
            except:
                pass

        # Clean up the text
        body_text = self._clean_text(body_text)
        return body_text

    def _strip_html(self, html: str) -> str:
        """Strip HTML tags and decode entities."""
        try:
            soup = BeautifulSoup(html, 'html.parser')

            # Remove script and style elements
            for script in soup(['script', 'style']):
                script.decompose()

            # Get text
            text = soup.get_text(separator=' ')
            return text
        except:
            # Fallback: simple regex strip
            text = re.sub(r'<[^>]+>', ' ', html)
            return text

    def _clean_text(self, text: str) -> str:
        """Clean up extracted text."""
        if not text:
            return ''

        # Decode common HTML entities
        text = text.replace('&nbsp;', ' ')
        text = text.replace('&amp;', '&')
        text = text.replace('&lt;', '<')
        text = text.replace('&gt;', '>')
        text = text.replace('&quot;', '"')

        # Remove excessive whitespace
        text = re.sub(r'\s+', ' ', text)

        # Remove very long URLs (common in email tracking)
        text = re.sub(r'https?://[^\s]{100,}', '[URL]', text)

        return text.strip()

    def _extract_with_llm(self, subject: str, from_addr: str, date: str, body: str) -> dict:
        """Use LLM to extract structured fields from email."""

        # Truncate body if too long
        body_truncated = body[:8000] if body else ''

        prompt = self.EXTRACTION_PROMPT.format(
            subject=subject,
            from_addr=from_addr,
            date=date,
            body=body_truncated
        )

        # Try LM Studio first if auto or explicitly requested
        if self.llm_provider in ('auto', 'lm_studio'):
            response = self._call_lm_studio(prompt)
            if response:
                return self._parse_json_response(response)

        # Try OpenRouter
        if self.llm_provider in ('auto', 'openrouter') and self.openrouter_api_key:
            response = self._call_openrouter(prompt)
            if response:
                return self._parse_json_response(response)

        # Return empty extraction if no LLM available
        return self._empty_extraction()

    def _call_lm_studio(self, prompt: str) -> Optional[str]:
        """Call LM Studio API at localhost:1234."""
        try:
            response = requests.post(
                'http://localhost:1234/v1/chat/completions',
                json={
                    'messages': [{'role': 'user', 'content': prompt}],
                    'temperature': 0.1,
                    'max_tokens': 1500
                },
                timeout=60
            )
            if response.status_code == 200:
                data = response.json()
                return data['choices'][0]['message']['content']
        except requests.exceptions.RequestException:
            pass
        return None

    def _call_openrouter(self, prompt: str) -> Optional[str]:
        """Call OpenRouter API."""
        try:
            response = requests.post(
                'https://openrouter.ai/api/v1/chat/completions',
                headers={
                    'Authorization': f'Bearer {self.openrouter_api_key}',
                    'Content-Type': 'application/json'
                },
                json={
                    'model': 'openai/gpt-4.1-nano',
                    'messages': [{'role': 'user', 'content': prompt}],
                    'temperature': 0.1,
                    'max_tokens': 1500
                },
                timeout=60
            )
            if response.status_code == 200:
                data = response.json()
                return data['choices'][0]['message']['content']
        except requests.exceptions.RequestException:
            pass
        return None

    def _parse_json_response(self, response: str) -> dict:
        """Parse JSON from LLM response, handling markdown code blocks."""
        if not response:
            return self._empty_extraction()

        # Remove markdown code blocks if present
        response = response.strip()
        if response.startswith('```'):
            # Find the end of the code block
            lines = response.split('\n')
            # Remove first line (```json or ```)
            if lines[0].startswith('```'):
                lines = lines[1:]
            # Remove last line if it's ```
            if lines and lines[-1].strip() == '```':
                lines = lines[:-1]
            response = '\n'.join(lines)

        # Try to find JSON object in response
        try:
            # Try direct parse first
            return json.loads(response)
        except json.JSONDecodeError:
            pass

        # Try to extract JSON from response
        json_match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', response, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group())
            except json.JSONDecodeError:
                pass

        return self._empty_extraction()

    def _empty_extraction(self) -> dict:
        """Return empty extraction template."""
        return {
            'project_name': None,
            'location': None,
            'bid_date': None,
            'bid_time': None,
            'gc_name': None,
            'gc_contact': None,
            'gc_email': None,
            'gc_phone': None,
            'owner': None,
            'architect': None,
            'trade_scope': None,
            'project_type': None,
            'estimated_value': None,
            'prebid_meeting': None,
            'notes': None
        }


def parse_email_file(eml_path: Path, llm_provider: str = 'auto') -> dict:
    """
    Convenience function to parse an email file.

    Args:
        eml_path: Path to the .eml file
        llm_provider: 'lm_studio', 'openrouter', or 'auto'

    Returns:
        Parsed email data with extracted fields
    """
    parser = EmailParser(llm_provider=llm_provider)
    return parser.parse_eml(eml_path)
