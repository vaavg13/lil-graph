from typing import Dict, List, Optional

from ..indexing.models import GraphNode
from ..pipeline_types import LogEntry
from ..resolution.crossref import CrossRefResolver
from ..settings import PipelineSettings


def resolve_citations(
    nodes: Dict[str, GraphNode],
    logs: List[LogEntry],
    settings: Optional[PipelineSettings] = None,
):
    try:
        cfg = settings or PipelineSettings.from_env()
        resolver = CrossRefResolver(
            email=cfg.crossref_email,
            delay=cfg.crossref_delay,
            timeout=cfg.crossref_timeout,
        )
        resolver.resolve_citations(nodes)
        logs.append(("ok", "Resolved citations via CrossRef"))
    except Exception as res_exc:
        logs.append(("warn", f"Citation resolution failed or partial: {res_exc}"))

