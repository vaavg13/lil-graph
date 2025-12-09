"""
Shallow re-exports of core domain types for easier imports.
"""

from ..indexing.models import GraphNode, NodeType
from ..pipeline_types import CitationDescriptor, SinglePaperResult
from ..settings import PipelineSettings

__all__ = [
    "GraphNode",
    "NodeType",
    "CitationDescriptor",
    "SinglePaperResult",
    "PipelineSettings",
]
