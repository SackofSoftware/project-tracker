# Analysis Tools Reference

This document describes all AI-powered and programmatic analysis tools available for Division 8 construction project analysis.

---

## Table of Contents

1. [Master Analysis Pipeline](#master-analysis-pipeline)
2. [RAG-Based Analysis](#rag-based-analysis)
3. [CSI/Specification Extraction](#csispecification-extraction)
4. [Document Classification](#document-classification)
5. [AI Brief Generation](#ai-brief-generation)
6. [Folder Audit System](#folder-audit-system)
7. [Smart Notes Processing](#smart-notes-processing)
8. [Shape Detection & Annotation](#shape-detection--annotation)
9. [Estimate & Quote Analysis](#estimate--quote-analysis)
10. [API Endpoints Reference](#api-endpoints-reference)

---

## Master Analysis Pipeline

**Location:** `modules/pipeline/master_pipeline.py`
**Type:** AI + Programmatic Hybrid
**API Endpoint:** `POST /api/project/<project_id>/pipeline/run`

The Master Pipeline runs 8 sequential stages on project documents:

### Pipeline Stages

| Stage | Name | Type | Description |
|-------|------|------|-------------|
| 1 | **Rename** | AI | Extract project name from cover sheet using vision AI |
| 2 | **Organize** | Programmatic | Structure files into standard folders (Plans, Specs, Quotes, etc.) |
| 3 | **Split Specs** | Programmatic | Split spec book PDF by CSI section headers |
| 4 | **Split Drawings** | Programmatic | Split drawing set PDF into individual pages |
| 5 | **AI Analysis** | AI | Analyze schedules with GPT-4o-mini + DeepSeek |
| 6 | **Schedule Parse** | AI + Regex | Parse AI results into structured JSON |
| 7 | **Highlight** | Programmatic | Highlight floor plans + exterior elevations |
| 8 | **Quote Analysis** | AI | Identify and parse vendor quote PDFs |

### Stage Details

#### Stage 1: Rename (`stage_rename.py`)
- Uses vision AI to read cover sheet/title block
- Extracts project name, number, location
- Renames project folder to standardized format

#### Stage 2: Organize (`stage_organize.py`)
- Creates standard folder structure:
  ```
  Project Folder/
  ├── Plans/        # Construction drawings
  ├── Specs/        # Specifications
  ├── Addendum/     # Addenda and ASIs
  ├── Quotes/       # Vendor quotes
  ├── Estimates/    # Takeoffs, pricing
  ├── Submittals/   # Product submittals
  ├── RFIs/         # Requests for information
  └── Photos/       # Site photos
  ```
- Classifies files by name patterns and content

#### Stage 3: Split Specs (`stage_split_specs.py`)
- Detects CSI division headers in spec PDF
- Splits into individual section files
- Names files by CSI section number

#### Stage 4: Split Drawings (`stage_split_drawings.py`)
- Extracts individual drawing pages
- Reads sheet number from title block
- Creates organized drawing files

#### Stage 5: AI Analysis (`stage_ai_analysis.py`)
- Identifies schedule pages (doors, windows, hardware)
- Uses DeepSeek for text reasoning
- Uses GPT-4o-mini for vision analysis
- Extracts structured schedule data

#### Stage 6: Schedule Parse (`stage_schedule_parse.py`)
- Converts AI output to structured JSON
- Validates door/window types
- Creates `schedules.json` output

#### Stage 7: Highlight (`stage_highlight.py`)
- Identifies floor plans and elevations
- Creates highlighted PDF copies
- Color-codes by opening type

#### Stage 8: Quote Analysis (`stage_quotes.py`)
- Finds quote/proposal PDFs
- Extracts vendor name, pricing, scope
- Creates `quotes_summary.json`

### AI Providers

**File:** `modules/pipeline/ai_providers.py`

```python
AIProviderManager:
    - Vision: GPT-4o-mini (OpenAI) - for image/PDF analysis
    - Reasoning: DeepSeek (OpenRouter) - for text analysis
    - Fallback: LM Studio (localhost:1234)
```

---

## RAG-Based Analysis

**Location:** `modules/rag/division8_rag.py`
**Type:** AI (RAG)
**API Endpoint:** `GET /api/project/<project_id>/rag-analysis`

### Overview

Uses Retrieval-Augmented Generation to extract Division 8 scope:

1. **Chunk** - Split documents into semantic chunks
2. **Embed** - Create embeddings with OpenAI `text-embedding-3-small`
3. **Store** - Index in ChromaDB (local vector database)
4. **Query** - Retrieve relevant chunks for Division 8 questions
5. **Generate** - Use GPT-4o-mini to create structured output

### Output Schema

```json
{
  "project_summary": {
    "name": "Project Name",
    "location": "City, State",
    "type": "new construction | renovation"
  },
  "windows": {
    "specified": true,
    "types": ["double hung", "awning", "fixed"],
    "manufacturers": ["Pella", "Andersen"],
    "count_estimate": "~150 windows",
    "performance_specs": {
      "u_factor": "0.30",
      "shgc": "0.25"
    }
  },
  "doors": {
    "metal_doors": {
      "specified": true,
      "types": ["hollow metal", "aluminum"],
      "count_estimate": "~45 doors"
    },
    "wood_doors_excluded": {
      "present_in_project": true,
      "note": "Wood doors by Division 6"
    }
  },
  "hardware": {
    "manufacturers": ["Schlage", "Von Duprin"],
    "lockset_types": ["mortise", "cylindrical"]
  },
  "storefront_curtainwall": {
    "specified": true,
    "systems": ["aluminum storefront"],
    "manufacturers": ["Kawneer", "Oldcastle"]
  }
}
```

### Local RAG Alternative

**File:** `modules/rag/division8_rag_local.py`

Uses Ollama embeddings for fully offline operation:
- Model: `nomic-embed-text`
- Inference: LM Studio or Ollama

---

## CSI/Specification Extraction

**Location:** `modules/doc_classification/division_extractor.py`
**Type:** Programmatic + AI
**API Endpoint:** `GET /api/project/<project_id>/scope/division8`

### Programmatic Extraction

Parses specification PDFs to extract CSI sections:

```python
# Regex patterns used
DIVISION_HEADER_RE = r"DIVISION\s+(\d{2})\s+[-–]\s+(.+)"
SECTION_HEADER_RE = r"SECTION\s+(\d{2}\s+\d{2}\s+\d{2})(.*)"
```

### Extracted Data

- Division 08 sections (08 00 00 - 08 99 00)
- Section titles and page ranges
- Text excerpts for each section

### CSI Service

**File:** `modules/csi/csi_service.py`

Provides CSI Masterformat data:
- Section lookups by code
- Manufacturer database matching
- Division 8 section list

### API Endpoints

```
GET  /api/csi/stats                    - CSI database stats
GET  /api/csi/section/<section_id>     - Section info lookup
GET  /api/csi/sections/division8       - All Division 8 sections
POST /api/csi/enrich                   - Enrich scope with CSI descriptions
POST /api/csi/manufacturers            - Find manufacturer references
GET  /api/project/<id>/csi-analysis    - Run CSI analysis on project
POST /api/project/<id>/auto-tag        - Auto-generate CSI tags
```

---

## Document Classification

**Location:** `modules/doc_classification/`
**Type:** Programmatic + AI

### Drawing Discipline Identifier

**File:** `drawing_discipline_identifier.py`

Classifies drawings by discipline code:

| Code | Discipline |
|------|------------|
| A | Architectural |
| S | Structural |
| M | Mechanical |
| E | Electrical |
| P | Plumbing |
| FP | Fire Protection |
| L | Landscape |
| C | Civil |

### Division Pipeline

**File:** `division_pipeline.py`

Orchestrates document classification:
1. Identifies spec vs drawings
2. Extracts CSI divisions from specs
3. Classifies drawing sheets
4. Creates document manifest

### Vision Analyzer

**File:** `vision_analyzer.py`

Uses AI vision to analyze PDFs:
- Title block extraction
- Schedule detection
- Drawing type identification

---

## AI Brief Generation

**Location:** `modules/brief/prompt_builder.py`
**Type:** AI
**API Endpoint:** `GET /api/project/<project_id>/brief`

### Overview

Generates comprehensive project briefs using LLM:

1. **Gather Context** - Collect all available project data
2. **Build Prompt** - Create structured prompt with context
3. **Generate** - Call LLM for brief generation
4. **Format** - Return as JSON or plain text

### Context Sources

- Project metadata (name, owner, architect, dates)
- Division 8 scope from specifications
- Window/door schedules from extracted data
- Drawing classifications
- Estimate status
- Vendor quotes summary

### AI Provider Priority

1. LM Studio (localhost:1234) - if available
2. OpenRouter (amazon/nova-lite-v1) - if API key set
3. Simple text brief - fallback

### Query Parameters

```
GET /api/project/<id>/brief
    ?format=json|text           # Response format
    ?use_lm_studio=true|false   # Try local LLM first
    ?force_openrouter=true      # Skip LM Studio
```

---

## Folder Audit System

**Location:** `modules/audit/folder_auditor.py`
**Type:** AI + Programmatic
**API Endpoint:** `GET /api/project/<project_id>/audit`

### Features

- **Structure Analysis** - Compare to ideal folder structure
- **Duplicate Detection** - MD5 hash-based file deduplication
- **Misplaced Files** - Identify files in wrong folders
- **AI Recommendations** - GPT suggestions for organization

### Ideal Structure

```python
IDEAL_STRUCTURE = {
    "Plans": "Construction drawings, floor plans, elevations, details",
    "Specs": "Project specifications, Division 8 sections",
    "Addendum": "Addenda and ASIs",
    "Quotes": "Vendor quotes and proposals",
    "Estimates": "Takeoffs, pricing spreadsheets",
    "Submittals": "Product submittals and shop drawings",
    "RFIs": "Requests for information",
    "Photos": "Site photos",
}
```

### File Pattern Detection

```python
FILE_PATTERNS = {
    "drawings": ["A-", "A0", "A1", "plan", "elevation", "detail"],
    "specs": ["spec", "division", "section 08"],
    "addendum": ["addendum", "asi", "bulletin"],
    "quote": ["quote", "proposal", "pricing", "bid"],
    "schedule": ["schedule", "door schedule", "window schedule"],
}
```

---

## Smart Notes Processing

**Location:** `modules/notes/smart_notes.py`
**Type:** AI
**API Endpoint:** `POST /api/notes/<project_id>/smart`

### Features

- Parse free-form notes with AI
- Extract structured data (dates, amounts, contacts)
- Classify document types
- Suggest actions based on content

### Document Type Detection

```python
DOC_PATTERNS = {
    'quote': [r'quot', r'proposal', r'price'],
    'addendum': [r'addend', r'revision', r'change\s*order'],
    'rfi': [r'rfi', r'request\s*for\s*information'],
    'submittal': [r'submittal', r'shop\s*drawing'],
    'spec': [r'specification', r'section\s*\d{5,6}'],
}
```

---

## Shape Detection & Annotation

**Location:** `modules/files/shape_detector.py`
**Type:** Programmatic (Computer Vision)
**API Endpoint:** `POST /api/project/<project_id>/detect-shapes`

### Shape Types Detected

| Shape | Use Case |
|-------|----------|
| Hexagon | Window/door tags |
| Circle | Elevation markers |
| Rectangle | Detail callouts |
| Diamond | Key notes |
| Triangle | Section markers |

### Technology Stack

- **PyMuPDF (fitz)** - PDF rendering
- **OpenCV** - Shape detection
- **NumPy** - Image processing

### Detection Parameters

```python
SHAPE_PARAMS = {
    ShapeType.HEXAGON: {
        'vertices': 6,
        'min_area': 200,
        'max_area': 8000,
        'aspect_range': (0.7, 1.4)
    },
    ShapeType.CIRCLE: {
        'vertices': (8, 20),  # Range for approximation
        'circularity': 0.8
    }
}
```

### Annotation Storage

Annotations stored in SQLite database:
- Project ID
- PDF path and page
- Shape type and coordinates
- Type label (A, B, C, etc.)
- Category (window, door, storefront, curtainwall)

---

## Estimate & Quote Analysis

### Estimate Reader

**Location:** `modules/estimates/estimate_reader.py`
**Type:** Programmatic
**API Endpoint:** `GET /api/estimate/<project_id>/openings`

Reads Excel estimate spreadsheets:
- Parses takeoff quantities
- Extracts opening types and counts
- Identifies material specifications

### Quote Reader

**Location:** `modules/quotes/quote_reader.py`
**Type:** AI + Programmatic
**API Endpoint:** `GET /api/quotes/<project_id>`

Analyzes vendor quote PDFs:
- Extracts vendor information
- Parses line items and pricing
- Identifies material types
- Creates comparison matrix

### Quote Comparison

**Endpoint:** `GET /api/quotes/<project_id>/compare`

Compares vendor quotes against estimate data:
- Identifies discrepancies
- Flags missing items
- Highlights pricing differences

---

## API Endpoints Reference

### Pipeline Endpoints

```
POST /api/project/<id>/pipeline/run              - Start full pipeline
GET  /api/project/<id>/pipeline/status           - Get pipeline status
POST /api/project/<id>/pipeline/stage/<name>/rerun - Re-run single stage
GET  /api/projects/needing-pipeline              - Projects needing analysis
```

### Extraction Endpoints

```
POST /api/extract/<id>                           - Start RAG extraction
GET  /api/extract/<id>/status                    - Extraction status
GET  /api/extract/<id>/result                    - Get extraction result
```

### Scope Analysis Endpoints

```
GET  /api/project/<id>/scope/division8           - Division 8 scope (sync)
POST /api/project/<id>/scope/division8/analyze   - Division 8 scope (async)
GET  /api/project/<id>/scope/division8/status    - Async status
GET  /api/project/<id>/scope/division8/result    - Async result
GET  /api/project/<id>/scope/drawings            - Drawing disciplines
GET  /api/project/<id>/scope/full                - Combined scope analysis
```

### RAG Endpoints

```
GET  /api/project/<id>/rag-analysis              - Get RAG analysis
GET  /api/project/<id>/rag-status                - RAG status check
POST /api/project/<id>/trigger-rag               - Trigger RAG analysis
GET  /api/rag/projects                           - Projects with RAG data
```

### CSI Endpoints

```
GET  /api/csi/stats                              - CSI database stats
GET  /api/csi/section/<section_id>               - Section lookup
GET  /api/csi/sections/division8                 - Division 8 sections
POST /api/csi/enrich                             - Enrich with CSI
POST /api/csi/manufacturers                      - Find manufacturers
GET  /api/project/<id>/csi-analysis              - Project CSI analysis
POST /api/project/<id>/auto-tag                  - Auto-generate tags
GET  /api/project/<id>/csi-tags                  - Get project tags
POST /api/project/<id>/csi-tags                  - Set project tags
```

### Audit Endpoints

```
GET  /api/project/<id>/audit                     - Full audit with AI
GET  /api/project/<id>/audit/quick               - Quick audit (no AI)
GET  /api/audit/cross-project-duplicates         - Find duplicates
```

### Brief Endpoints

```
GET  /api/project/<id>/brief                     - Generate AI brief
```

### Annotation Endpoints

```
GET  /api/project/<id>/annotations               - Get annotations
POST /api/project/<id>/annotations               - Create annotation
PUT  /api/project/<id>/annotations/<ann_id>      - Update annotation
DELETE /api/project/<id>/annotations/<ann_id>    - Delete annotation
POST /api/project/<id>/detect-shapes             - Auto-detect shapes
POST /api/project/<id>/annotations/bulk          - Bulk create
GET  /api/project/<id>/annotations/summary       - Annotation summary
```

### Estimate/Quote Endpoints

```
GET  /api/estimate/<id>/openings                 - Estimate data
GET  /api/quotes/<id>                            - Quote data
GET  /api/quotes/<id>/compare                    - Quote comparison
```

---

## Environment Variables

Required for AI features:

```bash
# OpenAI (for embeddings and vision)
OPENAI_API_KEY=sk-...

# OpenRouter (for DeepSeek and free models)
OPENROUTER_API_KEY=sk-or-...

# Local LLM (optional)
# LM Studio runs at localhost:1234 by default
```

---

## Dependencies

### Core

- Flask
- SQLAlchemy
- pdfplumber
- PyMuPDF (fitz)

### AI/ML

- openai
- chromadb
- requests (for OpenRouter)

### Computer Vision

- opencv-python
- numpy
- Pillow

### Document Processing

- python-docx
- openpyxl
