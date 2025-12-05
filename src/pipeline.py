import os
from typing import Optional, Tuple, List, Dict, Any

from .pipeline_types import (
    PipelineError,
    LogEntry,
    SinglePaperResult,
    CitationDescriptor,
)
from .pipeline_steps.download import download_content
from .pipeline_steps.parse import run_parsing
from .pipeline_steps.build import build_nodes
from .pipeline_steps.persist import persist_nodes
from .ingestion.arxiv import resolve_arxiv_id
from .verification.verifier import GraphVerifier
from .indexing.models import NodeType, CitationNode, PaperNode


def _extract_citation_descriptors(
    arxiv_id: str, nodes: Dict[str, PaperNode]
) -> List[CitationDescriptor]:
    descriptors: List[CitationDescriptor] = []
    for node in nodes.values():
        if isinstance(node, CitationNode) and node.node_type == NodeType.CITATION:
            extracted = node.extracted_data or {}
            descriptors.append(
                CitationDescriptor(
                    citation_node_id=node.id,
                    paper_arxiv_id=arxiv_id,
                    extracted_title=extracted.get("extracted_title"),
                    raw_text=extracted.get("text"),
                    reference_key=extracted.get("citation_key") or extracted.get("key"),
                )
            )
    return descriptors


def run_single_paper(
    identifier: str,
    base_dir: str,
    keep_extracted: bool = False,
    out_dir: Optional[str] = None,
    merge_section_chunks: bool = True,
    verify_graph: bool = False,
    verifier_model: str = "gpt-4o",
    parser_type: str = "latexml",
) -> SinglePaperResult:
    """
    Process a single paper: resolve ID -> download -> parse -> build graph -> persist.
    No recursive expansion or CrossRef resolution happens here.
    """
    logs: List[LogEntry] = []
    out_directory = out_dir or base_dir

    logs.append(("setup", f"BASE_DIR={base_dir}"))

    try:
        arxiv_id = resolve_arxiv_id(identifier)
        logs.append(("info", f"arXiv ID: {arxiv_id}"))
    except Exception as exc:
        logs.append(("error", f"Resolve failed: {exc}"))
        raise PipelineError("Failed to resolve arXiv identifier", logs)

    # Download content
    try:
        paper_dir, source_dir, paper_title, pub_date, upd_date = download_content(
            arxiv_id, out_directory, logs
        )
    except PipelineError as e:
        # Download failure – we cannot proceed.
        return SinglePaperResult(
            arxiv_id=arxiv_id,
            paper_dir=None,
            tree_path=None,
            root_node_id=None,
            status="download_failed",
            logs=logs + (e.logs or []),
            citation_descriptors=[],
            nodes=None,
        )

    if not source_dir:
        # No source available – we do not attempt parsing/expansion.
        return SinglePaperResult(
            arxiv_id=arxiv_id,
            paper_dir=paper_dir,
            tree_path=None,
            root_node_id=None,
            status="no_source",
            logs=logs,
            citation_descriptors=[],
            nodes=None,
        )

    nodes: Dict[str, PaperNode] = {}
    tree_path: Optional[str] = None

    try:
        # Parse
        parsed_data = run_parsing(source_dir, paper_dir, parser_type, logs)

        # Build nodes
        nodes = build_nodes(
            arxiv_id,
            parsed_data,
            paper_title,
            pub_date,
            upd_date,
            merge_section_chunks,
            logs,
        )

        # Optional verification
        if verify_graph:
            try:
                verifier = GraphVerifier(model_name=verifier_model)
                warnings = verifier.verify(nodes, source_dir)
                if warnings:
                    logs.append(("warn", "Graph Verification Issues Found:"))
                    for w in warnings:
                        logs.append(("warn", f"  - {w}"))
                else:
                    logs.append(("ok", "Graph verification passed with no issues."))
            except Exception as v_exc:
                logs.append(("warn", f"Graph verification failed to run: {v_exc}"))

        # Cleanup extracted source if requested
        if not keep_extracted and os.path.exists(source_dir):
            import shutil

            try:
                shutil.rmtree(source_dir)
                logs.append(("ok", "Extracted source removed"))
            except Exception as e:
                logs.append(("warn", f"Failed to remove source dir: {e}"))

        # Persist graph (JSON + Neo4j)
        tree_path = persist_nodes(nodes, paper_dir, arxiv_id, logs)

    except Exception as e:
        logs.append(("error", f"Pipeline failed: {e}"))
        # If parsing or building fails, we treat this paper as non-expandable.
        return SinglePaperResult(
            arxiv_id=arxiv_id,
            paper_dir=paper_dir,
            tree_path=None,
            root_node_id=None,
            status="parse_failed",
            logs=logs,
            citation_descriptors=[],
            nodes=None,
        )

    # Identify root node id (if present) and citation descriptors
    root_node_id: Optional[str] = None
    for node in nodes.values():
        if node.node_type == NodeType.ROOT:
            root_node_id = node.id
            break

    citation_descriptors = _extract_citation_descriptors(arxiv_id, nodes)

    return SinglePaperResult(
        arxiv_id=arxiv_id,
        paper_dir=paper_dir,
        tree_path=tree_path,
        root_node_id=root_node_id,
        status="ok",
        logs=logs,
        citation_descriptors=citation_descriptors,
        nodes=nodes,
    )

