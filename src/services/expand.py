from typing import Any, Optional

from ..citation_expansion import run_parallel_pipeline
from ..indexing.graph.interface import GraphStore
from ..settings import PipelineSettings


def expand_citations(
    root_identifier: str,
    base_dir: str,
    max_depth: int,
    workers: int = 4,
    settings: Optional[PipelineSettings] = None,
    graph_store: Optional[GraphStore] = None,
    **kwargs: Any,
):
    """
    Expand citations level-wise starting from a root identifier.
    """
    cfg = settings or PipelineSettings.from_env()
    return run_parallel_pipeline(
        root_identifier,
        base_dir,
        max_depth,
        workers=workers,
        settings=cfg,
        graph_store=graph_store,
        **kwargs,
    )
