"""
Service layer entry points for ingest, expansion, and queries.
"""

from .ingest import ingest_paper
from .expand import expand_citations
from .query import get_neighborhood

__all__ = ["ingest_paper", "expand_citations", "get_neighborhood"]
