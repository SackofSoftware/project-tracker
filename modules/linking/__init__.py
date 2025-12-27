"""
Project Source Linking Module

Provides unified matching and linking for external project sources
(PlanHub, ProjectDog, Email, GovWin) to canonical local projects.
"""

from .base_matcher import BaseProjectMatcher
from .link_service import ProjectLinkService

__all__ = ['BaseProjectMatcher', 'ProjectLinkService']
