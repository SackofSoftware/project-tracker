"""
Stage 6: Schedule Parsing

Parses AI analysis results into structured schedule data.
Extracts door, window, storefront, and hardware information.
"""

import re
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
import json
import logging

logger = logging.getLogger(__name__)


@dataclass
class StageResult:
    """Result from a pipeline stage"""
    success: bool
    data: Dict
    error: Optional[str] = None


@dataclass
class DoorEntry:
    """Parsed door schedule entry"""
    mark: str
    type_code: str = ""
    material: str = ""  # HM, wood, aluminum, etc.
    width: float = 0
    height: float = 0
    thickness: float = 0
    fire_rating: str = ""
    hardware_set: str = ""
    frame_type: str = ""
    notes: str = ""
    is_metal: bool = False
    is_wood: bool = False
    is_division_8: bool = False

    def to_dict(self) -> Dict:
        return {
            'mark': self.mark,
            'type_code': self.type_code,
            'material': self.material,
            'size': f"{self.width}x{self.height}",
            'fire_rating': self.fire_rating,
            'hardware_set': self.hardware_set,
            'frame_type': self.frame_type,
            'notes': self.notes,
            'is_metal': self.is_metal,
            'is_wood': self.is_wood,
            'is_division_8': self.is_division_8,
        }


@dataclass
class WindowEntry:
    """Parsed window schedule entry"""
    mark: str
    type_code: str = ""
    material: str = ""  # aluminum, wood, vinyl, etc.
    width: float = 0
    height: float = 0
    operation: str = ""  # fixed, casement, awning, etc.
    glazing: str = ""
    frame_finish: str = ""
    hardware: str = ""
    notes: str = ""

    def to_dict(self) -> Dict:
        return {
            'mark': self.mark,
            'type_code': self.type_code,
            'material': self.material,
            'size': f"{self.width}x{self.height}",
            'operation': self.operation,
            'glazing': self.glazing,
            'frame_finish': self.frame_finish,
            'hardware': self.hardware,
            'notes': self.notes,
        }


