"""
Brief generation module with CSI Masterformat integration.
"""
from .prompt_builder import (
    build_division8_brief,
    build_brief_prompt,
    get_section_description,
    load_division_context,
    load_manufacturer_specs
)

__all__ = [
    'build_division8_brief',
    'build_brief_prompt',
    'get_section_description',
    'load_division_context',
    'load_manufacturer_specs'
]
