"""
Project Numbering Module

Manages project lifecycle tracking with prefixed sequential numbers.

Prefixes:
- B = Bidding (active bids in progress)
- L = Lead (early stage/forecasting)
- O = Opportunity (potential, not yet qualified)
- A = Awarded (won)
- X = Lost/Not Bid/Gone
"""

from .project_numbering import ProjectNumberingService

__all__ = ['ProjectNumberingService']
