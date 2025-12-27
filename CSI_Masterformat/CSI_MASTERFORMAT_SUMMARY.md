# CSI MasterFormat Data Assets Summary

**Generated:** December 8, 2025
**Purpose:** Comprehensive reference for all CSI MasterFormat data and resources
**Version:** 1.0

---

## Table of Contents

1. [Overview: What is CSI MasterFormat](#overview-what-is-csi-masterformat)
2. [Data Assets Inventory](#data-assets-inventory)
3. [JSON Schema Documentation](#json-schema-documentation)
4. [Scripts and Tools](#scripts-and-tools)
5. [Division 8 Specific Resources](#division-8-specific-resources)
6. [How to Use These Resources](#how-to-use-these-resources)
7. [Integration Examples](#integration-examples)

---

## Overview: What is CSI MasterFormat

**CSI MasterFormat** is the standard taxonomy for organizing construction specifications and cost estimating in North America. Published by the Construction Specifications Institute (CSI), it provides a hierarchical structure for categorizing construction work into divisions and sections.

### Key Characteristics

- **50 Divisions**: Organized into numbered divisions (00-49)
- **6-Digit Section Numbers**: Format XX XX XX (Division-Level-Detail)
- **Hierarchical Structure**: Division > Group > Section > Subsection
- **Industry Standard**: Used in specifications, cost estimating, and project management

### Version

Your data is based on **MasterFormat 2018**, the most current version widely adopted in the construction industry.

### Division Organization

```
00: Procurement & Contracting Requirements
01: General Requirements
02-19: Building Construction
  02: Existing Conditions
  03: Concrete
  04: Masonry
  05: Metals
  06: Wood, Plastics, Composites
  07: Thermal and Moisture Protection
  08: Openings (DOORS, WINDOWS, GLAZING)
  09: Finishes
  10-14: Specialties through Conveying
21-29: Facility Services (MEP)
31-35: Site and Infrastructure
40-49: Process Equipment
```

---

## Data Assets Inventory

### 1. Primary MasterFormat Database

**Location:** `/Users/andrewhawes/NEECS Dropbox/Andrew Hawes/Python/Masterformat_ Breakdown/`

| Asset | Description | Size | Format |
|-------|-------------|------|--------|
| **masterformat_combined_20250806_101743.json** | Combined master database with all divisions and sections | 44 KB | JSON |
| **Masterformat2018 [1-557].pdf** | 557 individual PDF pages from MasterFormat 2018 | ~52 MB total | PDF |
| **Divisions/** | 35 consolidated division PDFs | ~7.5 MB | PDF |

**Content Coverage:**
- 4 total records (pages) in combined JSON
- 3 pages with structured data
- Average content length: 1,729 characters per page
- Extracted using: granite3-moe:3b and qwen3:8b models

### 2. Division-Specific PDFs

**Location:** `/Users/andrewhawes/NEECS Dropbox/Andrew Hawes/Python/Masterformat_ Breakdown/Divisions/`

| Division | Filename | Size | Sections |
|----------|----------|------|----------|
| 01 | Masterformat Division 01.pdf | 308 KB | General Requirements |
| 02 | Masterformat Division 02.pdf | 196 KB | Existing Conditions |
| 03 | Masterformat Division 03.pdf | 181 KB | Concrete |
| 04 | Masterformat Division 04.pdf | 174 KB | Masonry |
| 05 | Masterformat Division 05.pdf | 185 KB | Metals |
| 06 | Masterformat Division 06.pdf | 178 KB | Wood, Plastics |
| 07 | Masterformat Division 07.pdf | 254 KB | Thermal/Moisture |
| **08** | **Masterformat Division 08.pdf** | **266 KB** | **Openings** |
| 09 | Masterformat Division 09.pdf | 283 KB | Finishes |
| 10-14 | Various | 141-223 KB | Specialties |
| 21-28 | Various | 162-295 KB | MEP Systems |
| 31-35 | Various | 192-380 KB | Site/Infrastructure |
| 40-48 | Various | 154-298 KB | Process Equipment |

**Note:** Not all divisions 1-49 are present. Only divisions with active sections in MasterFormat 2018 are included.

### 3. Backup Archives

**Location:** `/Users/andrewhawes/NEECS Dropbox/Andrew Hawes/Python/Masterformat_ Breakdown/backups/`

- **18 automatic backups** from processing sessions
- Timestamped with page counts (5, 10, 15, 20+ pages)
- Date range: August 6, 2025
- Format: JSON with metadata

### 4. Division 8 Training Data

**Location:** `/Users/andrewhawes/NEECS Dropbox/Andrew Hawes/Python/project-tracker/CSI_Masterformat/division8_data/`

| File | Purpose | Status |
|------|---------|--------|
| division8_train.jsonl | Training dataset for Division 8 AI models | Empty (ready for data) |
| division8_test.jsonl | Test dataset for model evaluation | Empty (ready for data) |
| division8_unified_training.jsonl | Combined training/test data | Empty (ready for data) |

**Intended Use:** Fine-tuning AI models for Division 8 (Openings) specification analysis.

---

## JSON Schema Documentation

### Combined MasterFormat JSON Structure

The primary database uses a nested structure optimized for AI extraction and querying.

#### Root Schema

```json
{
  "export_info": {
    "export_timestamp": "ISO 8601 timestamp",
    "total_pages": "integer",
    "page_range": {
      "first": "integer",
      "last": "integer"
    },
    "model_used": "string (AI model identifier)",
    "data_integrity": {
      "total_records": "integer",
      "pages_with_structured_data": "integer",
      "average_content_length": "float"
    }
  },
  "data": [
    // Array of page objects
  ]
}
```

#### Page Object Schema

```json
{
  "metadata": {
    "page_number": "integer",
    "source_file": "string (PDF filename)",
    "model": "string (extraction model)",
    "timestamp": "ISO 8601 timestamp",
    "extraction_date": "YYYY-MM-DD",
    "content_length": "integer (characters)",
    "has_previous_context": "boolean",
    "save_attempt_count": "integer"
  },
  "raw_content": "string (extracted text)",
  "response_text": "string (model's JSON response)",
  "structured": {
    // Parsed structured data
  }
}
```

#### Structured Data Schema

```json
{
  "page_info": {
    "page_number": "integer",
    "has_spillover_from_previous": "boolean",
    "has_spillover_to_next": "boolean"
  },
  "sections": [
    {
      "section_number": "string (XX XX XX format)",
      "title": "string",
      "division": "string (2-digit)",
      "level": "integer (hierarchy depth)",
      "status": "string (complete|partial|continued)",
      "content": {
        "includes": ["array of strings"],
        "may_include": ["array of strings"],
        "alternate_terms": ["array of strings"],
        "see": ["array of cross-references"]
      },
      "cross_references": {
        "see": ["array of related sections"],
        "see_also": ["array of additional references"]
      },
      "sub_sections": [
        {
          "section_number": "string",
          "title": "string"
        }
      ],
      "raw_text": "string (original section text)"
    }
  ]
}
```

### Section Number Format

CSI MasterFormat uses a **6-digit hierarchical numbering system**:

```
XX XX XX
│  │  └─ Detail level (specific type)
│  └──── Group level (category)
└─────── Division (major category)
```

**Examples:**
- `08 00 00` - Division 08: Openings (top level)
- `08 11 00` - Metal Doors and Frames (group)
- `08 11 13` - Hollow Metal Doors and Frames (specific section)
- `08 44 13` - Glazed Aluminum Curtain Walls (specific section)

### Field Definitions

| Field | Type | Description | Example |
|-------|------|-------------|---------|
| **section_number** | string | CSI 6-digit code with spaces | "08 44 13" |
| **title** | string | Official section title | "Glazed Aluminum Curtain Walls" |
| **division** | string | 2-digit division code | "08" |
| **level** | integer | Hierarchy depth (1=division, 2=group, 3=section) | 3 |
| **status** | enum | Extraction completeness | "complete", "partial", "continued" |
| **includes** | array | Core scope of section | ["description of...", "requirements for..."] |
| **may_include** | array | Optional content | ["list of products...", "owner-furnished..."] |
| **alternate_terms** | array | Synonyms and abbreviations | ["procurement contract", "purchase order"] |
| **see** | array | Primary cross-references | ["00 24 00 for procurement scopes"] |
| **see_also** | array | Related references | ["Division 07 for waterproofing"] |
| **cross_references** | object | Organized reference links | {see: [...], see_also: [...]} |
| **sub_sections** | array | Child sections | [{section_number, title}, ...] |

---

## Scripts and Tools

### 1. MasterFormat Processor (Primary Tool)

**Location:** `/Users/andrewhawes/NEECS Dropbox/Andrew Hawes/Python/Masterformat_ Breakdown/masterformat_processor.py`

**Purpose:** Batch processing of MasterFormat PDFs with AI extraction

**Features:**
- GUI application (Tkinter)
- Ollama AI integration
- Multiple processing modes: Per Page, Whole File, Chunked
- Context window management (4K-128K tokens)
- JSON extraction with format validation
- Automatic backups every 5 pages
- Progress tracking and pause/resume

**Technology Stack:**
- **AI Server:** Ollama (http://10.0.0.36:11434)
- **Models:** qwen3:8b, granite3-moe:3b
- **PDF Parsing:** PyPDF2
- **Context Management:** Dynamic token budgeting

**Key Configuration:**

```python
# Context Presets
CONTEXT_PRESETS = [4096, 8192, 16384, 24000, 32000, 40000, 64000, 128000]

# Processing Modes
PROCESSING_MODES = ["Per Page", "Whole File", "Chunked"]

# JSON Modes
json_mode = "prompt_only"  # Alternative: "api_format"

# Token Budget
context_tokens = 8192          # Total context window
output_tokens = 3000           # Reserved for response
prompt_overhead_tokens = 1000  # System prompt overhead
safety_percent = 25            # Buffer percentage
```

**Usage:**

```bash
# Run the GUI processor
python3 masterformat_processor.py
```

The interface provides:
- Server URL configuration
- Model selection
- Processing mode toggle
- Context window adjustment
- Real-time progress monitoring
- Export/import capabilities

### 2. Division 08 Analyzer

**Location:** Multiple systems for Division 8 analysis

#### Bidding System
**Path:** `/Users/andrewhawes/NEECS Dropbox/Andrew Hawes/Python/Bidding/`

- **division_08_analyzer.py** - Core Division 08 scope extraction
- **orchestrate_project.py** - Multi-agent coordination
- **rag_document_parser.py** - ChromaDB + Ollama embeddings

#### Analysis Agents
**Path:** `/Users/andrewhawes/NEECS Dropbox/Andrew Hawes/Python/Bidding/agents/`

- **spec_analyzer_agent.py** - CSI section extraction from specifications
- **drawing_analyzer_agent.py** - Door/window schedule extraction
- **admin_doc_processor_agent.py** - Project metadata extraction

**Usage:**

```bash
# Full project analysis
cd /Users/andrewhawes/NEECS\ Dropbox/Andrew\ Hawes/Python/Bidding/
python3 orchestrate_project.py --project-path /path/to/bid --project-name "ProjectName"

# Individual agent execution
python3 agents/spec_analyzer_agent.py
python3 agents/drawing_analyzer_agent.py
```

### 3. Specification Processing Tools

#### Unified Spec Processor
**Location:** `/Users/andrewhawes/NEECS Dropbox/Andrew Hawes/Python/Spec_Book_Splitter/unified_spec_processor.py`

**Capabilities:**
- Splits PDF specifications by CSI section
- Extracts Division 08 sections automatically
- Handles multi-division specification books
- Preserves formatting and cross-references

#### Division Extractor
**Location:** `/Users/andrewhawes/NEECS Dropbox/Andrew Hawes/Python/construction_doc_summarizer/src/.../specs/division_extractor.py`

**Features:**
- Pattern matching for CSI section numbers
- Division-level aggregation
- Support for non-standard formatting

**CSI Section Detection Patterns:**

```python
section_patterns = [
    r'^(SECTION\s+\d{2}\s*\d{2}\s*\d{2}.*)',     # SECTION 08 80 00
    r'^(DIVISION\s+\d{1,2}.*)',                   # DIVISION 8
    r'^(PART\s+[123]\s*[-:]?\s*\w+.*)',          # PART 1 - GENERAL
    r'^(\d+\.\d+\s+[A-Z].*)',                     # 1.1 SUMMARY
    r'^([A-Z]{2,}\s+[A-Z].*)'                     # SUBMITTALS
]
```

### 4. Product Specification Extractor

**Location:** `/Users/andrewhawes/NEECS Dropbox/Andrew Hawes/Python/Job_Extraction/product_spec_extractor.py`

**Extracts 40+ fields:**
- Manufacturer name and contact info
- Product lines and model numbers
- Performance specifications (U-factor, SHGC, STC)
- Material types and finishes
- Hardware requirements
- Installation requirements

**Output:** Structured JSON with confidence scores

### 5. Domain Indexer Template

**Location:** `/Users/andrewhawes/NEECS Dropbox/Andrew Hawes/Python/Division 8 Product Guide/scripts/domain_indexer_template.py`

**Purpose:** Creates fine-tuned AI models for specification analysis

**Features:**
- Subsection filtering with regex patterns
- Question/answer pair generation
- JSONL export for model training
- Domain-specific configuration
- Quality assurance scoring

**Usage:**

```bash
# Create spec analysis configuration
python3 domain_indexer_template.py \
  --create-config spec_analysis_config.json \
  --domain-name "Specification Analysis"

# Launch with configuration
python3 domain_indexer_template.py --config spec_analysis_config.json
```

**Recommended Filters for MasterFormat:**

1. **Cross-References Filter**
   - Include: "refer to", "see section", "coordinate with"
   - Exclude: "warranty", "contact information"
   - Length: 50-1500 characters

2. **Standards and Codes Filter**
   - Include: "ASTM", "ANSI", "AAMA", "IGMA", "IBC"
   - Exclude: "warranty", "contact"
   - Length: 30-1000 characters

3. **Manufacturer Filter**
   - Include: "manufacturer", "model", "basis of design", "or equal"
   - Exclude: "warranty", "maintenance"
   - Length: 100-2000 characters

### 6. QwenD8 RAG System

**Location:** `/Users/andrewhawes/NEECS Dropbox/Andrew Hawes/Python/Division 8 Product Guide/scripts/qwend8_rag_tool.py`

**Purpose:** Query manufacturer specifications and technical documents

**Database:**
- **4,965 indexed documents** from glass/glazing manufacturers
- FAISS vector store for semantic search
- Metadata tracking for source attribution

**Usage:**

```bash
# Single query
python3 qwend8_rag_tool.py --query "aluminum storefront thermal break requirements" --docs 5

# Interactive mode
./qwend8
```

---

## Division 8 Specific Resources

### Overview

Division 08 - **Openings** is the focus of your construction document analysis system, covering:
- Doors and frames
- Windows
- Entrances and storefronts
- Curtain walls
- Hardware
- Glazing and mirrors

### CSI Sections Covered

#### Included in Scope

| Section | Title | Priority |
|---------|-------|----------|
| 08 11 13 | Hollow Metal Doors and Frames | High |
| 08 12 16 | Aluminum Doors and Frames | High |
| 08 21 13 | Plastic Doors | Medium |
| 08 31 13 | Access Doors | Medium |
| 08 41 13 | Aluminum-Framed Entrances and Storefronts | **Critical** |
| 08 42 13 | Sliding Aluminum-Framed Entrances | High |
| 08 43 13 | Revolving Door Entrances | Medium |
| 08 44 13 | Glazed Aluminum Curtain Walls | **Critical** |
| 08 51 13 | Metal Windows | High |
| 08 52 13 | Aluminum Windows | **Critical** |
| 08 53 13 | Vinyl Windows | High |
| 08 71 00 | Door Hardware | High |
| 08 80 00 | Glazing | **Critical** |
| 08 83 00 | Mirrors | Low |

#### Excluded from Scope

| Section | Title | Reason |
|---------|-------|--------|
| 08 14 16 | Flush Wood Doors | Not glazing contractor scope |
| 08 28 13 | Overhead Coiling Doors | Specialty door contractor |
| 08 33 13 | Rolling Doors | Specialty door contractor |

### Spec Book Analysis Guide

**Location:** `/Users/andrewhawes/NEECS Dropbox/Andrew Hawes/Division 8 Product Guide/SPEC_BOOK_ANALYSIS_GUIDE.md`

**Purpose:** Training guide for creating AI models that understand specification structure rather than just content.

**Key Topics:**
- Structural element recognition (section numbering, cross-references)
- Content pattern identification (submittals, quality assurance)
- Standards citation extraction (ASTM, ANSI, AAMA, IGMA)
- Manufacturer integration patterns
- Document navigation and coordination

**Sample Training Q&A Patterns:**

```
Structure Analysis:
Q: What organizational structure does Section 08 80 00 follow?
A: CSI 3-part format - Part 1 (General), Part 2 (Products), Part 3 (Execution)

Cross-Reference Mapping:
Q: What other sections does this glazing specification reference?
A: Section 08 10 00 for window frames, structural drawings for rough openings

Standards Identification:
Q: What testing standards are specified?
A: ASTM E283 (air infiltration), IGMA standards (durability), ASTM E2190 (IGU performance)

Manufacturer Analysis:
Q: How are manufacturers specified?
A: Guardian Glass as basis-of-design, with Pilkington and Vitro as approved equals
```

### Division 8 Analysis System

**Primary Files:**

| Component | Location | Function |
|-----------|----------|----------|
| Main Analyzer | `Bidding/division_08_analyzer.py` | Division 08 scope extraction |
| Orchestrator | `Bidding/orchestrate_project.py` | Multi-agent coordination |
| Spec Agent | `Bidding/agents/spec_analyzer_agent.py` | CSI section identification |
| Drawing Agent | `Bidding/agents/drawing_analyzer_agent.py` | Schedule extraction from drawings |
| Admin Agent | `Bidding/agents/admin_doc_processor_agent.py` | Project metadata |

**Technology Stack:**

| Component | Technology | Purpose |
|-----------|-----------|---------|
| Vector Store | ChromaDB | Document embeddings and retrieval |
| Embeddings | mxbai-embed-large (Ollama) | Semantic search |
| Vision AI | Pixtral-12B (OpenRouter) | Schedule extraction from drawings |
| Local Vision | Qwen3-VL (LM Studio) | Offline OCR processing |
| Analysis | DeepSeek (OpenRouter) | Drawing interpretation |

**Output Format:**

```json
{
  "project_name": "string",
  "division_08_sections": [
    {
      "section_number": "08 44 13",
      "title": "Glazed Aluminum Curtain Walls",
      "specification_location": "page reference",
      "manufacturers": ["Kawneer", "YKK AP"],
      "performance_requirements": {
        "wind_load": "value + units",
        "u_factor": "value",
        "shgc": "value"
      },
      "quantities": {
        "area": "value + units",
        "linear_feet": "value + units"
      },
      "confidence_score": 0.95
    }
  ],
  "drawings_analyzed": {
    "door_schedules": ["list of marks"],
    "window_schedules": ["list of types"],
    "hardware_sets": ["list of groups"]
  }
}
```

### Manufacturer Database

**Location:** `/Users/andrewhawes/NEECS Dropbox/Andrew Hawes/Python/Division 8 Product Guide/`

**Assets:**

| Resource | Description | Count |
|----------|-------------|-------|
| Product List/ | Manufacturer product catalogs | 175 files |
| Glass Vendors/ | Glass manufacturer datasheets | 25 vendors |
| Window Manufacturers/ | Window system specifications | 21 manufacturers |
| Hardware/ | Door hardware specifications | Multiple manufacturers |

**FAISS Index:**
- **4,965 documents** indexed
- Semantic search capability
- Source attribution for citations
- File: `scripts/faiss.index` + `index_metadata.jsonl`

**Query System:**

```bash
# Search manufacturer specs
cd "Division 8 Product Guide/scripts"
python3 qwend8_rag_tool.py --query "thermal break requirements"
```

### Training Data Assets

**Location:** `/Users/andrewhawes/NEECS Dropbox/Andrew Hawes/Python/FineTune/training-data/Cleaned_Subsections/`

| Section | Files | Purpose |
|---------|-------|---------|
| 084113_*.json | Storefront training data | AI model fine-tuning |
| 085213_*.json | Windows training data | AI model fine-tuning |
| 087100_*.json | Hardware training data | AI model fine-tuning |
| 088000_*.json | Glazing training data | AI model fine-tuning |

**Format:** Question/answer pairs for instruction fine-tuning

---

## How to Use These Resources

### Use Case 1: Look Up a CSI Section

**Goal:** Find the official definition and scope of a CSI section

**Method:**

```bash
# 1. Open the combined JSON database
file="/Users/andrewhawes/NEECS Dropbox/Andrew Hawes/Python/Masterformat_ Breakdown/masterformat_combined_20250806_101743.json"

# 2. Search for section number (e.g., 08 44 13)
jq '.data[] | select(.structured.sections[]?.section_number == "08 44 13")' "$file"

# 3. Or search by title keyword
jq '.data[] | select(.structured.sections[]?.title | contains("Curtain Wall"))' "$file"
```

**Alternative:** Use the PDF for browsing

```bash
# Open Division 08 PDF
open "/Users/andrewhawes/NEECS Dropbox/Andrew Hawes/Python/Masterformat_ Breakdown/Divisions/Masterformat Division 08.pdf"
```

### Use Case 2: Extract Division 08 from a Specification Book

**Goal:** Parse a project specification PDF and extract only Division 08 sections

**Method:**

```bash
cd "/Users/andrewhawes/NEECS Dropbox/Andrew Hawes/Python/Spec_Book_Splitter"

# Process spec book and extract Division 08
python3 unified_spec_processor.py \
  --input "/path/to/project_specs.pdf" \
  --output "/path/to/output/folder" \
  --division 08

# Output: Individual PDF files for each 08 XX XX section found
```

### Use Case 3: Analyze a Complete Bid Package

**Goal:** Extract all Division 08 scope, quantities, and requirements from bid documents

**Method:**

```bash
cd "/Users/andrewhawes/NEECS Dropbox/Andrew Hawes/Python/Bidding"

# Run full multi-agent analysis
python3 orchestrate_project.py \
  --project-path "/path/to/bid/documents" \
  --project-name "Example Office Building"

# Output: Combined_Bidding_Project_FINAL_ANALYSIS.json
```

**The orchestrator will:**
1. Parse specifications for Division 08 sections
2. Extract schedules from architectural drawings
3. Identify manufacturers and performance requirements
4. Estimate quantities
5. Flag missing information or conflicts
6. Generate structured JSON output

### Use Case 4: Query Manufacturer Specifications

**Goal:** Find technical information about specific products or systems

**Method:**

```bash
cd "/Users/andrewhawes/NEECS Dropbox/Andrew Hawes/Division 8 Product Guide"

# Interactive query mode
./qwend8

# Or single query
python3 scripts/qwend8_rag_tool.py \
  --query "What are the thermal performance requirements for Kawneer 1600 storefront?" \
  --docs 5

# Output includes:
# - AI-generated answer
# - Source document citations
# - Relevance scores
```

### Use Case 5: Create Training Data for AI Models

**Goal:** Generate question/answer pairs for fine-tuning an AI model on MasterFormat structure

**Method:**

```bash
cd "/Users/andrewhawes/NEECS Dropbox/Andrew Hawes/Division 8 Product Guide/scripts"

# 1. Create domain configuration
python3 domain_indexer_template.py \
  --create-config masterformat_config.json \
  --domain-name "CSI MasterFormat Analysis"

# 2. Launch GUI and configure filters
python3 domain_indexer_template.py --config masterformat_config.json

# 3. Process MasterFormat PDFs
# - Add subsection filters (cross-references, standards, manufacturers)
# - Generate Q&A pairs
# - Export as JSONL

# 4. Export training data
# Output: masterformat_training.jsonl (ready for fine-tuning)
```

### Use Case 6: Process Individual PDFs with AI

**Goal:** Extract structured data from a single MasterFormat PDF page

**Method:**

```bash
cd "/Users/andrewhawes/NEECS Dropbox/Andrew Hawes/Python/Masterformat_ Breakdown"

# Launch the GUI processor
python3 masterformat_processor.py

# In GUI:
# 1. Select PDF file (e.g., Masterformat2018 100.pdf)
# 2. Choose processing mode: "Per Page"
# 3. Set context window: 8192 tokens
# 4. Click "Process Pages"
# 5. Review JSON output in viewer
# 6. Export to combined database
```

**Recommended Settings:**
- **Mode:** Per Page (for MasterFormat structure)
- **Context:** 8192-16384 tokens
- **Output Allowance:** 3000 tokens
- **Model:** qwen3:8b or granite3-moe:3b

### Use Case 7: Identify Related Sections

**Goal:** Find all sections referenced by a given section

**Method:**

```bash
# Search for cross-references in JSON
jq '.data[] |
  select(.structured.sections[]?.section_number == "08 80 00") |
  .structured.sections[] |
  .content.see, .cross_references' \
  "/Users/andrewhawes/NEECS Dropbox/Andrew Hawes/Python/Masterformat_ Breakdown/masterformat_combined_20250806_101743.json"
```

**Example Output:**

```json
[
  "08 10 00 for door and window frames",
  "07 92 00 for joint sealants",
  "Section 09 90 00 for interior glazing"
]
```

### Use Case 8: Rebuild FAISS Index

**Goal:** Re-index manufacturer documents after adding new files

**Method:**

```bash
cd "/Users/andrewhawes/NEECS Dropbox/Andrew Hawes/Division 8 Product Guide/scripts"

# Rebuild FAISS index from all documents
python3 rebuild_faiss_index.py

# Output:
# - faiss.index (vector database)
# - index_metadata.jsonl (document references)
# - rebuild_index.log (processing log)
```

---

## Integration Examples

### Example 1: Claude Code Agent for Division 08 Analysis

**Location:** `/Users/andrewhawes/NEECS Dropbox/Andrew Hawes/Python/Bidding/.claude/commands/div8.md`

**Usage:**

```bash
# From within Claude Code CLI
/div8 /path/to/bid/documents "Project Name"
```

**What it does:**
1. Loads MasterFormat section definitions
2. Analyzes specifications for Division 08 scope
3. Extracts door/window/hardware schedules from drawings
4. Identifies manufacturers and performance criteria
5. Estimates quantities
6. Generates structured report

### Example 2: Programmatic Section Lookup

**Python:**

```python
import json

def get_section_info(section_number):
    """Look up CSI section details from MasterFormat database"""
    with open('/Users/andrewhawes/NEECS Dropbox/Andrew Hawes/Python/Masterformat_ Breakdown/masterformat_combined_20250806_101743.json', 'r') as f:
        data = json.load(f)

    for page in data['data']:
        if 'structured' in page and 'sections' in page['structured']:
            for section in page['structured']['sections']:
                if section.get('section_number') == section_number:
                    return section
    return None

# Example usage
info = get_section_info("08 44 13")
print(f"Title: {info['title']}")
print(f"Includes: {info['content']['includes']}")
print(f"See also: {info['cross_references'].get('see', [])}")
```

### Example 3: Batch Section Extraction

**Bash Script:**

```bash
#!/bin/bash
# extract_division_08.sh
# Extracts all Division 08 sections from the MasterFormat database

OUTPUT_DIR="/Users/andrewhawes/NEECS Dropbox/Andrew Hawes/Python/project-tracker/CSI_Masterformat/division8_data"
JSON_FILE="/Users/andrewhawes/NEECS Dropbox/Andrew Hawes/Python/Masterformat_ Breakdown/masterformat_combined_20250806_101743.json"

mkdir -p "$OUTPUT_DIR"

# Extract all 08 XX XX sections
jq '.data[] |
  .structured.sections[] |
  select(.section_number | startswith("08 "))' \
  "$JSON_FILE" > "$OUTPUT_DIR/division08_sections.json"

echo "Extracted Division 08 sections to $OUTPUT_DIR/division08_sections.json"
```

### Example 4: Specification Compliance Checker

**Python:**

```python
import json

class SpecComplianceChecker:
    def __init__(self, masterformat_json_path):
        """Load MasterFormat reference data"""
        with open(masterformat_json_path, 'r') as f:
            self.masterformat = json.load(f)

    def check_section_requirements(self, section_number, project_spec):
        """Verify project spec includes required elements"""
        # Get reference section from MasterFormat
        reference = self.get_section_info(section_number)
        if not reference:
            return {"error": "Section not found in MasterFormat"}

        required = reference['content'].get('includes', [])
        missing = []

        for requirement in required:
            if requirement.lower() not in project_spec.lower():
                missing.append(requirement)

        return {
            "section": section_number,
            "title": reference['title'],
            "required_elements": required,
            "missing_elements": missing,
            "compliant": len(missing) == 0
        }

    def get_section_info(self, section_number):
        """Look up section in MasterFormat database"""
        for page in self.masterformat['data']:
            if 'structured' in page:
                for section in page['structured'].get('sections', []):
                    if section.get('section_number') == section_number:
                        return section
        return None

# Usage
checker = SpecComplianceChecker('/path/to/masterformat_combined.json')
result = checker.check_section_requirements(
    "08 80 00",
    "Project specification text here..."
)
print(f"Compliance: {result['compliant']}")
print(f"Missing: {result['missing_elements']}")
```

### Example 5: Cross-Reference Navigator

**Python:**

```python
import json
from typing import List, Dict

class CrossReferenceNavigator:
    def __init__(self, masterformat_json_path):
        with open(masterformat_json_path, 'r') as f:
            self.data = json.load(f)
        self.sections = self._build_section_index()

    def _build_section_index(self) -> Dict:
        """Build searchable index of all sections"""
        index = {}
        for page in self.data['data']:
            if 'structured' in page:
                for section in page['structured'].get('sections', []):
                    sec_num = section.get('section_number')
                    if sec_num:
                        index[sec_num] = section
        return index

    def get_related_sections(self, section_number: str) -> Dict:
        """Get all sections referenced by a given section"""
        section = self.sections.get(section_number)
        if not section:
            return {}

        related = {
            'primary_references': [],
            'additional_references': [],
            'reverse_references': []  # sections that reference this one
        }

        # Extract forward references
        if 'content' in section and 'see' in section['content']:
            related['primary_references'] = self._parse_references(
                section['content']['see']
            )

        if 'cross_references' in section:
            if 'see_also' in section['cross_references']:
                related['additional_references'] = self._parse_references(
                    section['cross_references']['see_also']
                )

        # Find reverse references
        for sec_num, sec_data in self.sections.items():
            refs = self._extract_all_references(sec_data)
            if section_number in refs:
                related['reverse_references'].append({
                    'section_number': sec_num,
                    'title': sec_data.get('title', 'Unknown')
                })

        return related

    def _parse_references(self, ref_list: List[str]) -> List[Dict]:
        """Extract section numbers from reference text"""
        import re
        results = []
        section_pattern = r'\d{2}\s+\d{2}\s+\d{2}'

        for ref in ref_list:
            match = re.search(section_pattern, ref)
            if match:
                sec_num = match.group()
                results.append({
                    'section_number': sec_num,
                    'description': ref,
                    'title': self.sections.get(sec_num, {}).get('title', 'Unknown')
                })
        return results

    def _extract_all_references(self, section: Dict) -> List[str]:
        """Get all section numbers referenced in a section"""
        import re
        refs = []
        section_pattern = r'\d{2}\s+\d{2}\s+\d{2}'

        # Check content.see
        for ref in section.get('content', {}).get('see', []):
            matches = re.findall(section_pattern, ref)
            refs.extend(matches)

        # Check cross_references
        for ref in section.get('cross_references', {}).get('see', []):
            matches = re.findall(section_pattern, ref)
            refs.extend(matches)

        for ref in section.get('cross_references', {}).get('see_also', []):
            matches = re.findall(section_pattern, ref)
            refs.extend(matches)

        return refs

# Usage
navigator = CrossReferenceNavigator('/path/to/masterformat_combined.json')
related = navigator.get_related_sections("08 80 00")

print("Primary References:")
for ref in related['primary_references']:
    print(f"  {ref['section_number']} - {ref['title']}")

print("\nSections that reference this one:")
for ref in related['reverse_references']:
    print(f"  {ref['section_number']} - {ref['title']}")
```

---

## Appendix: Common Tasks

### Task: Find all sections in a division

```bash
# Using jq
jq '.data[] | .structured.sections[] | select(.division == "08") | {section_number, title}' \
  "/Users/andrewhawes/NEECS Dropbox/Andrew Hawes/Python/Masterformat_ Breakdown/masterformat_combined_20250806_101743.json"
```

### Task: Extract section full text

```bash
# Get raw content for a specific section
jq '.data[] | select(.structured.sections[]?.section_number == "08 80 00") | .structured.sections[] | select(.section_number == "08 80 00") | .raw_text' \
  "/Users/andrewhawes/NEECS Dropbox/Andrew Hawes/Python/Masterformat_ Breakdown/masterformat_combined_20250806_101743.json"
```

### Task: List all divisions present in database

```bash
# Get unique division numbers
jq '.data[] | .structured.sections[]? | .division' \
  "/Users/andrewhawes/NEECS Dropbox/Andrew Hawes/Python/Masterformat_ Breakdown/masterformat_combined_20250806_101743.json" | \
  sort -u
```

### Task: Export section to markdown

```bash
# Create markdown file for a section
SECTION="08 80 00"
OUTPUT="/tmp/section_08_80_00.md"

jq -r --arg sec "$SECTION" '
.data[] |
.structured.sections[] |
select(.section_number == $sec) |
"# \(.section_number) - \(.title)\n\n## Includes\n\n\(.content.includes | map("- \(.)") | join("\n"))\n\n## May Include\n\n\(.content.may_include | map("- \(.)") | join("\n"))\n\n## See Also\n\n\(.content.see | map("- \(.)") | join("\n"))\n\n## Full Text\n\n\(.raw_text)"
' "/Users/andrewhawes/NEECS Dropbox/Andrew Hawes/Python/Masterformat_ Breakdown/masterformat_combined_20250806_101743.json" > "$OUTPUT"

echo "Exported to $OUTPUT"
```

---

## Summary

This document provides a comprehensive reference to all CSI MasterFormat data and resources available in your system. Key takeaways:

1. **Central Database:** `masterformat_combined_20250806_101743.json` contains structured MasterFormat 2018 data
2. **Division PDFs:** 35 consolidated PDFs for all active divisions
3. **Processing Tools:** GUI-based processor with AI extraction capabilities
4. **Division 08 Focus:** Extensive tooling for door, window, and glazing analysis
5. **Integration Ready:** JSON schema designed for programmatic access
6. **Training Data:** Infrastructure for creating fine-tuned AI models
7. **Manufacturer Database:** 4,965 technical documents searchable via RAG

**For Questions or Updates:**
- Review `/DIVISION_8_FILE_MAP.md` for complete file locations
- Check `/SPEC_BOOK_ANALYSIS_GUIDE.md` for AI model training guidance
- Explore `/Bidding/` directory for production analysis systems

**Version Control:**
- Document created: December 8, 2025
- MasterFormat version: 2018
- Last database update: August 6, 2025
