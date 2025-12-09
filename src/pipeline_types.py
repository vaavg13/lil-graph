from dataclasses import dataclass
from typing import List, Optional, Tuple, Dict, Any


LogEntry = Tuple[str, str]


class PipelineError(RuntimeError):
    def __init__(self, message: str, logs: Optional[List[LogEntry]] = None):
        super().__init__(message)
        self.message = message
        self.logs = logs or []

@dataclass
class CitationDescriptor:
    """
    Lightweight description of a citation node used by the parallel orchestrator
    and bulk resolution logic.
    """
    citation_node_id: str
    paper_arxiv_id: str
    extracted_title: Optional[str] = None
    raw_text: Optional[str] = None
    reference_key: Optional[str] = None


@dataclass
class SinglePaperResult:
    """
    Result of processing a single paper (without recursive expansion).
    """
    arxiv_id: str
    paper_dir: Optional[str]
    tree_path: Optional[str]
    root_node_id: Optional[str]
    status: str  # "ok", "no_source", "parse_failed", "download_failed"
    logs: List[LogEntry]
    citation_descriptors: List[CitationDescriptor]
    # Optional in-memory nodes for this paper, used by the parallel orchestrator
    nodes: Optional[Dict[str, Any]] = None

