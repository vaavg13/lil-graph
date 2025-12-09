from typing import Any, Dict, List, Optional, Protocol, Tuple

from ..indexing.models import GraphNode


class IngestionPort(Protocol):
    def download_and_extract(
        self, arxiv_id: str, base_dir: str, logs: List[Tuple[str, str]]
    ) -> Tuple[str, Optional[str], Optional[str], Optional[str], Optional[str]]:
        ...


class ResolutionPort(Protocol):
    def resolve(self, nodes: Dict[str, GraphNode], logs: Optional[List[Tuple[str, str]]] = None) -> None:
        ...
