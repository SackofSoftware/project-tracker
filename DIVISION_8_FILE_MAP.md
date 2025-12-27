# Division 8 File Map & Quick Reference

**Generated:** December 4, 2025
**Purpose:** Quick reference for all Division 8 related files across the codebase

---

## Directory Structure Overview

```
Python/
├── Bidding/                    # PRIMARY - Multi-agent bid analysis
├── Job_Extraction/             # Estimating intelligence & pricing
├── ArchDrawingParse/           # Drawing extraction pipeline (219 files)
├── Spec_Book_Splitter/         # Specification processing
├── construction_doc_summarizer/# Document summarization
├── DeepseekOCR/                # Vision-based OCR
├── DrawingReview/              # Drawing review system
├── Agentic_Drawing_Viewer/     # Template-aware viewer
├── MultiAgent/                 # Agent framework
├── FineTune/                   # Training data
└── Windows_Thermal-Tools/      # Thermal analysis
```

---

## Quick Start Commands

### Run Division 08 Analysis
```bash
# From /Bidding directory
python3 orchestrate_project.py --project-path /path/to/bid/docs --project-name "Project Name"

# Or use Claude Code command
/div8 <project_path> <project_name>
```

### Run Individual Agents
```bash
python3 run_spec_analyzer_agent.py
python3 run_drawing_analyzer_agent.py
python3 run_admin_processor_agent.py
```

### Query Manufacturer Specs
```bash
cd Job_Extraction
python3 manufacturer_query.py "aluminum storefront thermal break"
```

---

## Primary Files by Function

### Bid Analysis (Core System)

| File | Path | Function |
|------|------|----------|
| Main Analyzer | `Bidding/division_08_analyzer.py` | Division 08 scope extraction |
| RAG Parser | `Bidding/rag_document_parser.py` | ChromaDB + Ollama embeddings |
| Orchestrator | `Bidding/orchestrate_project.py` | Multi-agent coordination |
| Spec Agent | `Bidding/agents/spec_analyzer_agent.py` | CSI section extraction |
| Drawing Agent | `Bidding/agents/drawing_analyzer_agent.py` | Schedule extraction |
| Admin Agent | `Bidding/agents/admin_doc_processor_agent.py` | Project metadata |

### Estimating Intelligence

| File | Path | Function |
|------|------|----------|
| Proposal Analyzer | `Job_Extraction/EstimateIQ/proposal_analyzer.py` | 287 proposal analysis |
| Quote Analyzer | `Job_Extraction/EstimateIQ/supplier_quote_analyzer.py` | Supplier quote parsing |
| Vision Quotes | `Job_Extraction/EstimateIQ/supplier_quote_vision_analyzer.py` | Vision-based extraction |
| Window Pricing | `Job_Extraction/EstimateIQ/window_pricing_analyzer.py` | $/SF pricing analysis |
| Material Trends | `Job_Extraction/EstimateIQ/tools/analysis/material_cost_trends.py` | Cost forecasting |
| Labor Predictor | `Job_Extraction/EstimateIQ/tools/analysis/labor_predictor.py` | Labor cost models |

### Drawing Processing

| File | Path | Function |
|------|------|----------|
| Pipeline CLI | `ArchDrawingParse/python_pipeline/pipeline_cli.py` | Command-line interface |
| PDF to PNG | `ArchDrawingParse/python_pipeline/stages/stage_01_pdf_to_png.py` | Image conversion |
| Vision Extract | `ArchDrawingParse/python_pipeline/stages/stage_05_vision_extraction.py` | AI extraction |
| Classification | `ArchDrawingParse/classify_drawings_robust.py` | Drawing categorization |
| RAG System | `ArchDrawingParse/rag_system.py` | Semantic search |

### Specification Processing

| File | Path | Function |
|------|------|----------|
| Unified Processor | `Spec_Book_Splitter/unified_spec_processor.py` | Main spec processing |
| Division Extractor | `construction_doc_summarizer/src/.../specs/division_extractor.py` | CSI division parsing |
| Division Pipeline | `construction_doc_summarizer/src/.../specs/division_pipeline.py` | Multi-PDF assembly |
| Product Extractor | `Job_Extraction/product_spec_extractor.py` | 40+ field extraction |

---

## Agent Configuration Files

### Claude Code Agents (`.claude/commands/`)

| Location | Agent | Purpose |
|----------|-------|---------|
| `Bidding/.claude/commands/div8.md` | Division 8 Inspector | Full Div 8 analysis |

### Agent Prompts (`Bidding/claude_agents/`)

