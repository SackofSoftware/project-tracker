#!/usr/bin/env python3
import os
import re
from pathlib import Path
from statistics import quantiles
from pypdf import PdfReader, PdfWriter
from pdfminer.high_level import extract_pages
from pdfminer.layout import LTTextContainer, LTChar

from dotenv import load_dotenv
load_dotenv()

# Paths - set via environment or command line
MASTERFORMAT_DIR = os.getenv("MASTERFORMAT_DIR", "")
if not MASTERFORMAT_DIR:
    print("Error: Set MASTERFORMAT_DIR environment variable to the Masterformat breakdown directory")
    import sys
    sys.exit(1)

SOURCE_PDF = Path(MASTERFORMAT_DIR) / "Masterformat2018.pdf"
OUTPUT_DIR = Path(MASTERFORMAT_DIR) / "Divisions"

HEADER_RE = re.compile(r"^\s*(?:DIVISION|Division)\s+([0-4]\d)\s*[–—-]\s+.+$")
EXPECTED = list(range(1, 49))  # 01..48

# Heuristics
TOP_FRACTION = 0.45          # only consider lines in top 45% of page
PCTL_THRESHOLD = 0.90        # keep lines with font size >= 90th percentile on that page

def page_candidates(pdf_path):
    """
    Yields per-page candidate header lines with metadata:
    [{'page': i, 'text': line, 'div': int, 'y_top': y1, 'y_rel': y1/height, 'font': size}]
    """
    candidates = []
    for i, page_layout in enumerate(extract_pages(str(pdf_path))):
        page_height = getattr(page_layout, "height", None) or 1000.0

        # Collect lines with their average font size and bbox
        lines = []
        for element in page_layout:
            if isinstance(element, LTTextContainer):
                for textline in element:
                    try:
                        line_text = textline.get_text().strip("\n")
                    except Exception:
                        continue
                    if not line_text.strip():
                        continue

                    # Compute average font size for chars on this line
                    sizes = []
                    for obj in textline:
                        if isinstance(obj, LTChar):
                            sizes.append(obj.size)
                    if not sizes:
                        # fallback: try children that contain LTChar
                        for obj in textline:
                            if hasattr(obj, "_objs"):
                                for sub in obj._objs:
                                    if isinstance(sub, LTChar):
                                        sizes.append(sub.size)
                    if not sizes:
                        continue

                    avg_size = sum(sizes) / len(sizes)
                    x0, y0, x1, y1 = textline.bbox
                    lines.append({
                        "text": line_text.strip(),
                        "font": avg_size,
                        "bbox": (x0, y0, x1, y1),
                        "y_rel": y1 / page_height
                    })

        if not lines:
            continue

        # Compute 90th percentile font size for this page
        try:
            p90 = quantiles([ln["font"] for ln in lines], n=10)[-1]  # 90th
        except Exception:
            # if quantiles fails (few lines), use max
            p90 = max(ln["font"] for ln in lines)

        # Filter to big, top-of-page lines that look like real headers
        for ln in lines:
            if ln["y_rel"] < (1.0 - TOP_FRACTION):  # we measure from bottom; y_rel close to 1 is top
                continue
            if ln["font"] + 1e-6 < p90:  # keep only the largest-ish text
                continue
            if ln["text"].startswith(("See Division", "SEE DIVISION", "See DIVISION", "see Division")):
                continue
            m = HEADER_RE.match(ln["text"])
            if not m:
                continue
            div = int(m.group(1))
            if 1 <= div <= 48:
                candidates.append({
                    "page": i,
                    "text": ln["text"],
                    "div": div,
                    "y_rel": ln["y_rel"],
                    "font": ln["font"]
                })
                # only the strongest line per page; break since we've got the big header
                break
    return candidates

def dedupe_first_by_div(cands):
    first = {}
    for h in sorted(cands, key=lambda x: x["page"]):
        if h["div"] not in first:
            first[h["div"]] = h
    return [first[d] for d in sorted(first.keys(), key=lambda d: first[d]["page"])]

