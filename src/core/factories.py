from typing import List, Optional, Tuple

from ..indexing.models import GraphNode
from ..pipeline_steps.download import download_content
from ..resolution.crossref import CrossRefResolver
from ..settings import PipelineSettings
from .ports import IngestionPort, ResolutionPort


class ArxivIngestion(IngestionPort):
    def download_and_extract(
        self, arxiv_id: str, base_dir: str, logs: List[Tuple[str, str]]
    ) -> Tuple[str, Optional[str], Optional[str], Optional[str], Optional[str]]:
        return download_content(arxiv_id, base_dir, logs)


class CrossRefResolution(ResolutionPort):
    def __init__(self, email: str, delay: float, timeout: int):
        self._resolver = CrossRefResolver(email=email, delay=delay, timeout=timeout)

    def resolve(self, nodes: dict[str, GraphNode], logs: Optional[List[Tuple[str, str]]] = None) -> None:
        # logs handling is inside resolver
        self._resolver.resolve_citations(nodes)


def get_ingestion_port(settings: PipelineSettings) -> IngestionPort:
    if settings.ingestion_backend == "arxiv":
        return ArxivIngestion()
    raise ValueError(f"Unsupported ingestion backend: {settings.ingestion_backend}")


def get_resolution_port(settings: PipelineSettings) -> ResolutionPort:
    if settings.resolution_backend == "crossref":
        return CrossRefResolution(
            email=settings.crossref_email,
            delay=settings.crossref_delay,
            timeout=settings.crossref_timeout,
        )
    raise ValueError(f"Unsupported resolution backend: {settings.resolution_backend}")
