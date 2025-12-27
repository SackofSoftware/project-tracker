# Your Division 8 Focus Areas - Analysis

**Generated:** December 4, 2025
**Purpose:** Analysis of what you tend to focus on based on your codebase

---

## Key Insight

Based on the extensive tooling and systems you've built, you are clearly operating as a **commercial glazing contractor** focused on:

1. **Bid document analysis** for Division 08 scope
2. **Automated extraction** of schedules and specs from construction documents
3. **Cost intelligence** for competitive bidding

---

## Your Primary Focus Areas

### 1. Schedule Extraction from Drawings

**Heavy Investment In:**
- Door schedule detection and parsing
- Window schedule/elevation extraction
- Hardware schedule identification
- Storefront/curtain wall system drawings

**Tools Built:**
- 219+ Python files in `/ArchDrawingParse/`
- Multi-pass vision extraction pipeline
- Template-aware processing in `/Agentic_Drawing_Viewer/`
- Confidence scoring for schedule findings

**Pattern:** You prioritize **accurate schedule extraction** over general drawing analysis. Your systems specifically target the A-sheets (architectural) where schedules live.

---

### 2. Specification Analysis

**Heavy Investment In:**
- Division 08 section identification (081113 through 088300)
- Manufacturer extraction from specs
- Performance requirement parsing (U-factor, SHGC, structural)
- Explicit exclusion of non-glazing scope (wood doors, overhead doors)

**Tools Built:**
- RAG-powered specification retrieval
- CSI MasterFormat section detection
- 40+ field product specification extractor
- Manufacturer FAISS index (4,965+ documents)

**Pattern:** You care deeply about **what's specified** - not just that specs exist, but extracting actionable data: who manufactures it, what performance is required, what finishes.

---

### 3. Estimating & Pricing Intelligence

**Heavy Investment In:**
- Historical proposal analysis (287 proposals catalogued)
- Supplier quote comparison
- Material cost trends (aluminum, uPVC, fiberglass)
- $/SF pricing calculations
- Labor cost prediction

**Tools Built:**
- Complete `EstimateIQ` subsystem
- Visual RAG for quote extraction
- Cross-reference analyzers
- Prevailing wage analysis

**Pattern:** You're building a **pricing intelligence system** - not just estimating individual projects but learning from historical data to improve future bids.

---

### 4. Multi-Agent Automation

**Heavy Investment In:**
- Parallel agent execution for bid analysis
- Orchestration with gap detection
- Confidence scoring and redeployment logic
- Structured JSON output for downstream use

**Tools Built:**
- Custom Claude Code agent definitions
- Orchestrator with synthesis capabilities
- 7-agent pipeline examples (calendar system as reference)
- AutoGen + LangChain hybrid framework

**Pattern:** You're not just automating tasks - you're building **autonomous systems** that can identify what they don't know and take corrective action.

---

## What You Seem to Care Most About

### From Drawing Analysis
| Priority | Element | Evidence |
|----------|---------|----------|
| High | Door schedules | Dedicated methods, pattern matching, confidence scoring |
| High | Window schedules | Elevation correlation, type extraction |
| High | Hardware schedules | Finish codes (US26D, 626, etc.), set groupings |
| Medium | Storefront details | System type identification |
| Medium | Curtain wall details | Unitized vs stick detection |
| Lower | Floor plans | Used for context, not primary extraction |

### From Specifications
| Priority | Element | Evidence |
|----------|---------|----------|
| High | Section identification | Regex patterns for 6-digit CSI codes |
| High | Manufacturers | Named entity extraction |
| High | Performance requirements | U-factor, SHGC, structural ratings |
| High | Hardware details | Sets, finishes, types |
| Medium | Submittals requirements | What needs to be submitted |
| Lower | General requirements | Div 01 context only |

### From Estimating
| Priority | Element | Evidence |
|----------|---------|----------|
| High | Material pricing | $/SF by material type |
| High | Historical comparisons | 287 proposal database |
| High | Supplier quote analysis | Vision-based extraction |
| Medium | Labor rates | Prediction models built |
| Medium | Prevailing wage impact | Davis-Bacon analysis |

---

## Excluded Scope (What You Don't Focus On)

Based on explicit exclusions in your code:

| Item | Reason |
|------|--------|
| Wood doors (081416) | Not glazing scope |
| Overhead coiling doors (082813) | Specialty door contractor scope |
| Rolling doors (083313) | Specialty door contractor scope |
| Interior partitions | Division 10 |
| Structural glazing calculations | Engineering scope |
| Installation means & methods | Field operations |

---

## Your Typical Workflow (Inferred)

```
1. RECEIVE BID DOCUMENTS
   ├── Specifications PDF
   ├── Architectural drawings PDF
   └── Administrative documents

2. AUTOMATED ANALYSIS
   ├── RAG index all documents
   ├── Deploy spec analyzer → Find Div 08 sections
   ├── Deploy drawing analyzer → Find schedules
   └── Deploy admin processor → Extract project info

3. ORCHESTRATOR SYNTHESIS
   ├── Correlate specs with schedules
   ├── Identify gaps (specs without schedules, etc.)
   └── Generate completeness score

4. ESTIMATING WORKFLOW
   ├── Extract quantities from schedules
   ├── Look up historical pricing
   ├── Apply material/labor models
   └── Generate bid pricing

5. OUTPUT
   ├── Structured JSON for systems integration
   ├── Gap report for manual review
   └── Confidence-scored findings
```

---

## Recommendations Based on Analysis

### What's Strong
- Specification parsing is robust
- Schedule extraction has multiple fallbacks (vision + OCR + text)
- Pricing intelligence is comprehensive
- Agent architecture is production-ready

### Potential Gaps Identified
1. **Takeoff quantities** - Systems identify schedules but quantity extraction could be deeper
2. **Shop drawing integration** - Less tooling for post-award shop drawing review
3. **Change order tracking** - No apparent RFI/CO management system
4. **Bid/no-bid decision support** - Could add scoring for go/no-go decisions

### Next Evolution
Based on your trajectory, likely next steps would be:
- Automated takeoff from schedules (count doors, windows, SF of storefront)
- Integration with estimating software (Excel/database output)
- Real-time pricing updates from supplier APIs
- Project outcome tracking (did we win? how accurate was estimate?)

---

## Summary Statistics

| Category | Count |
|----------|-------|
| Python files for Division 8 analysis | 550+ |
| Historical proposals analyzed | 287 |
| Manufacturer specs indexed | 4,965 |
| CSI sections actively tracked | 14 |
| Agent types configured | 10+ |
| Training data files (Div 08) | 36 |

---

## Conclusion

Your codebase reveals a **professional glazing contractor** building an **autonomous bid analysis system** that:

1. **Extracts scope** from specifications and drawings
2. **Compares pricing** against historical data
3. **Identifies gaps** before human review
4. **Outputs structured data** for estimating

The focus is clearly on **commercial glazing** (storefront, curtain wall, aluminum entrances) with strong attention to **hardware scope** and **performance specifications**.

This is not a general construction document system - it's a **specialized tool for glazing bid analysis**.
