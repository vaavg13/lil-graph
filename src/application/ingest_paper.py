import os
from typing import Any, Dict, List, Optional

from .types import PipelineError, LogEntry, SinglePaperResult, CitationDescriptor
from .parse_document import run_parsing
from .build_graph import build_nodes
from .persist_graph import persist_nodes
from ..adapters.ingestion.arxiv_ingestion import resolve_arxiv_id
from ..domain.nodes import NodeType, CitationNode, GraphNode
from ..config.settings import PipelineSettings
from ..ports.repositories import GraphStore
from ..adapters.factories import get_ingestion_port, get_resolution_port


def _extract_citation_descriptors(
    arxiv_id: str, nodes: Dict[str, GraphNode]
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
    resolve_citations: bool = False,
    verify_graph: bool = False,
    verifier_model: str = "gpt-4o",
    parser_type: str = "latexml",
    settings: Optional[PipelineSettings] = None,
    graph_store: Optional[GraphStore] = None,
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

    # Download content (ingestion backend)
    try:
        cfg = settings or PipelineSettings.from_env()
        ingestion = get_ingestion_port(cfg)
        paper_dir, source_dir, paper_title, pub_date, upd_date = ingestion.download_and_extract(
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

    nodes: Dict[str, GraphNode] = {}
    tree_path: Optional[str] = None

    try:
        # Parse
        parsed_data = run_parsing(source_dir, paper_dir, parser_type or "", logs, settings=settings)

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

        if resolve_citations:
            resolver = get_resolution_port(cfg)
            try:
                resolver.resolve(nodes, logs)
            except Exception as res_exc:
                logs.append(("warn", f"Citation resolution failed or partial: {res_exc}"))

        # Optional verification (skip gracefully if verifier module is unavailable)
        if verify_graph:
            try:
                from .verification.verifier import GraphVerifier  # type: ignore
            except Exception as import_exc:
                logs.append(("warn", f"Graph verification unavailable: {import_exc}"))
            else:
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
        tree_path = persist_nodes(
            nodes,
            paper_dir,
            arxiv_id,
            logs,
            settings=settings,
            graph_store=graph_store,
        )

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