| File | Purpose |
|------|---------|
| `orchestrator_agent_prompt.md` | Master coordination |
| `spec_analyzer_agent_prompt.md` | Specification analysis |
| `drawing_analyzer_agent_prompt.md` | Drawing extraction |
| `admin_doc_processor_agent_prompt.md` | Admin document processing |

---

## Data Assets

### Databases

| Asset | Path | Contents |
|-------|------|----------|
| Proposal DB | `Job_Extraction/EstimateIQ/data/proposal_database.csv` | 287 proposals |
| Supplier Quotes | `Job_Extraction/EstimateIQ/data/supplier_quotes_vision_full.csv` | 82 line items |
| Manufacturer Index | `Job_Extraction/manufacturer_specs/faiss.index` | 4,965 docs |
| ChromaDB | `Bidding/chroma_db/` | Project vectors |

### Training Data

| Path | Contents |
|------|----------|
| `FineTune/training-data/Cleaned_Subsections/084113_*.json` | Storefront training |
| `FineTune/training-data/Cleaned_Subsections/085213_*.json` | Windows training |
| `FineTune/training-data/Cleaned_Subsections/087100_*.json` | Hardware training |
| `FineTune/training-data/Cleaned_Subsections/088000_*.json` | Glazing training |

---

## CSI Section Reference

### Included in Scope

```
081113 - Hollow Metal Doors and Frames
081216 - Aluminum Doors and Frames
082113 - Plastic Doors
083113 - Access Doors
084113 - Aluminum-Framed Entrances and Storefronts
084213 - Sliding Aluminum-Framed Entrances
084313 - Revolving Door Entrances
084413 - Glazed Aluminum Curtain Walls
085113 - Metal Windows
085213 - Aluminum Windows
085313 - Vinyl Windows
087100 - Door Hardware
088000 - Glazing
088300 - Mirrors
```

### Excluded from Scope

```
081416 - Flush Wood Doors
082813 - Overhead Coiling Doors
083313 - Rolling Doors
```

---

## Technology Stack

### AI/ML Models

| Model | Usage | Location |
|-------|-------|----------|
| mxbai-embed-large | Embeddings | Ollama |
| Pixtral-12B | Vision extraction | OpenRouter |
| Qwen3-VL | Local vision OCR | LM Studio |
| DeepSeek | Drawing analysis | OpenRouter |

### Databases

| Technology | Purpose | Config |
|------------|---------|--------|
| ChromaDB | Vector store | `Bidding/chroma_db/` |
| FAISS | Fast similarity | `Job_Extraction/faiss.index` |
| SQLite | Product database | `Job_Extraction/products.db` |

### PDF Processing

| Library | Primary Use |
|---------|-------------|
| pdfplumber | Text extraction |
| PyMuPDF (fitz) | PDF manipulation |
| pdf2image | PNG conversion |
| Pillow | Image processing |

---

## Output Locations

### Analysis Results
- `Bidding/Combined_Bidding_Project_FINAL_ANALYSIS.json`
- `Bidding/*_spec_analyzer_results.json`
- `Bidding/*_drawing_analyzer_results.json`

### Reports
- `Job_Extraction/EstimateIQ/data/reports/material_trends_report.txt`
- `Job_Extraction/EstimateIQ/data/reports/market_trends_report.txt`
- `Job_Extraction/EstimateIQ/data/reports/prevailing_wage_report.txt`

---

## Common Patterns

### Hardware Finish Codes
| Code | Description |
|------|-------------|
| US26D | Satin Chrome |
| 626 | Satin Chrome (alt) |
| 630 | Satin Stainless |
| 689 | Aluminum Painted |

### Schedule Search Patterns
```python
# Door schedules
"door schedule", "hollow metal", "door type", "door mark"

# Window schedules
"window schedule", "window type", "aluminum window", "window elevation"

# Hardware schedules
"hardware set", "hardware group", "lockset", "closer"

# Storefront
"storefront", "entrance system", "aluminum framing"

# Curtain wall
"curtain wall", "unitized", "stick system"
```

---

## Troubleshooting

### RAG Not Finding Documents
1. Check ChromaDB collection exists: `ls Bidding/chroma_db/`
2. Verify embeddings model loaded: `ollama list | grep mxbai`
3. Re-index if needed: `python3 rag_document_parser.py --reindex`

### Vision Extraction Failing
1. Check OpenRouter API key in environment
2. Verify image DPI (150 recommended)
3. Try fallback OCR: `stage_04_ocr_fallback.py`

### Agent Not Finding Schedules
1. Verify PDF is text-based (not image-only)
2. Check document chunking parameters
3. Review confidence scores in output JSON
