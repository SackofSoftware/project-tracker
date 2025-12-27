"""
Vision LLM helper for PlanHub scraper

Uses vision models to:
1. Confirm page is fully loaded (no spinners)
2. Identify clickable lead items
3. Debug by seeing what the scraper sees
"""
import os
import base64
import requests
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple, Dict

from .config import BASE_DIR

# Try to import PIL for image cropping
try:
    from PIL import Image
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False
    print("Note: PIL not installed, image cropping disabled. Run: pip install pillow")

# OpenRouter API (same as existing project-tracker)
OPENROUTER_API_KEY = os.getenv('OPENROUTER_API_KEY')

# Free vision models (in preference order)
VISION_MODELS = [
    "google/gemma-3-4b-it:free",
    "google/gemma-3-12b-it:free",
    "google/gemini-2.0-flash-lite-001",
]

# Alternative: Local LM Studio
LM_STUDIO_URL = "http://localhost:1234/v1/chat/completions"

# Screenshot directory
SCREENSHOT_DIR = BASE_DIR / "debug_screenshots"

# Default crop regions for PlanHub (x, y, width, height as percentages)
# These exclude left sidebar, header, and footer to focus on main content
CROP_REGIONS = {
    'lead_list': {
        'left_pct': 0.20,    # Skip 20% on left (sidebar)
        'top_pct': 0.10,     # Skip 10% on top (header)
        'right_pct': 0.02,   # Skip 2% on right (scrollbar)
        'bottom_pct': 0.05,  # Skip 5% on bottom (footer)
    },
    'content_area': {
        'left_pct': 0.22,
        'top_pct': 0.12,
        'right_pct': 0.03,
        'bottom_pct': 0.08,
    },
    'full': {
        'left_pct': 0,
        'top_pct': 0,
        'right_pct': 0,
        'bottom_pct': 0,
    }
}


def crop_image(image_path: str, region: str = 'lead_list', output_path: str = None) -> str:
    """
    Crop an image to focus on a specific region.

    Args:
        image_path: Path to source image
        region: Preset region name ('lead_list', 'content_area', 'full')
                or dict with left_pct, top_pct, right_pct, bottom_pct
        output_path: Where to save cropped image (defaults to overwrite source)

    Returns:
        Path to cropped image
    """
    if not PIL_AVAILABLE:
        return image_path

    # Get crop settings
    if isinstance(region, str):
        crop_settings = CROP_REGIONS.get(region, CROP_REGIONS['full'])
    else:
        crop_settings = region

    try:
        img = Image.open(image_path)
        width, height = img.size

        # Calculate crop box (left, top, right, bottom)
        left = int(width * crop_settings.get('left_pct', 0))
        top = int(height * crop_settings.get('top_pct', 0))
        right = int(width * (1 - crop_settings.get('right_pct', 0)))
        bottom = int(height * (1 - crop_settings.get('bottom_pct', 0)))

        # Crop and save
        cropped = img.crop((left, top, right, bottom))

        output = output_path or image_path
        cropped.save(output)

        print(f"    Cropped image: {width}x{height} -> {right-left}x{bottom-top}")
        return output

    except Exception as e:
        print(f"    Crop error: {e}")
        return image_path


def crop_to_element(page, selector: str, output_path: str, padding: int = 10) -> Optional[str]:
    """
    Take a screenshot cropped to a specific element's bounding box.

    Args:
        page: Playwright page object
        selector: CSS selector for the element to capture
        output_path: Where to save the screenshot
        padding: Extra pixels around the element

    Returns:
        Path to screenshot, or None if element not found
    """
    try:
        element = page.query_selector(selector)
        if not element:
            print(f"    Element not found: {selector}")
            return None

        # Get element's bounding box
        box = element.bounding_box()
        if not box:
            return None

        # Add padding
        clip = {
            'x': max(0, box['x'] - padding),
            'y': max(0, box['y'] - padding),
            'width': box['width'] + (padding * 2),
            'height': box['height'] + (padding * 2),
        }

        # Take screenshot of just that region
        page.screenshot(path=output_path, clip=clip)
        print(f"    Element screenshot saved: {output_path}")
        return output_path

    except Exception as e:
        print(f"    Element screenshot error: {e}")
        return None


