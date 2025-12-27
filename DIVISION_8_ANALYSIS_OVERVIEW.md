# Division 8 Construction Analysis System Overview

**Generated:** December 4, 2025
**Purpose:** Document the comprehensive Division 8 (Openings) analysis ecosystem built across this codebase

---

## Executive Summary

This codebase represents a **sophisticated, production-ready multi-agent system** specifically designed for Division 8 construction scope analysis. The focus is on:

1. **Glazing contractor bid analysis** - Extracting doors, windows, storefront, curtain wall, hardware, and glazing from construction documents
2. **Automated specification parsing** - RAG-powered document retrieval and CSI MasterFormat section identification
3. **Drawing schedule extraction** - Vision-based extraction of door/window schedules from architectural drawings
4. **Cost estimation intelligence** - Historical pricing databases, supplier quote analysis, and labor prediction

---

## Primary Focus Areas

### 1. Division 08 Scope Extraction

**Target CSI Sections:**
| Section | Description | Status |
|---------|-------------|--------|
| 081113 | Hollow Metal Doors and Frames | Included |
| 081216 | Aluminum Doors and Frames | Included |
| 084113 | Aluminum-Framed Entrances/Storefronts | Included |
| 084213 | Sliding Aluminum-Framed Entrances | Included |
| 084313 | Revolving Door Entrances | Included |
| 084413 | Glazed Aluminum Curtain Walls | Included |
| 085113 | Metal Windows | Included |
| 085213 | Aluminum Windows | Included |
| 087100 | Door Hardware | Included |
| 088000 | Glazing | Included |
| 088300 | Mirrors | Included |

**Excluded Sections:**
- 081416 - Flush Wood Doors (not glazing scope)
- 082813 - Overhead Coiling Doors
- 083313 - Rolling Doors

### 2. Document Processing Workflow

```
PDF Documents
     │
     ▼
┌─────────────────┐
│  RAG Indexing   │ ─── ChromaDB + Ollama Embeddings
└────────┬────────┘
         │
         ▼
┌─────────────────────────────────────────────┐
│         Multi-Agent Orchestration           │
│  ┌─────────────┐ ┌─────────────┐ ┌────────┐ │
│  │Spec Analyzer│ │Drawing Anal.│ │Admin   │ │
│  │   Agent     │ │   Agent     │ │Processor│ │
│  └─────────────┘ └─────────────┘ └────────┘ │
└────────────────────┬────────────────────────┘
                     │
                     ▼
           ┌─────────────────┐
           │  Orchestrator   │ ─── Synthesis & Gap Detection
           │     Agent       │
           └────────┬────────┘
                    │
                    ▼
            FINAL_ANALYSIS.json
```

---

## Core Systems by Directory

### `/Bidding/` - Multi-Agent Bid Analysis System

| File | Purpose |
|------|---------|
| `division_08_analyzer.py` | Main Division 08 scope analyzer |
| `rag_document_parser.py` | RAG system with ChromaDB + Ollama |
| `orchestrate_project.py` | Autonomous multi-agent orchestration |
| `agents/spec_analyzer_agent.py` | CSI specification extraction |
| `agents/drawing_analyzer_agent.py` | Schedule/elevation extraction |
| `agents/admin_doc_processor_agent.py` | Project metadata extraction |
| `agents/orchestrator_agent.py` | Agent coordination |

**Key Capabilities:**
- Semantic search across bid documents
- Automatic gap detection (e.g., "specs found but no schedules")
- Confidence scoring for findings
- JSON schema-compliant output

### `/Job_Extraction/` - Estimating Intelligence

| Subsystem | Files | Purpose |
|-----------|-------|---------|
| **EstimateIQ** | 20+ files | Proposal analysis, quote comparison, pricing trends |
| **Visual RAG** | 5 files | Multimodal document retrieval with ColNomic embeddings |
| **Manufacturer Specs** | FAISS index | 4,965+ manufacturer documents indexed |

**Data Assets:**
- 287 analyzed proposals in `proposal_database.csv`
- 82+ supplier quote line items with pricing
- Material cost trend reports
- Prevailing wage analysis

### `/ArchDrawingParse/` - Drawing Extraction Pipeline

**8-Stage Processing Pipeline:**
1. PDF to PNG conversion
2. Table of Contents extraction
3. Image cropping
4. Vision model extraction
5. Text extraction (pdfplumber)
6. Text refinement
7. Project name refinement
8. Final organization

**219 Python files** covering:
- Multi-worker parallel processing
- Vision APIs (Pixtral-12B, Qwen, DeepSeek)
- FAISS vector search for semantic queries
- Drawing classification and categorization

### `/Spec_Book_Splitter/` - Specification Processing

- Unified spec processor with GUI
- MasterFormat section detection
- Footer pattern parsing
- PDF to JSON conversion
- 40+ test files for pattern validation

