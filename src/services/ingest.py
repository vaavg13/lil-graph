from typing import Any, Optional

from ..indexing.graph.interface import GraphStore
from ..settings import PipelineSettings
from ..single_paper import run_single_paper


def ingest_paper(
    identifier: str,
    base_dir: str,
    settings: Optional[PipelineSettings] = None,
    graph_store: Optional[GraphStore] = None,
    **kwargs: Any,
):
    """
    Ingest a single paper: resolve -> download -> parse -> build -> persist.
    """
    cfg = settings or PipelineSettings.from_env()
    return run_single_paper(
        identifier,
        base_dir,
        settings=cfg,
        graph_store=graph_store,
        **kwargs,
    )
