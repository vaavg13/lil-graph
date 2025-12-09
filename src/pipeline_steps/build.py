from typing import Dict, Optional, List, Any
from ..indexing.node_builder import build_nodes_from_parsed_data
from ..indexing.models import GraphNode
from ..pipeline_types import PipelineError, LogEntry

def build_nodes(
    arxiv_id: str,
    parsed_data: Dict[str, Any],
    paper_title: Optional[str],
    published_date: Optional[str],
    updated_date: Optional[str],
    merge_section_chunks: bool,
    logs: List[LogEntry]
) -> Dict[str, GraphNode]:
    try:
        nodes = build_nodes_from_parsed_data(
            arxiv_id, 
            parsed_data, 
            paper_title=paper_title,
            published_date=published_date,
            updated_date=updated_date,
            merge_section_chunks=merge_section_chunks,
        )
        node_count = len(nodes)
        logs.append(("ok", f"Constructed {node_count} graph nodes"))
        if node_count <= 1:
            logs.append(("error", "Only root node constructed; parsed content may be empty"))
            raise PipelineError("Graph construction failed: no content nodes", logs)
        return nodes
    except Exception as exc:
        logs.append(("error", f"Node construction failed: {exc}"))
        raise PipelineError(f"Node construction failed: {exc}", logs)

