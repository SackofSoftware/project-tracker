"""
Scope Card Aggregator

Aggregates Division 8 scope data from multiple sources into unified scope cards.
Sources include: specifications, drawing schedules, spreadsheets, vendor quotes, and RAG analysis.
"""

import json
from typing import Dict, List, Optional, Any
from pathlib import Path


# =============================================================================
# SCOPE CARD DEFINITIONS
# =============================================================================

SCOPE_CARD_DEFINITIONS = [
    {
        "id": "windows",
        "title": "Windows",
        "icon": "🪟",
        "csi_sections": ["08 51 00", "08 51 13", "08 51 23", "08 52 00"],
        "keywords": ["window", "aluminum window", "vinyl window", "steel window"],
        "data_keys": ["windows", "window"]
    },
    {
        "id": "storefront",
        "title": "Storefront & Curtain Wall",
        "icon": "🏢",
        "csi_sections": ["08 41 00", "08 41 13", "08 42 00", "08 43 00", "08 44 00"],
        "keywords": ["storefront", "curtain wall", "curtainwall", "entrance"],
        "data_keys": ["storefront", "curtain_wall", "curtainwall"]
    },
    {
        "id": "metal_doors",
        "title": "Metal Doors & Frames",
        "icon": "🚪",
        "csi_sections": ["08 11 00", "08 11 13", "08 12 00", "08 14 00"],
        "keywords": ["hollow metal", "steel door", "metal frame", "hm door"],
        "data_keys": ["doors", "metal_doors", "hollow_metal"]
    },
    {
        "id": "hardware",
        "title": "Door Hardware",
        "icon": "🔑",
        "csi_sections": ["08 71 00", "08 74 00", "08 75 00"],
        "keywords": ["hardware", "lockset", "hinges", "closer", "schlage", "von duprin"],
        "data_keys": ["hardware", "door_hardware"]
    },
    {
        "id": "glazing",
        "title": "Glass & Glazing",
        "icon": "🔲",
        "csi_sections": ["08 80 00", "08 81 00", "08 83 00", "08 84 00", "08 85 00", "08 88 00"],
        "keywords": ["glazing", "glass", "tempered", "insulated glass", "igu"],
        "data_keys": ["glazing", "glass"]
    },
    {
        "id": "specialties",
        "title": "Specialties",
        "icon": "✨",
        "csi_sections": ["08 31 00", "08 32 00", "08 34 00", "08 36 00", "08 91 00"],
        "keywords": ["access door", "louver", "grille", "panel", "specialty"],
        "data_keys": ["specialties", "access_doors", "louvers"]
    }
]


