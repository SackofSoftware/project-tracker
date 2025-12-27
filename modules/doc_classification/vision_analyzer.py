"""
Vision-based Drawing Analyzer
Uses OpenRouter's free Amazon Nova 2 Lite model for image analysis
with rate limiting (10 req/min) and concurrent workers.
"""

import os
import time
import base64
import threading
import requests
from pathlib import Path
from typing import Dict, List, Optional
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor, as_completed
from pdf2image import convert_from_path
from io import BytesIO


@dataclass
class RateLimiter:
    """Centralized rate limiter for API calls - 10 requests per minute"""
    requests_per_minute: int = 10

    def __init__(self, requests_per_minute: int = 10):
        self.requests_per_minute = requests_per_minute
        self.interval = 60.0 / requests_per_minute  # 6 seconds between calls
        self.last_request_time = 0.0
        self.lock = threading.Lock()
        self.request_count = 0

    def wait(self) -> float:
        """Wait until next request is allowed. Returns wait time."""
        with self.lock:
            now = time.time()
            time_since_last = now - self.last_request_time

            if time_since_last < self.interval:
                wait_time = self.interval - time_since_last
                time.sleep(wait_time)
            else:
                wait_time = 0

            self.last_request_time = time.time()
            self.request_count += 1
            return wait_time


