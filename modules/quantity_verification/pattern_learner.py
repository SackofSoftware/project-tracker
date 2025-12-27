"""
Pattern Learner for Quantity Verification

Uses AI to extract tag patterns from door/window schedule PDFs.
Handles inconsistent formats across projects:
- Single letters: A, B, C
- Letter-number: W1, W2, D1
- Prefixed: WIN-A, WIN-1, DOOR-A
- Type-based: Type 1, Type A, T-1
- Hardware mark: HM-1, HM-A

Returns detected patterns for user confirmation before scanning.
"""

import re
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
import fitz  # PyMuPDF

logger = logging.getLogger(__name__)


@dataclass
class TagPattern:
    """A detected tag pattern from schedule analysis"""
    pattern_id: str           # Unique ID for this pattern
    category: str             # 'door', 'window', 'hardware', 'frame'
    examples: List[str]       # Actual tags found: ['A', 'B', 'C']
    regex: str                # Regex to match this pattern
    source_file: str          # Schedule PDF this came from
    confidence: float = 0.0   # AI confidence in pattern detection
    quantity: int = 0         # Count from schedule if available


@dataclass
class LearningResult:
    """Result from pattern learning"""
    success: bool
    door_patterns: List[TagPattern] = field(default_factory=list)
    window_patterns: List[TagPattern] = field(default_factory=list)
    hardware_patterns: List[TagPattern] = field(default_factory=list)
    raw_response: str = ""
    error: Optional[str] = None