def pretty_candidates(cands, total_pages):
    print("\n=== Division Header Candidates (Pre-Filter) ===")
    if not cands:
        print("No header candidates found.")
        return
    print(f"Total pages: {total_pages}")
    print(f"{'Page':>6} {'Div':>3} {'Font':>6} {'Top%':>6}  Header")
    print("-" * 92)
    for h in sorted(cands, key=lambda x: x["page"]):
        txt = h["text"]
        if len(txt) > 70:
            txt = txt[:67] + "..."
        print(f"{h['page']+1:6} {h['div']:>3} {h['font']:6.1f} {h['y_rel']*100:6.1f}  {txt}")

def pretty_plan(ordered, total_pages):
    print("\n=== Extraction Plan ===")
    if not ordered:
        print("No divisions to extract.")
        return
    print(f"{'Division':>8} {'StartPg':>8} {'EndPg':>8}")
    print("-" * 28)
    for idx, h in enumerate(ordered):
        start = h["page"]
        end = (ordered[idx+1]["page"] - 1) if (idx + 1) < len(ordered) else (total_pages - 1)
        print(f"{h['div']:>8} {start+1:8} {end+1:8}")

def robust_div_from_page(reader, page_idx):
    """Re-parse the first ~40% of page text and confirm the division number."""
    try:
        txt = reader.pages[page_idx].extract_text() or ""
    except Exception:
        return None
    if not txt.strip():
        return None
    # only look near the top
    head = txt[: max(300, int(len(txt) * 0.40))]
    for line in head.splitlines():
        line = line.strip()
        if line.startswith(("See Division", "SEE DIVISION", "See DIVISION", "see Division")):
            continue
        m = HEADER_RE.match(line)
        if m:
            return int(m.group(1))
    return None

def write_slice(reader, start_idx, end_idx_inclusive, out_path):
    writer = PdfWriter()
    for p in range(max(0, start_idx), min(end_idx_inclusive + 1, len(reader.pages))):
        writer.add_page(reader.pages[p])
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("wb") as f:
        writer.write(f)

def main():
    if not SOURCE_PDF.exists():
        raise FileNotFoundError(f"Source PDF not found: {SOURCE_PDF}")

    reader = PdfReader(str(SOURCE_PDF))
    total_pages = len(reader.pages)
    if total_pages == 0:
        raise RuntimeError("PDF has 0 pages.")

    raw = page_candidates(SOURCE_PDF)
    pretty_candidates(raw, total_pages)

    ordered = dedupe_first_by_div(raw)
    pretty_plan(ordered, total_pages)

    found_set = {h["div"] for h in ordered}
    missing = [d for d in EXPECTED if d not in found_set]
    if missing:
        print("\nℹ️ Missing divisions (skipped): " + ", ".join(f"{d:02d}" for d in missing))

    print("\n=== Writing Files ===")
    wrote = 0
    for idx, h in enumerate(ordered):
        start = h["page"]
        end = (ordered[idx+1]["page"] - 1) if (idx + 1) < len(ordered) else (total_pages - 1)
        if end < start:
            print(f"⚠️ Skip Division {h['div']:02d}: end before start (start={start+1}, end={end+1}).")
            continue

        # confirm division from slice start page
        confirmed = robust_div_from_page(reader, start)
        div_for_name = confirmed if confirmed else h["div"]

        out_name = f"Masterformat Division {div_for_name:02d}.pdf"
        out_path = OUTPUT_DIR / out_name

        write_slice(reader, start, end, out_path)
        tag = "" if confirmed == h["div"] else f" (detected {h['div']:02d}→renamed {div_for_name:02d})"
        print(f"✅ {out_name}: pages {start+1}–{end+1}{tag}")
        wrote += 1

    if wrote == 0:
        print("\n❌ Wrote 0 files. If the candidate list looks wrong, try lowering the size threshold or OCRing.")
    else:
        print(f"\n✅ Done. Wrote {wrote} file(s) to:\n{OUTPUT_DIR}")

if __name__ == "__main__":
    main()