class VisionDrawingAnalyzer:
    """Analyze construction drawings using vision AI"""

    API_URL = "https://openrouter.ai/api/v1/chat/completions"
    MODEL = "amazon/nova-lite-v1"  # Free tier model

    def __init__(self, api_key: str = None, max_workers: int = 3):
        self.api_key = api_key or os.getenv("OPENROUTER_API_KEY")
        self.max_workers = max_workers
        self.rate_limiter = RateLimiter(requests_per_minute=10)

    def _pdf_page_to_base64(self, pdf_path: str, page_num: int,
                            dpi: int = 200) -> tuple:
        """Convert a PDF page to base64 encoded JPEG

        Returns: (base64_string, width, height)
        """
        images = convert_from_path(
            pdf_path,
            first_page=page_num,
            last_page=page_num,
            dpi=dpi,
            fmt='jpeg'
        )

        if not images:
            return "", 0, 0

        img = images[0]
        width, height = img.size

        # Convert to base64 (full page - Nova handles large images well)
        buffer = BytesIO()
        img.save(buffer, format='JPEG', quality=90)
        return base64.b64encode(buffer.getvalue()).decode('utf-8'), width, height

    def _analyze_image(self, image_base64: str, page_num: int) -> Dict:
        """Send image to OpenRouter for analysis"""

        # Wait for rate limiter
        wait_time = self.rate_limiter.wait()

        prompt = """Analyze this construction drawing title block. Extract:
1. Sheet Number (e.g., A-201, M-101, E-001)
2. Discipline (Architectural, Structural, Mechanical, Electrical, etc.)
3. Sheet Title (e.g., "Floor Plan Level 1", "Exterior Elevations")

Respond ONLY with JSON:
{"sheet_id": "A-201", "discipline": "Architectural", "title": "Sheet Title", "confidence": 0.9}

If you cannot read the title block clearly, use confidence < 0.5."""

        try:
            response = requests.post(
                self.API_URL,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.MODEL,
                    "messages": [{
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {"type": "image_url", "image_url": {
                                "url": f"data:image/jpeg;base64,{image_base64}"
                            }}
                        ]
                    }],
                    "temperature": 0.1,
                    "max_tokens": 200,
                },
                timeout=30
            )

            if response.status_code == 200:
                content = response.json()['choices'][0]['message']['content']
                # Parse JSON from response
                import json
                import re

                # Clean up response
                content = content.strip()
                if content.startswith("```"):
                    content = re.sub(r'^```\w*\n?', '', content)
                    content = re.sub(r'\n?```$', '', content)

                result = json.loads(content)
                result['page'] = page_num
                result['method'] = 'vision'
                result['wait_time'] = wait_time
                return result
            else:
                return {
                    'page': page_num,
                    'error': f"API error: {response.status_code}",
                    'method': 'vision',
                    'confidence': 0
                }

        except Exception as e:
            return {
                'page': page_num,
                'error': str(e),
                'method': 'vision',
                'confidence': 0
            }

    def analyze_page(self, pdf_path: str, page_num: int) -> Dict:
        """Analyze a single PDF page"""
        try:
            image_base64 = self._pdf_page_to_base64(pdf_path, page_num)
            if not image_base64:
                return {'page': page_num, 'error': 'Failed to convert page', 'confidence': 0}

            return self._analyze_image(image_base64, page_num)
        except Exception as e:
            return {'page': page_num, 'error': str(e), 'confidence': 0}

    def analyze_pages(self, pdf_path: str, pages: List[int],
                      progress_callback=None) -> List[Dict]:
        """Analyze multiple pages concurrently with rate limiting"""
        results = []
        total = len(pages)
        completed = 0

        print(f"Analyzing {total} pages with {self.max_workers} workers...")
        print(f"Rate limit: {self.rate_limiter.requests_per_minute} req/min")
        print(f"Estimated time: {total * 6 / self.max_workers:.0f} seconds")
        print()

        def process_page(page_num):
            return self.analyze_page(pdf_path, page_num)

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {executor.submit(process_page, p): p for p in pages}

            for future in as_completed(futures):
                page_num = futures[future]
                try:
                    result = future.result()
                    results.append(result)
                    completed += 1

                    # Progress output
                    if result.get('error'):
                        print(f"  Page {page_num}: ERROR - {result['error'][:50]}")
                    else:
                        print(f"  Page {page_num}: {result.get('sheet_id', '?')} - "
                              f"{result.get('discipline', '?')} "
                              f"({result.get('confidence', 0):.0%})")

                    if progress_callback:
                        progress_callback(completed, total, result)

                except Exception as e:
                    results.append({'page': page_num, 'error': str(e), 'confidence': 0})
                    completed += 1

        # Sort by page number
        results.sort(key=lambda x: x.get('page', 0))
        return results

    def analyze_sample(self, pdf_path: str, sample_size: int = 5) -> Dict:
        """Analyze a random sample of pages from a PDF"""
        import random
        import pdfplumber

        with pdfplumber.open(pdf_path) as pdf:
            total_pages = len(pdf.pages)

        # Select random pages
        sample_pages = sorted(random.sample(range(1, total_pages + 1),
                                           min(sample_size, total_pages)))

        print(f"=== VISION ANALYSIS TEST ===")
        print(f"File: {Path(pdf_path).name}")
        print(f"Total pages: {total_pages}")
        print(f"Sample pages: {sample_pages}")
        print()

        results = self.analyze_pages(pdf_path, sample_pages)

        # Summary
        successful = [r for r in results if r.get('confidence', 0) > 0.5]
        print()
        print(f"=== SUMMARY ===")
        print(f"Analyzed: {len(results)} pages")
        print(f"Successful: {len(successful)} ({len(successful)/len(results)*100:.0f}%)")
        print(f"API calls made: {self.rate_limiter.request_count}")

        return {
            'results': results,
            'total_pages': total_pages,
            'sample_size': len(results),
            'success_rate': len(successful) / len(results) if results else 0
        }


# Convenience function
def analyze_drawings_with_vision(pdf_path: str, pages: List[int] = None,
                                  sample_size: int = 5, api_key: str = None) -> Dict:
    """
    Analyze construction drawings using vision AI.

    Args:
        pdf_path: Path to PDF file
        pages: Specific pages to analyze (1-indexed), or None for random sample
        sample_size: Number of random pages if pages not specified
        api_key: OpenRouter API key (or use OPENROUTER_API_KEY env var)
    """
    analyzer = VisionDrawingAnalyzer(api_key=api_key)

    if pages:
        return {
            'results': analyzer.analyze_pages(pdf_path, pages),
            'pages_analyzed': pages
        }
    else:
        return analyzer.analyze_sample(pdf_path, sample_size)


if __name__ == "__main__":
    import sys
    from dotenv import load_dotenv
    load_dotenv()

    # Get PDF path from args
    if len(sys.argv) > 1:
        test_pdf = sys.argv[1]
    else:
        print("Usage: python vision_analyzer.py <path_to_pdf>")
        sys.exit(1)

    result = analyze_drawings_with_vision(test_pdf, sample_size=3)
    print("\nResults:", result)
