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
from .parsing.pipeline import ParsingPipeline
from .indexing.models import (
    NodeType, RootNode, SectionNode, ChunkNode, 
    FigureNode, TableNode, CitationNode, PaperNode
)
from .indexing.persist import write_tree_json
from .indexing.graph.neo4j_impl import Neo4jPersister
from .resolution.crossref import CrossRefResolver


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


def build_nodes_from_parsed_data(
    arxiv_id: str,
    parsed_data: Dict[str, Any],
    paper_title: Optional[str] = None,
    published_date: Optional[str] = None,
    updated_date: Optional[str] = None,
    merge_section_chunks: bool = True,
) -> Dict[str, PaperNode]:
    """
    Convert the parsed AST data into the flat dictionary of Node objects
    expected by the indexing/persistence layer.
    """
    nodes: Dict[str, PaperNode] = {}
    
    # 1. Root Node
    root_id = f"{arxiv_id}::ROOT"
    
    # Abstract is now directly in parsed_data
    abstract_text = parsed_data.get("abstract")
    
    root_node = RootNode(
        id=root_id,
        paper_id=arxiv_id,
        title=paper_title or parsed_data.get("metadata", {}).get("title", "Untitled"),
        abstract=abstract_text,
        publication_date=published_date,
        update_date=updated_date,
        children_ids=[]
    )
    nodes[root_id] = root_node
    
    # Stack of (node_id, level)
    section_stack: List[Tuple[str, int]] = [(root_id, 0)]
    
    section_counter = 0
    chunk_counter = 0
    
    for section_data in parsed_data.get("sections", []):
        title = section_data.get("title", "")
        level = section_data.get("level", 1)
        section_chunks = section_data.get("chunks", [])
        if merge_section_chunks and section_chunks:
            merged_text_parts: List[str] = []
            merged_citations: List[str] = []
            for chunk_data in section_chunks:
                text_fragment = chunk_data.get("text", "")
                if text_fragment.strip():
                    merged_text_parts.append(text_fragment.strip())
                merged_citations.extend(chunk_data.get("citations", []))
            if merged_text_parts:
                section_chunks = [{
                    "text": "\n\n".join(merged_text_parts),
                    "citations": merged_citations,
                }]
            else:
                section_chunks = []
        
        # Determine parent section
        while len(section_stack) > 1 and section_stack[-1][1] >= level:
            section_stack.pop()
        
        parent_id, _ = section_stack[-1]
        
        # Create Section Node
        section_id = f"{arxiv_id}::SEC::{section_counter}"
        section_counter += 1
        
        section_node = SectionNode(
            id=section_id,
            paper_id=arxiv_id,
            title=title,
            level=level,
            parent_id=parent_id,
            children_ids=[]
        )
        nodes[section_id] = section_node
        nodes[parent_id].children_ids.append(section_id)
        
        # Update stack
        section_stack.append((section_id, level))
        
        # Process Chunks
        for chunk_data in section_chunks:
            text = chunk_data.get("text", "")
            citations = chunk_data.get("citations", [])
            
            if not text.strip():
                continue
                
            chunk_id = f"{arxiv_id}::CHUNK::{chunk_counter}"
            chunk_counter += 1
            
            chunk_node = ChunkNode(
                id=chunk_id,
                paper_id=arxiv_id,
                text=text,
                parent_id=section_id,
                children_ids=[]
            )
            nodes[chunk_id] = chunk_node
            section_node.children_ids.append(chunk_id)
            
            # Attach Citations to Chunk
            for cite_key in citations:
                cite_node_id = f"{chunk_id}::CITE::{cite_key}"
                
                # Get extracted data (from bib entries)
                bibliography = parsed_data.get("bibliography", {})
                bib_entry = bibliography.get(cite_key, {})
                extracted_data = dict(bib_entry) if isinstance(bib_entry, dict) else {}
                if cite_key:
                    extracted_data.setdefault("key", cite_key)
                    extracted_data.setdefault("citation_key", cite_key)
                
                # IMPORTANT: We do NOT populate title/year/authors/doi here.
                # These must be resolved via CrossRef. Extracted data is just a hint.
                cite_node = CitationNode(
                    id=cite_node_id,
                    paper_id=arxiv_id,
                    parent_id=chunk_id,
                    extracted_data=extracted_data, # Raw extraction preserved here
                    title=None, 
                    year=None,
                    authors=[],
                    children_ids=[]
                )
                nodes[cite_node_id] = cite_node
                chunk_node.children_ids.append(cite_node_id)

    # 3. Process Images
    if parsed_data.get("images"):
        fig_section_id = f"{arxiv_id}::SEC::FIGURES"
        fig_section = SectionNode(
            id=fig_section_id,
            paper_id=arxiv_id,
            title="Figures and Assets",
            level=1,
            parent_id=root_id,
            children_ids=[]
        )
        nodes[fig_section_id] = fig_section
        nodes[root_id].children_ids.append(fig_section_id)
        
        for i, img_path in enumerate(parsed_data.get("images", [])):
            fig_id = f"{arxiv_id}::FIG::{i}"
            fig_node = FigureNode(
                id=fig_id,
                paper_id=arxiv_id,
                asset_path=img_path,
                caption=None,
                parent_id=fig_section_id
            )
            nodes[fig_id] = fig_node
            fig_section.children_ids.append(fig_id)

    # 4. Process Tables
    if parsed_data.get("tables"):
        table_section_id = f"{arxiv_id}::SEC::TABLES"
        table_section = SectionNode(
            id=table_section_id,
            paper_id=arxiv_id,
            title="Tables",
            level=1,
            parent_id=root_id,
            children_ids=[]
        )
        nodes[table_section_id] = table_section
        nodes[root_id].children_ids.append(table_section_id)
        
        for i, table_data in enumerate(parsed_data.get("tables", [])):
            tbl_id = f"{arxiv_id}::TBL::{i}"
            tbl_node = TableNode(
                id=tbl_id,
                paper_id=arxiv_id,
                table_content=table_data.get("content", ""),
                caption=table_data.get("caption"),
                parent_id=table_section_id
            )
            nodes[tbl_id] = tbl_node
            table_section.children_ids.append(tbl_id)

    return nodes


def run_pipeline(
    identifier: str,
    base_dir: str,
    strip_comments: bool = True,
    keep_extracted: bool = False,
    out_dir: Optional[str] = None,
    merge_section_chunks: bool = True,
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

    # 4) Clean up
    if not keep_extracted and os.path.exists(source_dir):
        import shutil
        try:
            shutil.rmtree(source_dir)
            log("ok", "Extracted source removed")
        except Exception as e:
            log("warn", f"Failed to remove source dir: {e}")

    # 5) Build Nodes
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

    # 6) Persist and Resolve
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
