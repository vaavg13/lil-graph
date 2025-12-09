from typing import Dict, List, Optional, Protocol

from ..domain.nodes import GraphNode

LogEntry = tuple[str, str]


class ResolutionPort(Protocol):
    """
    Port for resolving citation metadata (CrossRef, etc.).
    """

    def resolve(self, nodes: Dict[str, GraphNode], logs: Optional[List[LogEntry]] = None) -> None:
        ...
