#!/usr/bin/env python3
# mf_extract.py
# Deterministic MasterFormat division parser (no LLM)

import os
import re
import json
import sys
import datetime
from typing import List, Dict, Tuple, Optional

from dotenv import load_dotenv
load_dotenv()

# ====== CONFIG ======
# Point this to your folder of .txt divisions via environment variable:
MASTERFORMAT_DIR = os.getenv("MASTERFORMAT_DIR", "")
if not MASTERFORMAT_DIR:
    print("Error: Set MASTERFORMAT_DIR environment variable")
    sys.exit(1)
INPUT_DIR = os.path.join(MASTERFORMAT_DIR, "Divisions")
OUTPUT_DIR = os.path.join(INPUT_DIR, "out")
# If you want to process PDFs directly, set USE_PDF=True and ensure pdfplumber is installed
USE_PDF = False

# ====== OPTIONAL PDF EXTRACTION ======
def extract_text_from_pdf(pdf_path: str) -> str:
    try:
        import pdfplumber  # pip install pdfplumber
    except ImportError:
        raise RuntimeError("pdfplumber not installed. Run: pip install pdfplumber")
    chunks = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            txt = page.extract_text() or ""
            chunks.append(txt)
    return "\n".join(chunks)

# ====== NORMALIZATION ======
def normalize_text(s: str) -> str:
    # Fix hyphenated line breaks like "construc-\ntion"
    s = re.sub(r"(\w)-\n(\w)", r"\1\2", s)
    # Collapse multiple spaces
    s = re.sub(r"[ \t]+", " ", s)
    # Normalize space around hyphens: "owner -installed" -> "owner-installed"
    s = re.sub(r"\s*-\s*", "-", s)
    # Normalize line endings
    s = s.replace("\r\n", "\n").replace("\r", "\n")
    # Remove obvious page headers/footers like "DIVISION 01 – GENERAL REQUIREMENTS" repeating
    s = re.sub(r"\n?DIVISION\s+\d{2}\b[^\n]*\n", "\n", s, flags=re.IGNORECASE)
    return s.strip()

# ====== SECTION SPLIT ======
# Use a PATTERN STRING (no inline flags)
HEADER_PAT = r"^(?P<num>\d{2} \d{2} \d{2}(?:\.\d{2})?)\s+(?P<title>.+?)\s*$"
HEADER_RE = re.compile(HEADER_PAT, re.MULTILINE)

def split_into_sections(text: str) -> List[Tuple[str, str, str]]:
    """
    Returns list of (section_number, title, body) in source order.
    """
    sections: List[Tuple[str, str, str]] = []
    matches = list(HEADER_RE.finditer(text))
    for i, m in enumerate(matches):
        sec_num = m.group("num").strip()
        title = m.group("title").strip()
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[start:end].strip()
        sections.append((sec_num, title, body))
    return sections

# ====== LABELED BLOCKS ======
# Build a block regex that stops at the next label header OR the next SECTION header.
# IMPORTANT: don't inject a compiled pattern with flags.
SECTION_HEAD_BOUNDARY = r"^(?:\d{2} \d{2} \d{2}(?:\.\d{2})?)\s+"

def _block_regex(label: str) -> re.Pattern:
    # Accepts spacing and line breaks; stops at next label or section header or EOF
    next_label = r"^\s*\w[\w /-]*\s*:"
    # Lookahead: next label OR next section header OR end of string
    pat = rf"^\s*{re.escape(label)}\s*:\s*(.*?)\s*(?=(?:{next_label})|(?:{SECTION_HEAD_BOUNDARY})|\Z)"
    return re.compile(pat, re.IGNORECASE | re.MULTILINE | re.DOTALL)

def extract_label_block(body: str, label: str) -> Optional[str]:
    m = _block_regex(label).search(body)
    return m.group(1).strip() if m else None

# ====== SEE / SEE ALSO PARSER ======
SEE_ITEM_RE = re.compile(
    r"\b(\d{2} \d{2} \d{2}(?:\.\d{2})?)\b\s+(.*?)(?:(?:\.\s*)?$|(?=\b\d{2} \d{2} \d{2}(?:\.\d{2})?\b))",
    re.MULTILINE | re.DOTALL,
)

def parse_see_list(s: str) -> List[Dict[str, str]]:
    items: List[Dict[str, str]] = []
    for m in SEE_ITEM_RE.finditer(s):
        sec = m.group(1).strip()
        desc = m.group(2).strip(" .")
        if sec and desc:
            items.append({"section_number": sec, "description": desc})
    # Deduplicate by section_number+description
    uniq: List[Dict[str, str]] = []
    seen = set()
    for it in items:
        key = (it["section_number"], it["description"].lower())
        if key not in seen:
            seen.add(key)
            uniq.append(it)
    return uniq

# Convert lines/semicolons to list items

def lines_to_list(s: str) -> List[str]:
    raw = [x.strip(" \t•-") for x in re.split(r"\n|;", s) if x.strip()]
    return [re.sub(r"\.\s*$", "", x) for x in raw if x]

