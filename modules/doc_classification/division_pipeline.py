"""High-level helpers for assembling division summaries across multiple PDFs."""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Dict, Iterable, List, Optional

import pandas as pd

from .division_extractor import DivisionContent, extract_divisions_from_pdf


def summarize_terms(texts, top_n: int = 20):
    """
    Simple term frequency extraction from text series.

    Args:
        texts: Pandas Series or iterable of text strings
        top_n: Number of top terms to return

    Returns:
        List of top terms by frequency
    """
    from collections import Counter
    import re

    # Common stop words to filter out
    stop_words = {
        'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for',
        'of', 'with', 'by', 'from', 'as', 'is', 'was', 'are', 'were', 'been',
        'be', 'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would',
        'could', 'should', 'may', 'might', 'must', 'shall', 'can', 'need',
        'this', 'that', 'these', 'those', 'it', 'its', 'all', 'each', 'every',
        'both', 'few', 'more', 'most', 'other', 'some', 'such', 'no', 'nor',
        'not', 'only', 'own', 'same', 'so', 'than', 'too', 'very', 'just',
        'section', 'part', 'see', 'refer', 'per', 'also', 'any', 'new'
    }

    word_counts = Counter()

    for text in texts:
        if not isinstance(text, str):
            continue
        # Extract words (alphanumeric, 3+ chars)
        words = re.findall(r'\b[a-zA-Z]{3,}\b', text.lower())
        # Filter stop words
        words = [w for w in words if w not in stop_words]
        word_counts.update(words)

    return [word for word, count in word_counts.most_common(top_n)]


def gather_division_content(
    pdf_paths: Iterable[Path],
    division: str,
    max_pages: Optional[int] = None,
) -> Dict[str, DivisionContent]:
    """Merge division content from multiple specification PDFs."""
    division_code = division.zfill(2)
    merged: Dict[str, DivisionContent] = {}

    for pdf_path in pdf_paths:
        divisions = extract_divisions_from_pdf(pdf_path, target_divisions=[division_code], max_pages=max_pages)
        if division_code not in divisions:
            continue
        content = divisions[division_code]
        if division_code not in merged:
            merged[division_code] = content
        else:
            existing = merged[division_code]
            existing.sections.extend(content.sections)
            if existing.start_page is None or (content.start_page and content.start_page < existing.start_page):
                existing.start_page = content.start_page
            if existing.end_page is None or (content.end_page and content.end_page > existing.end_page):
                existing.end_page = content.end_page
            if not existing.title and content.title:
                existing.title = content.title

    return merged


def build_division_dataframe(content: DivisionContent) -> pd.DataFrame:
    """Convert division sections into a dataframe for downstream analysis."""
    records = [
        {
            "section_id": section.section_id,
            "title": section.title,
            "page": section.page,
            "excerpt": section.excerpt,
        }
        for section in content.sections
    ]
    return pd.DataFrame(records)


def summarize_division_content(content: DivisionContent) -> Dict[str, object]:
    """Produce a structured summary for a division."""
    summary = {
        "division": content.division,
        "title": content.title,
        "start_page": content.start_page,
        "end_page": content.end_page,
        "section_count": len(content.sections),
    }
    df = build_division_dataframe(content)
    if not df.empty:
        terms = summarize_terms(df["excerpt"])
        summary["top_terms"] = terms[:10]
    return summary


__all__ = ["gather_division_content", "build_division_dataframe", "summarize_division_content"]