class ScheduleParseStage:
    """
    Stage 6: Schedule Parsing

    Takes AI analysis results and parses them into
    structured schedule data for doors, windows, etc.
    """

    # Material classification
    METAL_MATERIALS = [
        'hm', 'hollow metal', 'hollow-metal',
        'aluminum', 'alum', 'al',
        'steel', 'stainless', 'ss',
        'bronze', 'brass',
    ]

    WOOD_MATERIALS = [
        'wood', 'wd', 'flush wood',
        'stile and rail', 'stile & rail',
        'oak', 'maple', 'birch', 'mahogany',
    ]

    def __init__(self, project_folder: Path, ai_provider=None):
        self.project_folder = Path(project_folder)
        self.ai = ai_provider

    async def run(self, ai_analysis_data: Dict = None) -> StageResult:
        """
        Execute the schedule parsing stage.

        Args:
            ai_analysis_data: Results from Stage 5 (AI Analysis)
        """
        try:
            # Load AI analysis data if not provided
            if ai_analysis_data is None:
                ai_analysis_data = self._load_analysis_data()

            if not ai_analysis_data:
                return StageResult(
                    success=True,
                    data={'message': 'No AI analysis data to parse'},
                )

            # Parse door schedules
            doors = self._parse_door_schedule(ai_analysis_data.get('door_schedule', {}))
            logger.info(f"[ScheduleParse] Parsed {len(doors)} door entries")

            # Parse window schedules
            windows = self._parse_window_schedule(ai_analysis_data.get('window_schedule', {}))
            logger.info(f"[ScheduleParse] Parsed {len(windows)} window entries")

            # Parse storefront/curtain wall
            storefront = self._parse_storefront(ai_analysis_data.get('storefront', {}))
            hardware = self._parse_hardware(ai_analysis_data.get('hardware', {}))

            # Calculate summary statistics
            metal_doors = [d for d in doors if d.is_metal]
            wood_doors = [d for d in doors if d.is_wood]
            div8_doors = [d for d in doors if d.is_division_8]

            # Save parsed data
            output_file = self.project_folder / 'Extracted-Data' / 'parsed_schedules.json'
            output_file.parent.mkdir(parents=True, exist_ok=True)

            parsed_data = {
                'doors': [d.to_dict() for d in doors],
                'windows': [w.to_dict() for w in windows],
                'storefront': storefront,
                'hardware': hardware,
                'summary': {
                    'total_doors': len(doors),
                    'metal_doors': len(metal_doors),
                    'wood_doors': len(wood_doors),
                    'division_8_doors': len(div8_doors),
                    'total_windows': len(windows),
                    'storefront_systems': len(storefront),
                }
            }

            with open(output_file, 'w') as f:
                json.dump(parsed_data, f, indent=2)

            return StageResult(
                success=True,
                data={
                    'door_entries': len(doors),
                    'window_entries': len(windows),
                    'storefront_entries': len(storefront),
                    'metal_doors': len(metal_doors),
                    'wood_doors_excluded': len(wood_doors),
                    'output_file': str(output_file),
                }
            )

        except Exception as e:
            logger.error(f"[ScheduleParse] Error: {e}")
            return StageResult(
                success=False,
                data={},
                error=str(e)
            )

    def _load_analysis_data(self) -> Optional[Dict]:
        """Load AI analysis data from previous stage"""
        data_file = self.project_folder / 'Extracted-Data' / 'ai_analysis.json'
        if data_file.exists():
            with open(data_file, 'r') as f:
                return json.load(f)
        return None

    def _parse_door_schedule(self, door_data: Any) -> List[DoorEntry]:
        """Parse door schedule from AI analysis"""
        doors = []

        # Handle different input formats
        entries = []
        if isinstance(door_data, dict):
            entries = door_data.get('entries', [])
        elif isinstance(door_data, list):
            entries = door_data

        for entry in entries:
            if isinstance(entry, dict):
                door = DoorEntry(
                    mark=str(entry.get('mark', entry.get('number', ''))),
                    type_code=str(entry.get('type', entry.get('type_code', ''))),
                    material=str(entry.get('material', '')),
                    width=self._parse_dimension(entry.get('width', 0)),
                    height=self._parse_dimension(entry.get('height', 0)),
                    thickness=self._parse_dimension(entry.get('thickness', 0)),
                    fire_rating=str(entry.get('fire_rating', entry.get('rating', ''))),
                    hardware_set=str(entry.get('hardware_set', entry.get('hw_set', ''))),
                    frame_type=str(entry.get('frame', entry.get('frame_type', ''))),
                    notes=str(entry.get('notes', entry.get('remarks', ''))),
                )

                # Classify material
                door.is_metal = self._is_metal_material(door.material)
                door.is_wood = self._is_wood_material(door.material)
                door.is_division_8 = door.is_metal  # Metal doors are Division 8

                doors.append(door)

        return doors

    def _parse_window_schedule(self, window_data: Any) -> List[WindowEntry]:
        """Parse window schedule from AI analysis"""
        windows = []

        entries = []
        if isinstance(window_data, dict):
            entries = window_data.get('entries', [])
        elif isinstance(window_data, list):
            entries = window_data

        for entry in entries:
            if isinstance(entry, dict):
                window = WindowEntry(
                    mark=str(entry.get('mark', entry.get('number', ''))),
                    type_code=str(entry.get('type', entry.get('type_code', ''))),
                    material=str(entry.get('material', entry.get('frame_material', ''))),
                    width=self._parse_dimension(entry.get('width', 0)),
                    height=self._parse_dimension(entry.get('height', 0)),
                    operation=str(entry.get('operation', entry.get('type', ''))),
                    glazing=str(entry.get('glazing', entry.get('glass', ''))),
                    frame_finish=str(entry.get('finish', entry.get('frame_finish', ''))),
                    hardware=str(entry.get('hardware', '')),
                    notes=str(entry.get('notes', entry.get('remarks', ''))),
                )
                windows.append(window)

        return windows

    def _parse_storefront(self, storefront_data: Any) -> List[Dict]:
        """Parse storefront/curtain wall data"""
        systems = []

        if isinstance(storefront_data, dict):
            entries = storefront_data.get('systems', storefront_data.get('entries', []))
        elif isinstance(storefront_data, list):
            entries = storefront_data
        else:
            entries = []

        for entry in entries:
            if isinstance(entry, dict):
                systems.append({
                    'type': entry.get('type', 'Storefront'),
                    'manufacturer': entry.get('manufacturer', ''),
                    'series': entry.get('series', ''),
                    'finish': entry.get('finish', ''),
                    'glazing': entry.get('glazing', ''),
                    'locations': entry.get('locations', []),
                    'notes': entry.get('notes', ''),
                })

        return systems

    def _parse_hardware(self, hardware_data: Any) -> List[Dict]:
        """Parse hardware schedule/sets"""
        hardware = []

        if isinstance(hardware_data, dict):
            entries = hardware_data.get('sets', hardware_data.get('entries', []))
        elif isinstance(hardware_data, list):
            entries = hardware_data
        else:
            entries = []

        for entry in entries:
            if isinstance(entry, dict):
                hardware.append({
                    'set_number': entry.get('set', entry.get('set_number', '')),
                    'description': entry.get('description', ''),
                    'items': entry.get('items', []),
                    'doors': entry.get('doors', []),
                })

        return hardware

    def _parse_dimension(self, value: Any) -> float:
        """Parse dimension value to float"""
        if isinstance(value, (int, float)):
            return float(value)

        if isinstance(value, str):
            # Try to extract numeric value
            match = re.search(r'(\d+(?:\.\d+)?)', value)
            if match:
                return float(match.group(1))

        return 0.0

    def _is_metal_material(self, material: str) -> bool:
        """Check if material is metal (Division 8 scope)"""
        material_lower = material.lower()
        return any(m in material_lower for m in self.METAL_MATERIALS)

    def _is_wood_material(self, material: str) -> bool:
        """Check if material is wood (Division 6 - exclusion)"""
        material_lower = material.lower()
        return any(m in material_lower for m in self.WOOD_MATERIALS)
