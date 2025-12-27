"""
Gov Leads Integration Module

Reads government leads from the GovWin SQLite database.

Source: Configured via GOV_DB_PATH environment variable

Entity Types:
- BID = Active procurement opportunities with response dates
- LEAD = Forecasted opportunities from Capital Improvement Plans
"""

from .govleads_reader import GovLeadsReader, GovLeadRecord, GovDocument

__all__ = ['GovLeadsReader', 'GovLeadRecord', 'GovDocument']