class ScopeCardAggregator:
    """
    Aggregates scope data from multiple sources into unified cards.

    Each card shows:
    - Status: specified, not_specified, by_others, pending
    - Data from each source (spec, schedule, spreadsheet, quotes)
    - Summary with best/latest data
    - Confidence level based on source agreement
    - Any conflicts between sources
    """

    def __init__(self, project_id: str, status_tracker=None):
        """
        Initialize aggregator for a project.

        Args:
            project_id: Project identifier
            status_tracker: Optional ProjectStatusTracker instance
        """
        self.project_id = project_id
        self.status_tracker = status_tracker
        self._cache = {}
        self._rag_analysis = None

    def _load_rag_analysis(self, project_data: Dict = None) -> Optional[Dict]:
        """Load RAG analysis data from project folder."""
        if self._rag_analysis is not None:
            return self._rag_analysis

        # Try to get project folder path
        project_path = None

        # Check folder_path and source_id
        if project_data:
            folder_path = project_data.get('folder_path')
            source_id = project_data.get('source_id')

            if folder_path and source_id:
                potential_path = Path(folder_path) / source_id
                if potential_path.exists():
                    project_path = potential_path
            elif folder_path:
                potential_path = Path(folder_path)
                if potential_path.exists():
                    project_path = potential_path

            # Try folder field
            if not project_path:
                folder = project_data.get('folder')
                if folder:
                    folder_path = Path(folder)
                    if folder_path.is_absolute() and folder_path.exists():
                        project_path = folder_path

        if not project_path:
            self._rag_analysis = {}
            return {}

        # Try to load analysis files
        analysis_files = [
            project_path / "division8_analysis.json",
            project_path / "division8_rag_analysis.json"
        ]

        for analysis_file in analysis_files:
            if analysis_file.exists():
                try:
                    with open(analysis_file, 'r') as f:
                        data = json.load(f)
                        # Check if legacy format and convert
                        if self._is_legacy_format(data):
                            data = self._convert_legacy_analysis(data)
                        self._rag_analysis = data
                        return self._rag_analysis
                except Exception:
                    continue

        self._rag_analysis = {}
        return {}

    def _is_legacy_format(self, data: Dict) -> bool:
        """Check if analysis data is in legacy format."""
        # Legacy format has _rag_metadata and no metadata
        return '_rag_metadata' in data and 'metadata' not in data

    def _convert_legacy_analysis(self, legacy: Dict) -> Dict:
        """Convert legacy analysis format to new format."""
        metadata = legacy.get('_rag_metadata', {})

        return {
            "metadata": {
                "project_id": metadata.get('project_id', ''),
                "analyzed_at": metadata.get('generated_at') or metadata.get('analyzed_at', ''),
                "embedder": metadata.get('embedder', 'ollama-nomic-embed-text'),
                "generator": metadata.get('generator', 'unknown'),
                "chunks_analyzed": metadata.get('chunks_analyzed', 0),
                "confidence": legacy.get('confidence', 'medium')
            },
            "summary": {
                "scope_description": legacy.get('scope_summary', ''),
                "key_items": [],
                "total_doors": 0,
                "total_windows": 0,
                "has_storefront": bool(legacy.get('storefront', {}).get('sf_estimate', 0)),
                "has_curtain_wall": False,
                "has_hardware": bool(legacy.get('hardware', {}).get('groups'))
            },
            "doors": {
                "metal_doors_frames": {
                    "specified": legacy.get('doors', {}).get('metal_count') != 'not specified',
                    "count": legacy.get('doors', {}).get('metal_count', 'not specified'),
                    "types": [],
                    "manufacturers": [],
                    "notes": legacy.get('doors', {}).get('notes', [])
                },
                "wood_doors": {
                    "excluded": legacy.get('doors', {}).get('wood_count_excluded', True),
                    "exclusion_note": "Division 6 - by others"
                },
                "aluminum_doors": {"specified": False, "count": "not specified"},
                "access_doors": {"specified": False, "count": "not specified"},
                "automatic_entrances": {"specified": False}
            },
            "windows": {
                "aluminum_windows": {
                    "specified": False,
                    "count": legacy.get('windows', {}).get('count', 'not specified'),
                    "types": legacy.get('windows', {}).get('types', []),
                    "manufacturers": [legacy.get('windows', {}).get('manufacturers', '')] if legacy.get('windows', {}).get('manufacturers') and legacy.get('windows', {}).get('manufacturers') != 'not specified' else [],
                    "notes": legacy.get('windows', {}).get('notes', [])
                },
                "vinyl_windows": {
                    "specified": 'vinyl' in str(legacy.get('windows', {}).get('types', [])).lower(),
                    "count": legacy.get('windows', {}).get('count', 'not specified'),
                    "types": legacy.get('windows', {}).get('types', []),
                    "manufacturers": [],
                    "notes": []
                }
            },
            "storefronts": {
                "specified": bool(legacy.get('storefront', {}).get('sf_estimate', 0)),
                "sf_estimate": legacy.get('storefront', {}).get('sf_estimate', 0),
                "systems": [],
                "manufacturers": [],
                "finish": "",
                "notes": [legacy.get('storefront', {}).get('description', '')] if legacy.get('storefront', {}).get('description') else []
            },
            "curtain_wall": {
                "specified": False,
                "sf_estimate": 0,
                "systems": [],
                "manufacturers": [],
                "notes": []
            },
            "hardware": {
                "specified": bool(legacy.get('hardware', {}).get('groups')),
                "hardware_sets": legacy.get('hardware', {}).get('groups', []),
                "manufacturers": [legacy.get('hardware', {}).get('manufacturers', '')] if legacy.get('hardware', {}).get('manufacturers') and legacy.get('hardware', {}).get('manufacturers') != 'not specified' else [],
                "finish": "",
                "access_control": False,
                "notes": legacy.get('hardware', {}).get('notes', [])
            },
            "glazing": {
                "specified": bool(legacy.get('glass', {}).get('specs')),
                "glass_types": legacy.get('glass', {}).get('specs', []),
                "performance": {},
                "notes": legacy.get('glass', {}).get('notes', [])
            },
            "exclusions": legacy.get('exclusions', []),
            "alternates": [],
            "clarifications_needed": [],
            "source_documents": [],
            "_legacy_converted": True
        }

    def get_all_cards(self, project_data: Dict = None, status_data: Dict = None) -> List[Dict]:
        """
        Get all scope cards with aggregated data.

        Args:
            project_data: Project data dict (from find_project_by_id)
            status_data: Status data dict (from status_tracker.get_status)

        Returns:
            List of scope card dicts
        """
        cards = []

        for definition in SCOPE_CARD_DEFINITIONS:
            card = self._build_card(definition, project_data, status_data)
            cards.append(card)

        return cards

    def get_card(self, card_id: str, project_data: Dict = None, status_data: Dict = None) -> Optional[Dict]:
        """
        Get a single scope card by ID.

        Args:
            card_id: Card identifier (e.g., "windows", "hardware")
            project_data: Project data dict
            status_data: Status data dict

        Returns:
            Scope card dict or None if not found
        """
        definition = next((d for d in SCOPE_CARD_DEFINITIONS if d["id"] == card_id), None)
        if not definition:
            return None

        return self._build_card(definition, project_data, status_data)

    def _build_card(self, definition: Dict, project_data: Dict = None, status_data: Dict = None) -> Dict:
        """Build a scope card from definition and available data."""
        card = {
            "id": definition["id"],
            "title": definition["title"],
            "icon": definition["icon"],
            "csi_sections": definition["csi_sections"],
            "status": "pending",
            "sources": {},
            "summary": {},
            "confidence": "low",
            "conflicts": []
        }

        # Gather data from each source
        spec_data = self._extract_spec_data(definition, project_data, status_data)
        schedule_data = self._extract_schedule_data(definition, project_data, status_data)
        spreadsheet_data = self._extract_spreadsheet_data(definition, status_data)
        quote_data = self._extract_quote_data(definition, status_data)
        rag_data = self._extract_rag_data(definition, project_data)

        # Store source data
        if spec_data:
            card["sources"]["spec"] = spec_data
        if schedule_data:
            card["sources"]["schedule"] = schedule_data
        if spreadsheet_data:
            card["sources"]["spreadsheet"] = spreadsheet_data
        if quote_data:
            card["sources"]["quotes"] = quote_data
        if rag_data:
            card["sources"]["rag"] = rag_data

        # Determine status
        card["status"] = self._determine_status(card, definition, status_data)

        # Build summary from best sources
        card["summary"] = self._build_summary(card)

        # Detect conflicts
        card["conflicts"] = self._detect_conflicts(card)

        # Calculate confidence
        card["confidence"] = self._calculate_confidence(card)

        return card

    def _extract_spec_data(self, definition: Dict, project_data: Dict, status_data: Dict) -> Optional[Dict]:
        """Extract specification data for a scope type."""
        if not status_data:
            return None

        # Check division_8_scope from status
        div8 = status_data.get("division_8_scope", {})

        for key in definition["data_keys"]:
            if key in div8 and div8[key]:
                data = div8[key]
                if isinstance(data, dict):
                    return {
                        "found": True,
                        "section": data.get("spec_section") or definition["csi_sections"][0],
                        "manufacturer": data.get("manufacturer") or data.get("basis_of_design"),
                        "series": data.get("series") or data.get("model"),
                        "material": data.get("material"),
                        "finish": data.get("finish"),
                        "performance": data.get("performance", {}),
                        "source_file": data.get("found_in")
                    }

        # Check extracted_data
        extracted = status_data.get("extracted_data", {}).get("data", {})
        if "division_8" in extracted:
            div8_extracted = extracted["division_8"]
            for key in definition["data_keys"]:
                if key in div8_extracted and div8_extracted[key]:
                    return {
                        "found": True,
                        "data": div8_extracted[key]
                    }

        return None

    def _extract_schedule_data(self, definition: Dict, project_data: Dict, status_data: Dict) -> Optional[Dict]:
        """Extract schedule data (from drawings) for a scope type."""
        if not status_data:
            return None

        # Check openings_schedule from extraction
        schedule = status_data.get("openings_schedule", {})

        card_id = definition["id"]

        if card_id == "windows" and schedule.get("windows"):
            windows = schedule["windows"]
            return {
                "found": True,
                "count": len(windows) if isinstance(windows, list) else windows.get("count"),
                "types": self._extract_types(windows),
                "source_file": schedule.get("source_drawing")
            }

        if card_id in ["metal_doors", "wood_doors"] and schedule.get("doors"):
            doors = schedule["doors"]
            return {
                "found": True,
                "count": len(doors) if isinstance(doors, list) else doors.get("count"),
                "types": self._extract_types(doors),
                "source_file": schedule.get("source_drawing")
            }

        if card_id == "storefront" and schedule.get("storefront"):
            sf = schedule["storefront"]
            return {
                "found": True,
                "count": sf.get("count") if isinstance(sf, dict) else None,
                "sqft": sf.get("sqft") or sf.get("area"),
                "source_file": schedule.get("source_drawing")
            }

        return None

    def _extract_spreadsheet_data(self, definition: Dict, status_data: Dict) -> Optional[Dict]:
        """Extract data from uploaded spreadsheets."""
        if not status_data:
            return None

        # Check for spreadsheet_data in status
        spreadsheet = status_data.get("spreadsheet_data", {})

        card_id = definition["id"]
        if card_id in spreadsheet:
            return {
                "found": True,
                "data": spreadsheet[card_id],
                "uploaded": spreadsheet.get("uploaded_at")
            }

        return None

    def _extract_quote_data(self, definition: Dict, status_data: Dict) -> Optional[Dict]:
        """Extract quote data for a scope type."""
        if not status_data:
            return None

        # Check for quotes in status
        quotes = status_data.get("quotes", [])
        if not quotes:
            return None

        # Filter quotes relevant to this scope
        relevant_quotes = []
        keywords = definition["keywords"]

        for quote in quotes:
            quote_scope = (quote.get("scope", "") or "").lower()
            quote_desc = (quote.get("description", "") or "").lower()

            for kw in keywords:
                if kw in quote_scope or kw in quote_desc:
                    relevant_quotes.append({
                        "vendor": quote.get("vendor"),
                        "amount": quote.get("amount"),
                        "date": quote.get("date")
                    })
                    break

        if relevant_quotes:
            return {
                "found": True,
                "quotes": relevant_quotes,
                "count": len(relevant_quotes),
                "lowest": min((q["amount"] for q in relevant_quotes if q.get("amount")), default=None),
                "highest": max((q["amount"] for q in relevant_quotes if q.get("amount")), default=None)
            }

        return None

    def _extract_rag_data(self, definition: Dict, project_data: Dict) -> Optional[Dict]:
        """Extract RAG analysis data for a scope type."""
        analysis = self._load_rag_analysis(project_data)
        if not analysis:
            return None

        card_id = definition["id"]

        # Map card IDs to analysis sections
        if card_id == "windows":
            windows = analysis.get("windows", {})
            # Check both aluminum and vinyl windows
            for window_type in ["aluminum_windows", "vinyl_windows"]:
                window_data = windows.get(window_type, {})
                if window_data.get("specified"):
                    return {
                        "found": True,
                        "count": window_data.get("count"),
                        "types": window_data.get("types", []),
                        "manufacturers": window_data.get("manufacturers", []),
                        "notes": window_data.get("notes", []),
                        "source": "rag_analysis"
                    }

        elif card_id == "storefront":
            storefronts = analysis.get("storefronts", {})
            curtain_wall = analysis.get("curtain_wall", {})

            if storefronts.get("specified") or curtain_wall.get("specified"):
                sf_estimate = storefronts.get("sf_estimate", 0) + curtain_wall.get("sf_estimate", 0)
                systems = storefronts.get("systems", []) + curtain_wall.get("systems", [])
                manufacturers = storefronts.get("manufacturers", []) + curtain_wall.get("manufacturers", [])
                return {
                    "found": True,
                    "sqft": sf_estimate,
                    "systems": systems,
                    "manufacturers": list(set(manufacturers)),
                    "finish": storefronts.get("finish") or curtain_wall.get("finish"),
                    "notes": storefronts.get("notes", []) + curtain_wall.get("notes", []),
                    "source": "rag_analysis"
                }

        elif card_id == "metal_doors":
            doors = analysis.get("doors", {})
            metal_doors = doors.get("metal_doors_frames", {})
            if metal_doors.get("specified"):
                return {
                    "found": True,
                    "count": metal_doors.get("count"),
                    "types": metal_doors.get("types", []),
                    "manufacturers": metal_doors.get("manufacturers", []),
                    "notes": metal_doors.get("notes", []),
                    "source": "rag_analysis"
                }

        elif card_id == "hardware":
            hardware = analysis.get("hardware", {})
            if hardware.get("specified"):
                return {
                    "found": True,
                    "hardware_sets": hardware.get("hardware_sets", []),
                    "manufacturers": hardware.get("manufacturers", []),
                    "finish": hardware.get("finish"),
                    "access_control": hardware.get("access_control"),
                    "notes": hardware.get("notes", []),
                    "source": "rag_analysis"
                }

        elif card_id == "glazing":
            glazing = analysis.get("glazing", {})
            if glazing.get("specified"):
                return {
                    "found": True,
                    "glass_types": glazing.get("glass_types", []),
                    "performance": glazing.get("performance", {}),
                    "notes": glazing.get("notes", []),
                    "source": "rag_analysis"
                }

        elif card_id == "specialties":
            # Check access doors from doors section
            doors = analysis.get("doors", {})
            access_doors = doors.get("access_doors", {})
            automatic = doors.get("automatic_entrances", {})

            if access_doors.get("specified") or automatic.get("specified"):
                return {
                    "found": True,
                    "access_doors_count": access_doors.get("count"),
                    "automatic_entrances": automatic.get("types", []),
                    "notes": access_doors.get("notes", []) + automatic.get("notes", []),
                    "source": "rag_analysis"
                }

        return None

    def _determine_status(self, card: Dict, definition: Dict, status_data: Dict) -> str:
        """Determine the status of a scope card."""
        # Check if marked as by_others in status
        if status_data:
            by_others = status_data.get("scope_exclusions", [])
            if definition["id"] in by_others:
                return "by_others"

        # Check if we have any data
        has_spec = card["sources"].get("spec", {}).get("found")
        has_schedule = card["sources"].get("schedule", {}).get("found")
        has_spreadsheet = card["sources"].get("spreadsheet", {}).get("found")
        has_quotes = card["sources"].get("quotes", {}).get("found")
        has_rag = card["sources"].get("rag", {}).get("found")

        if has_spec or has_schedule or has_spreadsheet or has_rag:
            return "specified"
        elif has_quotes:
            return "specified"  # Quotes imply specified
        elif definition.get("often_excluded"):
            return "by_others"  # Wood doors often by others
        else:
            return "pending"

    def _build_summary(self, card: Dict) -> Dict:
        """Build a summary from the best available data sources."""
        summary = {}
        sources = card["sources"]

        # Count - prefer spreadsheet > schedule > rag > spec
        if sources.get("spreadsheet", {}).get("data", {}).get("count"):
            summary["count"] = sources["spreadsheet"]["data"]["count"]
            summary["count_source"] = "spreadsheet"
        elif sources.get("schedule", {}).get("count"):
            summary["count"] = sources["schedule"]["count"]
            summary["count_source"] = "schedule"
        elif sources.get("rag", {}).get("count"):
            summary["count"] = sources["rag"]["count"]
            summary["count_source"] = "rag"

        # Manufacturer/Basis of Design - prefer spec, then rag
        if sources.get("spec", {}).get("manufacturer"):
            summary["basis_of_design"] = sources["spec"]["manufacturer"]
            if sources["spec"].get("series"):
                summary["basis_of_design"] += f" {sources['spec']['series']}"
        elif sources.get("rag", {}).get("manufacturers"):
            manufacturers = sources["rag"]["manufacturers"]
            if manufacturers:
                summary["basis_of_design"] = ", ".join(manufacturers[:3])

        # Material/Finish - from spec or rag
        if sources.get("spec", {}).get("material"):
            summary["material"] = sources["spec"]["material"]
        if sources.get("spec", {}).get("finish"):
            summary["finish"] = sources["spec"]["finish"]
        elif sources.get("rag", {}).get("finish"):
            summary["finish"] = sources["rag"]["finish"]

        # Performance - from spec or rag
        if sources.get("spec", {}).get("performance"):
            summary["performance"] = sources["spec"]["performance"]
        elif sources.get("rag", {}).get("performance"):
            summary["performance"] = sources["rag"]["performance"]

        # Types - from rag if available
        if sources.get("rag", {}).get("types"):
            summary["types"] = sources["rag"]["types"]

        # Quote range
        if sources.get("quotes", {}).get("lowest"):
            summary["quote_low"] = sources["quotes"]["lowest"]
            summary["quote_high"] = sources["quotes"]["highest"]

        return summary

    def _detect_conflicts(self, card: Dict) -> List[Dict]:
        """Detect conflicts between data sources."""
        conflicts = []
        sources = card["sources"]

        # Check count conflicts between schedule and spreadsheet
        schedule_count = sources.get("schedule", {}).get("count")
        spreadsheet_count = sources.get("spreadsheet", {}).get("data", {}).get("count")

        if schedule_count and spreadsheet_count and schedule_count != spreadsheet_count:
            conflicts.append({
                "field": "count",
                "sources": ["schedule", "spreadsheet"],
                "values": {"schedule": schedule_count, "spreadsheet": spreadsheet_count},
                "message": f"Count differs: schedule has {schedule_count}, spreadsheet has {spreadsheet_count}"
            })

        return conflicts

    def _calculate_confidence(self, card: Dict) -> str:
        """Calculate confidence level based on data sources and conflicts."""
        sources = card["sources"]
        conflicts = card["conflicts"]

        source_count = sum(1 for s in sources.values() if s.get("found"))

        if conflicts:
            return "low"
        elif source_count >= 3:
            return "high"
        elif source_count >= 2:
            return "medium"
        elif source_count >= 1:
            return "low"
        else:
            return "none"

    def _extract_types(self, data: Any) -> List[str]:
        """Extract type labels from schedule data."""
        if isinstance(data, list):
            types = set()
            for item in data:
                if isinstance(item, dict) and item.get("type"):
                    types.add(item["type"])
            return sorted(types)
        elif isinstance(data, dict) and data.get("types"):
            return data["types"]
        return []


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

def get_scope_cards(project_id: str, project_data: Dict = None, status_data: Dict = None) -> List[Dict]:
    """
    Convenience function to get all scope cards for a project.

    Args:
        project_id: Project identifier
        project_data: Optional project data dict
        status_data: Optional status data dict

    Returns:
        List of scope card dicts
    """
    aggregator = ScopeCardAggregator(project_id)
    return aggregator.get_all_cards(project_data, status_data)


def get_card_definitions() -> List[Dict]:
    """Get the scope card definitions."""
    return SCOPE_CARD_DEFINITIONS