### `/construction_doc_summarizer/` - Document Summarization

- Division extraction from spec books
- CSI format parsing
- Summary pipeline for division content
- GUI application for manual processing

---

## Performance Metrics Extracted

The system extracts comprehensive performance data for Division 08 products:

### Thermal Performance
- U-factor (overall thermal transmittance)
- SHGC (Solar Heat Gain Coefficient)
- VT (Visible Transmittance)
- CR/CRF (Condensation Resistance)

### Structural Performance
- Design pressure ratings
- Wind load resistance
- Deflection limits
- Impact resistance

### Air/Water Infiltration
- ASTM E283 air infiltration
- ASTM E331 water penetration
- AAMA/WDMA ratings

### Acoustic & Fire
- STC ratings
- Fire ratings (doors/frames)
- Smoke/draft resistance

---

## Agent Architecture

### Custom Claude Code Agents

Located in `.claude/` directories across projects:

| Agent Type | Function |
|------------|----------|
| `division-8-inspector` | Coordinates entire Div 8 analysis |
| `door-schedule-agent` | Door schedule extraction |
| `window-schedule-agent` | Window/glazing extraction |
| `spec-analyzer-agent` | CSI specification parsing |
| `project-estimate-assessor` | Estimate status analysis |
| `construction-bid-organizer` | PDF organization for bids |

### Multi-Agent Framework

`/MultiAgent/` provides hybrid orchestration supporting:
- AutoGen (Microsoft framework)
- LangChain + LangGraph workflows
- Concurrent processing with thread pools

### Family Dashboard Calendar Agents (Reference)

7-agent sequential pipeline demonstrating pattern:
1. Date Parsing Agent
2. Venue Agent
3. Team Recognition Agent
4. Member Assignment Agent
5. Categorization Agent
6. Conflict Detection Agent
7. Sync Agent

---

## Training Data & Fine-Tuning

### `/FineTune/training-data/Cleaned_Subsections/`

Pre-processed training data for Division 08 sections:
- 084110, 084113, 084213, 084313 (Storefronts/Entrances)
- 085160, 085200, 085216, 085310, 085313 (Windows)
- 085413 (Curtain Walls)
- 086200 (Skylights)
- 087100, 087150 (Door Hardware)
- 088000, 088050, 088100, 088413, 088813 (Glazing/Mirrors)

Both `.json` and `.jsonl` formats available for model training.

---

## Hardware Patterns Tracked

The system specifically identifies and categorizes:

### Door Hardware Sets
- SET 1, SET 2, SET 3, etc.
- Hardware group associations

### Finish Codes
- US26D (Satin Chrome)
- 626 (Satin Chrome - alternate)
- 630 (Satin Stainless)
- 689 (Aluminum painted)

### Hardware Types
- Hinges
- Locksets
- Door Closers
- Panic Hardware
- Exit Devices
- Thresholds
- Weatherstripping
- Sweeps

---

## Key Integrations

| Technology | Purpose |
|------------|---------|
| **Ollama** | Local LLM inference (mxbai-embed-large) |
| **ChromaDB** | Vector database for RAG |
| **FAISS** | Fast similarity search |
| **OpenRouter** | Cloud vision models (Pixtral-12B) |
| **LM Studio** | Local model hosting |
| **pdfplumber** | PDF text extraction |
| **PyMuPDF** | PDF manipulation |

---

## Typical Workflow

1. **Receive bid documents** (PDF specs + drawings)
2. **Run RAG indexing** via `rag_document_parser.py`
3. **Deploy specialized agents** in parallel
4. **Orchestrator synthesizes** findings
5. **Gap detection** identifies missing information
6. **Redeployment** if needed for specific queries
7. **Final analysis JSON** with completeness score

---

## Output Schema

The system produces structured JSON with:

```json
{
  "project_info": { "name", "location", "square_footage", "budget" },
  "division_08_scope": {
    "doors": [...],
    "windows": [...],
    "storefront": [...],
    "curtainwall": [...],
    "hardware": [...],
    "glazing": [...],
    "mirrors": [...]
  },
  "specifications": { "sections_found": [...], "manufacturers": [...] },
  "drawings": { "schedules": [...], "details": [...] },
  "completeness_score": 0.85,
  "gaps_identified": [...]
}
```

---

## Summary

This Division 8 analysis ecosystem represents a **glazing contractor's complete bid analysis toolkit**, combining:

- **RAG-powered document retrieval** for semantic search
- **Multi-agent orchestration** for parallel processing
- **Vision models** for drawing extraction
- **Historical pricing intelligence** for cost estimation
- **Structured output** for downstream integration

The focus is clearly on **commercial glazing scope** (storefront, curtain wall, aluminum windows) with explicit exclusion of wood doors and overhead doors that fall outside typical glazing contractor scope.
