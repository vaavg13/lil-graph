import os
import tarfile
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from .ingestion.arxiv import (
    download_pdf,
    download_source_tarball_if_available,
    resolve_arxiv_id,
)
from .parsing.assets_preparer import prepare_assets
from .parsing.bibliography_parser import (
    build_citation_database,
    parse_latex_bibliography,
    build_citation_database_from_latex,
)
from .parsing.figtable_mapper import (
    detect_chunk_mentions,
    find_unreferenced_figures_in_sections,
    parse_latex_figures_tables,
    parse_simplified_markdown_figures,
    parse_simplified_markdown_tables,
)
from .parsing.latex_flattener import flatten_latex
from .parsing.markdown_simplifier import simplify_markdown_file
from .parsing.structure_extractor import extract_markdown_structure
from .indexing.models import NodeType
from .indexing.persist import write_tree_json
from .indexing.tree_builder import build_tree
from .indexing.graph.neo4j_impl import Neo4jPersister


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

    # 1) Download PDF (best-effort)
    published_date = None
    updated_date = None
    paper_title = None
    try:
        pdf_path, published_date, updated_date, paper_title = download_pdf(arxiv_id, out_directory)
        log("ok", f"PDF -> {pdf_path} (Published: {published_date})")
    except Exception as exc:  # pragma: no cover - best effort
        log("warn", f"PDF download failed: {exc}")

    # 2) Download LaTeX source tarball and extract
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
    except Exception as exc:  # pragma: no cover - defensive
        log("error", f"Source download/extract failed: {exc}")
        raise PipelineError("Source download/extract failed", logs)

    # 3) Flatten LaTeX and produce paper.md
    flattened_path = os.path.join(paper_dir, "flattened.tex")
    try:
        flatten_latex(source_dir, flattened_path, strip_comments=strip_comments)
        log("ok", f"Flattened -> {flattened_path}")
    except Exception as exc:
        log("error", f"Flattening failed: {exc}")
        raise PipelineError("Flattening failed", logs)

    # 4) Prepare assets and optionally clean extracted source
    try:
        prepare_assets(paper_dir, keep_extracted=keep_extracted)
        action = "kept" if keep_extracted else "removed"
        log("ok", f"Assets prepared; extracted source {action}")
    except Exception as exc:  # pragma: no cover - best effort
        log("warn", f"Asset preparation failed: {exc}")

    # 5) Simplify Pandoc markdown to clean, uniform markdown
    paper_md = os.path.join(paper_dir, "paper.md")
    if not os.path.exists(paper_md):
        log("error", f"paper.md not found at {paper_md}")
        raise PipelineError("paper.md not found", logs)

    simplified_md_path = os.path.join(paper_dir, "paper_simplified.md")
    try:
        simplify_markdown_file(paper_md, simplified_md_path)
        log("ok", f"Markdown simplified -> {simplified_md_path}")
    except Exception as exc:  # pragma: no cover - best effort
        log("warn", f"Markdown simplification failed: {exc}")
        simplified_md_path = paper_md

    # 6) Build structure and index
    try:
        sections, chunks, bibliography_text = extract_markdown_structure(simplified_md_path)

        maps = parse_latex_figures_tables(flattened_path)
        md_figures = parse_simplified_markdown_figures(simplified_md_path)
        if md_figures:
            maps.setdefault("figure_labels", {}).update(md_figures)

        # Parse full markdown table blocks for later TABLE node population
        md_tables = parse_simplified_markdown_tables(simplified_md_path)
        if md_tables:
            maps.setdefault("table_blocks", {}).update({k: v.get("text", "") for k, v in md_tables.items()})
            # Keep captions separately to assist TREE building when mention lacks caption
            caps = {k: v.get("caption", "") for k, v in md_tables.items() if v.get("caption")}
            if caps:
                maps.setdefault("table_captions", {}).update(caps)

        mentions = detect_chunk_mentions(chunks)

        citation_db = {}
        # Collect all cited keys from mentions first
        cited_keys = set()
        for chunk_mentions in mentions.values():
            for mention in chunk_mentions:
                if mention.get("type") == "CITATION":
                    cite_key = mention.get("key")
                    if cite_key:
                        cited_keys.add(cite_key)

        # Prefer LaTeX bibliography from flattened.tex to preserve keys
        try:
            latex_bib_entries = parse_latex_bibliography(flattened_path)
        except Exception:
            latex_bib_entries = {}

        if latex_bib_entries:
            citation_db = build_citation_database_from_latex(latex_bib_entries, cited_keys)
            log("info", f"Parsed {len(citation_db)} citations from LaTeX bibliography")
        elif bibliography_text:
            # Fallback to markdown-extracted bibliography if LaTeX one missing
            citation_db = build_citation_database(bibliography_text, cited_keys)
            log("info", f"Parsed {len(citation_db)} citations from markdown bibliography")

        nodes = build_tree(
            arxiv_id,
            sections,
            chunks,
            mentions,
            maps,
            None,
            citation_db,
            published_date=published_date,
            updated_date=updated_date,
            title=paper_title,
        )

        referenced_assets = set()
        for node in nodes.values():
            node_type = getattr(node, "node_type", getattr(node, "type", None))
            if node_type in [NodeType.FIGURE, NodeType.TABLE] and getattr(node, "asset_path", None):
                referenced_assets.add(node.asset_path)

        unreferenced = find_unreferenced_figures_in_sections(
            simplified_md_path,
            sections,
            chunks,
            referenced_assets,
        )

        nodes = build_tree(
            arxiv_id,
            sections,
            chunks,
            mentions,
            maps,
            unreferenced,
            citation_db,
            published_date=published_date,
            updated_date=updated_date,
            title=paper_title,
        )

        abstract_path = os.path.join(paper_dir, "abstract.txt")
        root_id = f"{arxiv_id}::ROOT"
        if os.path.exists(abstract_path) and root_id in nodes:
            try:
                with open(abstract_path, "r", encoding="utf-8") as abstract_file:
                    nodes[root_id].summary = abstract_file.read().strip()
            except Exception:  # pragma: no cover - best effort
                pass

        tree_path = write_tree_json(paper_dir, nodes)
        log("ok", f"Tree persisted -> {tree_path}")

        # --- Graph Persistence ---
        try:
            # Connect to local Neo4j Docker instance
            # In production, these should come from env vars
            neo4j_uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
            neo4j_auth = (os.getenv("NEO4J_USER", "neo4j"), os.getenv("NEO4J_PASSWORD", "password"))
            
            graph_db = Neo4jPersister(neo4j_uri, neo4j_auth)
            graph_db.persist_nodes(nodes)
            graph_db.close()
            log("ok", f"Nodes pushed to Neo4j Graph DB at {neo4j_uri}")
        except Exception as graph_exc:
            log("warn", f"Graph persistence failed: {graph_exc}")

    except Exception as exc:
        log("error", f"Indexing failed: {exc}")
        raise PipelineError("Indexing failed", logs)

    return PipelineResult(
        arxiv_id=arxiv_id,
        paper_dir=paper_dir,
        nodes=nodes,
        tree_path=tree_path,
        logs=logs,
        flattened_path=flattened_path,
        simplified_markdown_path=simplified_md_path,
        abstract_path=os.path.join(paper_dir, "abstract.txt"),
    )