# ====== SUBSECTION DISCOVERY ======
DECIMAL_CHILD_RE = re.compile(r"^\s*(\d{2} \d{2} \d{2}\.\d{2})\s+(.+?)\s*$", re.MULTILINE)

def find_subsections(parent_num: str, body: str) -> List[Dict[str, str]]:
    base = parent_num + "."
    subs: List[Dict[str, str]] = []
    for m in DECIMAL_CHILD_RE.finditer(body):
        if m.group(1).startswith(base):
            subs.append({"section_number": m.group(1).strip(), "title": m.group(2).strip()})
    # Deduplicate
    uniq, seen = [], set()
    for s in subs:
        k = s["section_number"]
        if k not in seen:
            seen.add(k)
            uniq.append(s)
    return uniq

# ====== SECTION OBJECT ======
L1_PATTERN = re.compile(r"^\d{2} \d{2} \d{2}$")
L2_PATTERN = re.compile(r"^\d{2} \d{2} \d{2}\.\d{2}$")

def division_of(sec_num: str) -> str:
    return sec_num[:2]

def level_of(sec_num: str) -> int:
    if L2_PATTERN.match(sec_num):
        return 2
    if L1_PATTERN.match(sec_num):
        return 1
    return 1

def split_alternate_terms(s: str) -> List[str]:
    parts = re.split(r"[:,;]", s.strip())
    return [p.strip(" .") for p in parts if p.strip(" .")]

def parse_section(sec_num: str, title: str, body: str) -> Dict:
    out: Dict = {
        "section_number": sec_num,
        "title": title,
        "division": division_of(sec_num),
        "level": level_of(sec_num),
    }

    # Labeled blocks
    includes = extract_label_block(body, "Includes")
    may_inc  = extract_label_block(body, "May Include")
    products = extract_label_block(body, "Products")
    alts     = extract_label_block(body, "Alternate Terms/Abbreviations")
    see      = extract_label_block(body, "See")
    see_also = extract_label_block(body, "See Also")

    if includes:
        out["includes"] = lines_to_list(includes)
    if may_inc:
        out["may_include"] = lines_to_list(may_inc)
    if products:
        out["products"] = lines_to_list(products)
    if alts:
        out["alternate_terms"] = split_alternate_terms(alts)
    if see:
        parsed = parse_see_list(see)
        if parsed:
            out["see"] = parsed
    if see_also:
        parsed = parse_see_list(see_also)
        if parsed:
            out["see_also"] = parsed

    # Subsections (only decimals under this parent)
    subs = find_subsections(sec_num, body)
    if subs:
        out["sub_sections"] = subs

    # Keep raw block if helpful for QA
    raw_block = body.strip()
    if raw_block:
        out["raw_text"] = raw_block

    return out

# ====== FILE PROCESS ======

def process_text_unit(unit_label: str, text: str) -> Dict:
    text = normalize_text(text)
    sections = split_into_sections(text)
    results = []
    for sec_num, title, body in sections:
        # Enforce a valid pattern (skip junk headers)
        if not (L1_PATTERN.match(sec_num) or L2_PATTERN.match(sec_num)):
            continue
        results.append(parse_section(sec_num, title, body))

    return {
        "unit": unit_label,
        "document_info": {
            "division": results[0]["division"] if results else "",
            "source_file": unit_label,
            "extracted_at": datetime.datetime.utcnow().isoformat() + "Z",
            "model": "deterministic-parser"
        },
        "sections": results
    }

def write_json(out_path: str, obj: Dict):
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    tmp = out_path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, ensure_ascii=True)
    if os.path.exists(out_path):
        try:
            os.remove(out_path)
        except Exception:
            pass
    os.rename(tmp, out_path)


def extract_text(path: str) -> str:
    if USE_PDF and path.lower().endswith('.pdf'):
        return extract_text_from_pdf(path)
    # default: read TXT
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        return f.read()


def process_path(path: str):
    name = os.path.basename(path)
    text = extract_text(path)
    unit_json = process_text_unit(name, text)
    out_name = os.path.splitext(name)[0] + ".json"
    out_path = os.path.join(OUTPUT_DIR, out_name)
    write_json(out_path, unit_json)
    print(f"\u2713 {name} \u2192 {out_name} ({len(unit_json.get('sections', []))} sections)")


def main():
    src = INPUT_DIR
    if len(sys.argv) > 1:
        src = sys.argv[1]

    paths: List[str] = []
    if os.path.isdir(src):
        for fn in sorted(os.listdir(src)):
            if USE_PDF:
                if fn.lower().endswith(".pdf"):
                    paths.append(os.path.join(src, fn))
            else:
                if fn.lower().endswith(".txt"):
                    paths.append(os.path.join(src, fn))
    elif os.path.isfile(src):
        paths = [src]
    else:
        print(f"Not found: {src}")
        sys.exit(1)

    if not paths:
        kind = "PDFs" if USE_PDF else "TXT files"
        print(f"No {kind} found in {src}")
        sys.exit(1)

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    for p in paths:
        try:
            process_path(p)
        except Exception as e:
            print(f"\u2717 Error on {os.path.basename(p)}: {e}")


if __name__ == "__main__":
    main()
