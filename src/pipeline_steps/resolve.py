from typing import Dict, List
from ..resolution.crossref import CrossRefResolver
from ..indexing.models import PaperNode
from ..pipeline_types import LogEntry

def resolve_citations(nodes: Dict[str, PaperNode], logs: List[LogEntry]):
    try:
        resolver = CrossRefResolver()
        resolver.resolve_citations(nodes)
        logs.append(("ok", "Resolved citations via CrossRef"))
    except Exception as res_exc:
        logs.append(("warn", f"Citation resolution failed or partial: {res_exc}"))