class PatternLearner:
    """
    Learns tag patterns from schedule PDFs using AI.

    Uses the project's schedule documents (door schedules, window schedules)
    to identify the tagging convention used. Different projects use different
    formats, so this learns from the actual schedule content.
    """

    # Common schedule sheet prefixes in architectural drawings
    SCHEDULE_SHEET_PREFIXES = ['A5', 'A6', 'A7', 'A8', 'A9']

    # Common schedule file name patterns
    SCHEDULE_FILE_PATTERNS = [
        r'door.*schedule', r'window.*schedule', r'hardware.*schedule',
        r'schedule.*door', r'schedule.*window', r'schedule.*hardware',
        r'd[0-9]+.*schedule', r'w[0-9]+.*schedule',
    ]

    def __init__(self, ai_provider=None):
        """
        Initialize pattern learner.

        Args:
            ai_provider: AIProviderManager instance for AI-assisted learning
        """
        self.ai = ai_provider

    async def learn_patterns(self, project_folder: Path) -> LearningResult:
        """
        Learn tag patterns from schedule documents in project folder.

        Args:
            project_folder: Path to project folder

        Returns:
            LearningResult with detected patterns
        """
        logger.info(f"[PatternLearner] Learning patterns from: {project_folder.name}")

        # Find schedule documents
        schedule_pdfs = self._find_schedule_documents(project_folder)

        if not schedule_pdfs:
            logger.warning("[PatternLearner] No schedule documents found")
            return LearningResult(
                success=False,
                error="No schedule documents found in project folder"
            )

        logger.info(f"[PatternLearner] Found {len(schedule_pdfs)} schedule document(s)")

        # Extract text from schedules
        schedule_texts = {}
        for pdf_path in schedule_pdfs:
            text = self._extract_pdf_text(pdf_path)
            if text:
                schedule_texts[pdf_path.name] = text

        if not schedule_texts:
            return LearningResult(
                success=False,
                error="Could not extract text from schedule documents"
            )

        # Use AI to learn patterns if available
        if self.ai and self.ai.has_unified_pipeline:
            return await self._learn_with_ai(schedule_texts)
        else:
            # Fallback to regex-based pattern detection
            return self._learn_with_regex(schedule_texts)

    def _find_schedule_documents(self, project_folder: Path) -> List[Path]:
        """Find schedule documents in project folder"""
        schedule_pdfs = []

        # Search in Schedules folder first
        schedules_folder = project_folder / 'Schedules'
        if schedules_folder.exists():
            schedule_pdfs.extend(schedules_folder.glob("*.pdf"))

        # Search in Drawings/Architectural for A5xx-A9xx sheets
        arch_folder = project_folder / 'Drawings' / 'Architectural'
        if arch_folder.exists():
            for pdf in arch_folder.glob("*.pdf"):
                name_upper = pdf.stem.upper()
                # Check for schedule sheet prefixes
                if any(name_upper.startswith(prefix) for prefix in self.SCHEDULE_SHEET_PREFIXES):
                    schedule_pdfs.append(pdf)
                # Check for schedule in filename
                elif 'schedule' in pdf.stem.lower():
                    schedule_pdfs.append(pdf)

        # Search root folder for schedule files
        for pdf in project_folder.glob("*.pdf"):
            name_lower = pdf.stem.lower()
            for pattern in self.SCHEDULE_FILE_PATTERNS:
                if re.search(pattern, name_lower, re.IGNORECASE):
                    if pdf not in schedule_pdfs:
                        schedule_pdfs.append(pdf)

        return schedule_pdfs

    def _extract_pdf_text(self, pdf_path: Path, max_pages: int = 5) -> str:
        """Extract text from PDF"""
        try:
            with fitz.open(str(pdf_path)) as doc:
                text_parts = []
                for i in range(min(max_pages, len(doc))):
                    text = doc[i].get_text()
                    if text.strip():
                        text_parts.append(text)
                return "\n".join(text_parts)
        except Exception as e:
            logger.warning(f"[PatternLearner] Failed to extract text from {pdf_path.name}: {e}")
            return ""

    async def _learn_with_ai(self, schedule_texts: Dict[str, str]) -> LearningResult:
        """Use AI to learn patterns from schedule text"""
        combined_text = "\n\n---\n\n".join([
            f"=== {name} ===\n{text}"
            for name, text in schedule_texts.items()
        ])

        prompt = """Analyze these construction schedule documents and extract the tag/mark patterns used.

Look for:
1. DOOR TAGS: The marks/numbers used to identify doors (e.g., A, B, 101, D1, HM-1, etc.)
2. WINDOW TAGS: The marks/numbers used to identify windows (e.g., W1, W2, WIN-A, Type 1, etc.)
3. HARDWARE TAGS: Hardware set identifiers (e.g., HS-1, HW-A, Set 1, etc.)

For each category found, provide:
- The pattern type (letter, number, letter-number, prefixed)
- All unique tags found
- A regex pattern that matches them
- The source document

Return JSON:
{
    "door_patterns": [
        {
            "pattern_type": "letter",
            "tags": ["A", "B", "C"],
            "regex": "[A-Z]",
            "source": "Door Schedule.pdf",
            "quantity_found": 3
        }
    ],
    "window_patterns": [...],
    "hardware_patterns": [...]
}"""

        result = await self.ai.unified_query(
            prompt=prompt,
            context=combined_text,
            system_prompt="You are a construction document analyst. Extract tag patterns accurately.",
            max_tokens=4096
        )

        if not result.success:
            logger.error(f"[PatternLearner] AI learning failed: {result.error}")
            return self._learn_with_regex(schedule_texts)

        # Parse AI response
        try:
            data = result.data
            door_patterns = self._parse_ai_patterns(data.get('door_patterns', []), 'door')
            window_patterns = self._parse_ai_patterns(data.get('window_patterns', []), 'window')
            hardware_patterns = self._parse_ai_patterns(data.get('hardware_patterns', []), 'hardware')

            return LearningResult(
                success=True,
                door_patterns=door_patterns,
                window_patterns=window_patterns,
                hardware_patterns=hardware_patterns,
                raw_response=result.raw_response or ""
            )
        except Exception as e:
            logger.error(f"[PatternLearner] Failed to parse AI response: {e}")
            return self._learn_with_regex(schedule_texts)

    def _parse_ai_patterns(self, patterns_data: List[Dict], category: str) -> List[TagPattern]:
        """Parse AI-generated pattern data"""
        patterns = []
        for i, p in enumerate(patterns_data):
            patterns.append(TagPattern(
                pattern_id=f"{category}_{i}",
                category=category,
                examples=p.get('tags', []),
                regex=p.get('regex', r'\w+'),
                source_file=p.get('source', 'unknown'),
                confidence=0.9,  # AI patterns have high confidence
                quantity=p.get('quantity_found', 0)
            ))
        return patterns

    def _learn_with_regex(self, schedule_texts: Dict[str, str]) -> LearningResult:
        """Fallback regex-based pattern learning"""
        logger.info("[PatternLearner] Using regex-based pattern detection")

        door_patterns = []
        window_patterns = []
        hardware_patterns = []

        for source_file, text in schedule_texts.items():
            # Detect door patterns
            door_tags = self._detect_door_patterns(text)
            if door_tags:
                door_patterns.append(TagPattern(
                    pattern_id=f"door_{len(door_patterns)}",
                    category='door',
                    examples=door_tags,
                    regex=self._build_regex_from_examples(door_tags),
                    source_file=source_file,
                    confidence=0.7,
                    quantity=len(door_tags)
                ))

            # Detect window patterns
            window_tags = self._detect_window_patterns(text)
            if window_tags:
                window_patterns.append(TagPattern(
                    pattern_id=f"window_{len(window_patterns)}",
                    category='window',
                    examples=window_tags,
                    regex=self._build_regex_from_examples(window_tags),
                    source_file=source_file,
                    confidence=0.7,
                    quantity=len(window_tags)
                ))

            # Detect hardware patterns
            hardware_tags = self._detect_hardware_patterns(text)
            if hardware_tags:
                hardware_patterns.append(TagPattern(
                    pattern_id=f"hardware_{len(hardware_patterns)}",
                    category='hardware',
                    examples=hardware_tags,
                    regex=self._build_regex_from_examples(hardware_tags),
                    source_file=source_file,
                    confidence=0.6,
                    quantity=len(hardware_tags)
                ))

        return LearningResult(
            success=len(door_patterns) > 0 or len(window_patterns) > 0,
            door_patterns=door_patterns,
            window_patterns=window_patterns,
            hardware_patterns=hardware_patterns
        )

    def _detect_door_patterns(self, text: str) -> List[str]:
        """Detect door tag patterns in text"""
        patterns = [
            # DOOR MARK column patterns
            r'(?:DOOR|MARK|NO\.?)\s*[:=]?\s*([A-Z](?:\d{0,3})?)(?:\s|$)',
            # Letter-only tags in context
            r'(?:TYPE|MARK)\s+([A-Z])(?:\s|,|$)',
            # Numbered doors
            r'(?:DOOR|DR)\s*(?:#|NO\.?)?\s*(\d{1,4})',
            # HM doors
            r'(HM-?\d+)',
        ]

        tags = set()
        for pattern in patterns:
            matches = re.findall(pattern, text, re.IGNORECASE | re.MULTILINE)
            tags.update(matches)

        return sorted(list(tags))

    def _detect_window_patterns(self, text: str) -> List[str]:
        """Detect window tag patterns in text"""
        patterns = [
            # W1, W2 style
            r'\b(W-?\d{1,3})\b',
            # WIN-A, WIN-1 style
            r'\b(WIN-?[A-Z0-9]+)\b',
            # Type 1, Type A
            r'TYPE\s+([A-Z0-9]+)',
            # Single letter in window context
            r'(?:WINDOW|WIN)\s*(?:MARK|TYPE)?\s*[:=]?\s*([A-Z])(?:\s|$)',
        ]

        tags = set()
        for pattern in patterns:
            matches = re.findall(pattern, text, re.IGNORECASE | re.MULTILINE)
            tags.update(matches)

        return sorted(list(tags))

    def _detect_hardware_patterns(self, text: str) -> List[str]:
        """Detect hardware tag patterns in text"""
        patterns = [
            # HS-1, HW-A style
            r'\b(H[SW]-?\d+)\b',
            r'\b(H[SW]-?[A-Z])\b',
            # Set 1, Set A
            r'SET\s+(\d+|[A-Z])',
            # Hardware group
            r'(?:HARDWARE|HDWR)\s*(?:SET|GROUP)?\s*[:=]?\s*([A-Z0-9]+)',
        ]

        tags = set()
        for pattern in patterns:
            matches = re.findall(pattern, text, re.IGNORECASE | re.MULTILINE)
            tags.update(matches)

        return sorted(list(tags))

    def _build_regex_from_examples(self, examples: List[str]) -> str:
        """Build a regex pattern from example tags"""
        if not examples:
            return r'\w+'

        # Analyze pattern structure
        all_letters = all(re.match(r'^[A-Z]$', e, re.IGNORECASE) for e in examples)
        all_numbers = all(re.match(r'^\d+$', e) for e in examples)
        has_prefix = any('-' in e for e in examples)

        if all_letters:
            return r'[A-Z]'
        elif all_numbers:
            return r'\d{1,4}'
        elif has_prefix:
            # Find common prefix
            prefixes = set(e.split('-')[0] for e in examples if '-' in e)
            if len(prefixes) == 1:
                prefix = list(prefixes)[0]
                return rf'{prefix}-[A-Z0-9]+'

        # Fallback: escape and join with OR
        escaped = [re.escape(e) for e in examples]
        return '|'.join(escaped)
