import os
import tarfile
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple, Union
import re

from .ingestion.arxiv import (
    download_pdf,
    download_source_tarball_if_available,
    resolve_arxiv_id,
)
from .parsing import ParsingPipeline
from .indexing.node_builder import build_nodes_from_parsed_data
from .indexing.persist import write_tree_json
from .indexing.graph.neo4j_impl import Neo4jPersister
from .resolution.crossref import CrossRefResolver
from .verification.verifier import GraphVerifier


LogEntry = Tuple[str, str]


@dataclass
class PipelineResult:
    arxiv_id: str
    paper_dir: Optional[str]
    nodes: Optional[Dict[str, Any]]
    tree_path: Optional[str]
    logs: List[LogEntry]
    flattened_path: Optional[str] = None
    simplified_markdown_path: Optional[str] = None
    abstract_path: Optional[str] = None


class PipelineError(RuntimeError):
    def __init__(self, message: str, logs: Optional[List[LogEntry]] = None):
        super().__init__(message)
        self.message = message
        self.logs = logs or []


def run_pipeline(
    identifier: str,
    base_dir: str,
    strip_comments: bool = True,
    keep_extracted: bool = False,
    out_dir: Optional[str] = None,
    merge_section_chunks: bool = True,
    verify_graph: bool = False,
    verifier_model: str = "gpt-4o",
) -> PipelineResult:
    logs: List[LogEntry] = []

    def log(level: str, message: str) -> None:
        logs.append((level, message))

    out_directory = out_dir or base_dir
    log("setup", f"BASE_DIR={base_dir}")

    try:
        arxiv_id = resolve_arxiv_id(identifier)
        log("info", f"arXiv ID: {arxiv_id}")
    except Exception as exc:  # pragma: no cover - defensive
        log("error", f"Resolve failed: {exc}")
        raise PipelineError("Failed to resolve arXiv identifier", logs)

    paper_dir = os.path.join(out_directory, "PAPER", arxiv_id.replace("/", "_"))
    os.makedirs(paper_dir, exist_ok=True)

    # 1) Download PDF
    published_date = None
    updated_date = None
    paper_title = None
    try:
        pdf_path, published_date, updated_date, paper_title = download_pdf(arxiv_id, out_directory)
        log("ok", f"PDF -> {pdf_path} (Published: {published_date})")
    except Exception as exc: 
        log("warn", f"PDF download failed: {exc}")

    # 2) Download Source
    try:
        src_tar = download_source_tarball_if_available(arxiv_id, out_directory)
        if not src_tar:
            log("info", "No LaTeX source available; stopping.")
            return PipelineResult(
                arxiv_id=arxiv_id,
                paper_dir=paper_dir,
                nodes=None,
                tree_path=None,
                logs=logs,
            )
        source_dir = os.path.join(paper_dir, "source_extracted")
        with tarfile.open(src_tar, "r") as tar:
            tar.extractall(path=source_dir)
        log("ok", f"Source extracted -> {source_dir}")
    except Exception as exc: 
        log("error", f"Source download/extract failed: {exc}")
        raise PipelineError("Source download/extract failed", logs)

    # 3) Parsing Pipeline
    try:
        parsing_pipeline = ParsingPipeline(source_dir, paper_dir)
        parsed_data = parsing_pipeline.run()
        log("ok", "Parsing pipeline completed successfully")
    except Exception as exc:
        log("error", f"Parsing pipeline failed: {exc}")
        raise PipelineError(f"Parsing failed: {exc}", logs)

    # 4) Build Nodes
    try:
        nodes = build_nodes_from_parsed_data(
            arxiv_id, 
            parsed_data, 
            paper_title=paper_title,
            published_date=published_date,
            updated_date=updated_date,
            merge_section_chunks=merge_section_chunks,
        )
        log("ok", f"Constructed {len(nodes)} graph nodes")
    except Exception as exc:
        log("error", f"Node construction failed: {exc}")
        raise PipelineError(f"Node construction failed: {exc}", logs)

    # 5) Verify Graph (Optional)
    if verify_graph:
        try:
            verifier = GraphVerifier(model_name=verifier_model)
            warnings = verifier.verify(nodes, source_dir)
            if warnings:
                log("warn", "Graph Verification Issues Found:")
                for w in warnings:
                    log("warn", f"  - {w}")
            else:
                log("ok", "Graph verification passed with no issues.")
        except Exception as v_exc:
            log("warn", f"Graph verification failed to run: {v_exc}")

    # 6) Clean up
    if not keep_extracted and os.path.exists(source_dir):
        import shutil
        try:
            shutil.rmtree(source_dir)
            log("ok", "Extracted source removed")
        except Exception as e:
            log("warn", f"Failed to remove source dir: {e}")

    # 7) Persist and Resolve
    tree_path = None
    try:
        # Check abstract fallback (if PDF download failed or extraction failed)
        abstract_path = os.path.join(paper_dir, "abstract.txt")
        root_node = nodes.get(f"{arxiv_id}::ROOT")
        if root_node and not root_node.abstract and os.path.exists(abstract_path):
             with open(abstract_path, 'r', encoding='utf-8') as f:
                 root_node.abstract = f.read().strip()

        # Online Resolution
        try:
            resolver = CrossRefResolver()
            resolver.resolve_citations(nodes)
            log("ok", "Resolved citations via CrossRef")
        except Exception as res_exc:
            log("warn", f"Citation resolution failed or partial: {res_exc}")

        # JSON Persistence
        tree_path = write_tree_json(paper_dir, nodes)
        log("ok", f"Tree persisted -> {tree_path}")

        # Neo4j Persistence
        try:
            neo4j_uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
            neo4j_auth = (os.getenv("NEO4J_USER", "neo4j"), os.getenv("NEO4J_PASSWORD", "password"))
            
            graph_db = Neo4jPersister(neo4j_uri, neo4j_auth)
            graph_db.persist_nodes(nodes)
            graph_db.close()
            log("ok", f"Nodes pushed to Neo4j Graph DB at {neo4j_uri}")
        except Exception as graph_exc:
            log("warn", f"Graph persistence failed: {graph_exc}")

    except Exception as exc:
        log("error", f"Persistence/Resolution failed: {exc}")
        raise PipelineError(f"Persistence failed: {exc}", logs)

    return PipelineResult(
        arxiv_id=arxiv_id,
        paper_dir=paper_dir,
        nodes=nodes,
        tree_path=tree_path,
        logs=logs,
        flattened_path=None,
        simplified_markdown_path=None,
        abstract_path=abstract_path if os.path.exists(abstract_path) else None,
    )