def take_screenshot(page, name: str = None, save_debug: bool = True,
                   crop_region: str = None, element_selector: str = None) -> str:
    """
    Take screenshot of current page with optional cropping.

    Args:
        page: Playwright page object
        name: Optional name for the screenshot file
        save_debug: If True, save to debug_screenshots folder
        crop_region: Region preset to crop to ('lead_list', 'content_area', 'full')
        element_selector: CSS selector to screenshot just that element

    Returns:
        Path to screenshot file
    """
    if save_debug:
        SCREENSHOT_DIR.mkdir(exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{timestamp}_{name}.png" if name else f"{timestamp}.png"
        path = SCREENSHOT_DIR / filename
    else:
        path = Path(tempfile.mktemp(suffix='.png'))

    # If element selector provided, screenshot just that element
    if element_selector:
        result = crop_to_element(page, element_selector, str(path))
        if result:
            return result
        # Fall back to full screenshot if element not found
        print(f"    Falling back to full screenshot")

    # Take full screenshot
    page.screenshot(path=str(path))
    print(f"    Screenshot saved: {path}")

    # Apply region crop if specified
    if crop_region and crop_region != 'full':
        crop_image(str(path), crop_region)

    return str(path)


def call_vision_model(image_path: str, prompt: str, use_local: bool = True) -> Optional[str]:
    """
    Send screenshot to vision model and get response.

    Args:
        image_path: Path to screenshot image
        prompt: Question/instruction for the vision model
        use_local: If True, try LM Studio first

    Returns:
        Vision model's response text, or None if failed
    """
    with open(image_path, 'rb') as f:
        img_base64 = base64.b64encode(f.read()).decode('utf-8')

    # Try local LM Studio first
    if use_local:
        try:
            print("    Trying local LM Studio...")
            response = requests.post(
                LM_STUDIO_URL,
                json={
                    "messages": [{
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img_base64}"}}
                        ]
                    }],
                    "temperature": 0.2,
                    "max_tokens": 1000
                },
                timeout=60
            )
            if response.status_code == 200:
                result = response.json()['choices'][0]['message']['content']
                print(f"    LM Studio response received")
                return result
        except requests.exceptions.ConnectionError:
            print("    LM Studio not running, trying OpenRouter...")
        except Exception as e:
            print(f"    LM Studio error: {e}")

    # Fall back to OpenRouter
    if not OPENROUTER_API_KEY:
        print("    No OPENROUTER_API_KEY set, vision model unavailable")
        return None

    for model in VISION_MODELS:
        try:
            print(f"    Trying OpenRouter model: {model}")
            response = requests.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                    "HTTP-Referer": "https://planhub-scraper.local",
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
                    "max_tokens": 1000
                },
                timeout=60
            )
            if response.status_code == 200:
                result = response.json()['choices'][0]['message']['content']
                print(f"    OpenRouter response received from {model}")
                return result
            elif response.status_code == 404:
                continue  # Model not available, try next
            else:
                print(f"    OpenRouter error {response.status_code}: {response.text[:200]}")
        except Exception as e:
            print(f"    OpenRouter error with {model}: {e}")
            continue

    print("    All vision models failed")
    return None


# ============================================
# PlanHub-specific prompts
# ============================================

LEAD_LIST_PROMPT = """Analyze this construction project lead list page from PlanHub.

Please identify:
1. How many project/lead items are visible in the list?
2. List the project names you can see (just the names)
3. Is the page fully loaded or still loading? (look for spinners, loading text)
4. Are there any projects with a LOCK icon (indicating they're locked)?

Be concise. Start with the count, then list names."""


PAGE_LOADED_PROMPT = """Is this webpage fully loaded?

Look for:
- Loading spinners or circular progress indicators
- Skeleton loaders or placeholder gray boxes
- "Loading..." text
- Partial/cut-off content

Answer ONLY with one word: LOADED or LOADING"""


IDENTIFY_CLICK_TARGET_PROMPT = """I need to click on a construction project to view its details.

Looking at this page:
1. What text/element should I click to open a project?
2. Where are the clickable project names located?

Describe the element I should click (e.g., "blue text links in the left column")."""


def check_page_loaded(page, use_local: bool = True) -> bool:
    """
    Use vision model to check if page is fully loaded.

    Returns:
        True if page appears loaded, False if still loading
    """
    screenshot_path = take_screenshot(page, "load_check", save_debug=False)
    response = call_vision_model(screenshot_path, PAGE_LOADED_PROMPT, use_local)

    # Clean up temp file
    try:
        Path(screenshot_path).unlink()
    except:
        pass

    if response:
        return "LOADED" in response.upper()
    return True  # Assume loaded if vision fails


def analyze_lead_list(page, use_local: bool = True, save_debug: bool = True,
                      crop: bool = True) -> dict:
    """
    Use vision model to analyze lead list page.

    Args:
        page: Playwright page object
        use_local: Try local LM Studio first
        save_debug: Save screenshot to debug folder
        crop: If True, crop to lead list area (exclude sidebar/header/footer)

    Returns:
        Dict with: lead_count, lead_names, is_loaded, has_locked
    """
    # Take screenshot with optional cropping
    crop_region = 'lead_list' if crop else 'full'
    screenshot_path = take_screenshot(page, "lead_list", save_debug=save_debug,
                                      crop_region=crop_region)
    response = call_vision_model(screenshot_path, LEAD_LIST_PROMPT, use_local)

    result = {
        'lead_count': 0,
        'lead_names': [],
        'is_loaded': True,
        'has_locked': False,
        'raw_response': response
    }

    if response:
        # Try to extract count from response
        import re
        count_match = re.search(r'(\d+)\s*(?:project|lead|item)', response.lower())
        if count_match:
            result['lead_count'] = int(count_match.group(1))

        # Check for loading indicators
        if any(word in response.lower() for word in ['loading', 'spinner', 'progress']):
            result['is_loaded'] = False

        # Check for locked mentions
        if 'lock' in response.lower():
            result['has_locked'] = True

    return result


def wait_for_visual_load(page, max_attempts: int = 5, use_local: bool = True) -> bool:
    """
    Poll vision model until page appears loaded.

    Args:
        page: Playwright page object
        max_attempts: Maximum number of checks
        use_local: Whether to use local LM Studio

    Returns:
        True if page loaded within attempts, False otherwise
    """
    import time

    for attempt in range(max_attempts):
        print(f"    Visual load check {attempt + 1}/{max_attempts}...")
        if check_page_loaded(page, use_local):
            print(f"    Page visually confirmed loaded")
            return True
        time.sleep(2)

    print(f"    Page still loading after {max_attempts} attempts")
    return False


if __name__ == "__main__":
    # Test vision model connectivity
    print("Testing vision model connectivity...")

    # Create a simple test image
    from PIL import Image
    test_path = "/tmp/test_vision.png"
    img = Image.new('RGB', (100, 100), color='white')
    img.save(test_path)

    response = call_vision_model(test_path, "What color is this image?", use_local=True)
    print(f"Response: {response}")

    Path(test_path).unlink()
