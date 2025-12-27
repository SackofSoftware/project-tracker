"""
Division 8 Extraction Configuration
"""
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


def _get_required_env(var_name: str) -> str:
    """Fetch required secrets from the environment to avoid hard-coding keys."""
    value = os.getenv(var_name)
    if not value:
        raise RuntimeError(f"Environment variable {var_name} is required but not set.")
    return value

# Paths
BASE_DIR = Path(__file__).parent.parent.parent
_projects_dir = os.getenv('BIDDING_FOLDER')
if not _projects_dir:
    raise ValueError("BIDDING_FOLDER environment variable not set. Copy .env.example to .env and configure.")
PROJECTS_DIR = Path(_projects_dir)
CHROMA_DIR = BASE_DIR / "static" / "data" / "chroma_db"

# OpenRouter/OpenAI API (keys pulled from environment or .env)
OPENROUTER_API_KEY = _get_required_env("OPENROUTER_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")  # Optional; set if you call OpenAI directly
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

# LLM Model - Using free Amazon Nova Lite (10 calls/min, 1000/day limit)
# Data is logged by Amazon but free for extraction work
# Alternative paid options:
# - "qwen/qwen3-8b" - $0.03/1M input, $0.11/1M output
# - "openai/gpt-4o-mini" - $0.15/$0.60 (reliable but expensive)
LLM_MODEL = os.getenv("DIV8_LLM_MODEL", "amazon/nova-lite-v1")

# Vision Model (for schedule extraction from drawings) - same free model
VISION_MODEL = os.getenv("DIV8_VISION_MODEL", "amazon/nova-lite-v1")

# Embeddings
EMBEDDING_PROVIDER = os.getenv("DIV8_EMBED_PROVIDER", "openrouter")

# Ollama settings (local)
OLLAMA_BASE_URL = "http://localhost:11434"
EMBEDDING_MODEL = "nomic-embed-text"
EMBEDDING_DIM = 768

# OpenRouter embedding settings
OPENROUTER_EMBED_MODEL = os.getenv("DIV8_OPENROUTER_EMBED_MODEL", "intfloat/e5-base-v2")
OPENROUTER_EMBED_URL = "https://openrouter.ai/api/v1/embeddings"

# RAG Settings
CHUNK_SIZE = 5500
CHUNK_OVERLAP = 200
TOP_K_RESULTS = 10
EMBED_BATCH_SIZE = 150
EMBED_TIMEOUT_SECONDS = int(os.getenv("DIV8_EMBED_TIMEOUT", "60"))

# Processing
MAX_WORKERS = 5
BATCH_SIZE = 10

# Division 8 Spec Sections
DIV8_SECTIONS = [
    "08 00 00",  # Openings General
    "08 10 00",  # Doors and Frames
    "08 11 00",  # Metal Doors and Frames
    "08 12 00",  # Metal Frames
    "08 13 00",  # Metal Doors
    "08 14 00",  # Wood Doors
    "08 31 00",  # Access Doors and Panels
    "08 32 00",  # Sliding Glass Doors
    "08 33 00",  # Coiling Doors and Grilles
    "08 34 00",  # Special Function Doors
    "08 36 00",  # Panel Doors
    "08 38 00",  # Traffic Doors
    "08 41 00",  # Entrances and Storefronts
    "08 42 00",  # Entrances
    "08 43 00",  # Storefronts
    "08 44 00",  # Curtain Wall and Glazed Assemblies
    "08 45 00",  # Translucent Wall and Roof Assemblies
    "08 50 00",  # Windows
    "08 51 00",  # Metal Windows
    "08 52 00",  # Wood Windows
    "08 53 00",  # Plastic Windows
    "08 54 00",  # Composite Windows
    "08 55 00",  # Pressure-Resistant Windows
    "08 56 00",  # Special Function Windows
    "08 60 00",  # Roof Windows and Skylights
    "08 70 00",  # Hardware
    "08 71 00",  # Door Hardware
    "08 74 00",  # Access Control Hardware
    "08 75 00",  # Window Hardware
    "08 80 00",  # Glazing
    "08 81 00",  # Glass Glazing
    "08 83 00",  # Mirrors
    "08 84 00",  # Plastic Glazing
    "08 85 00",  # Glazing Accessories
    "08 87 00",  # Glazing Surface Films
    "08 88 00",  # Special Function Glazing
    "08 90 00",  # Louvers and Vents
    "08 91 00",  # Louvers
    "08 92 00",  # Louvered Equipment Enclosures
    "08 95 00",  # Vents
]

# Document type patterns
DOC_PATTERNS = {
    "specs": ["spec", "division", "section", "08"],
    "drawings": ["dwg", "drawing", "plan", "elevation", "detail", "A-", "A0", "A1", "A2"],
    "schedules": ["schedule", "door schedule", "window schedule", "hardware schedule"],
    "addendums": ["addendum", "add ", "add_", "add-"],
    "estimates": ["estimate", "takeoff", "qty", "pricing", "cost"],
    "rfis": ["rfi", "request for information"],
}

# PDF extraction guards
MAX_PDF_SIZE_MB = 0   # 0 = no size-based fallback
MAX_PDF_PAGES = 0     # 0 = all pages
PDFTEXT_FALLBACK_MB = 40  # Force pdftotext for files > 40MB

# Skip large-format drawing sheets (by page dimension in points; letter ~612x792)
DRAWING_SKIP_MAX_DIM_PT = 1200  # Set 0 to disable skipping
