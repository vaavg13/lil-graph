from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List, Optional, Set, Tuple

from ..adapters.ingestion.arxiv_ingestion import resolve_arxiv_id
from ..ports.repositories import GraphStore
from ..adapters.repositories.neo4j_store import Neo4jPersister
from ..domain.nodes import CitationNode, GraphNode, NodeType
from .ingest_paper import run_single_paper
from .types import LogEntry, PipelineError
from ..adapters.factories import get_resolution_port
from ..config.settings import PipelineSettings


def _try_resolve_child_arxiv_id(cite: CitationNode) -> Optional[str]:
    # Prefer DOI, fall back to resolved title
    if cite.doi:
        try:
            return resolve_arxiv_id(cite.doi)
        except Exception:
            pass
    if cite.title:
        try:
            return resolve_arxiv_id(cite.title)
        except Exception:
            pass
    return None


def run_parallel_pipeline(
    root_identifier: str,
    base_dir: str,
    max_depth: int,
    workers: int = 4,
    settings: Optional[PipelineSettings] = None,
    graph_store: Optional[GraphStore] = None,
    **pipeline_kwargs,
):
    """
    Level-wise parallel pipeline with deferred, bulk citation resolution and
    database-level linking of citation nodes to expanded paper roots.
    """
    cfg = settings or pipeline_kwargs.pop("settings", None) or PipelineSettings.from_env()

    visited: Set[str] = set()
    frontier: Set[str] = {root_identifier}

    # child_arxiv_id -> List[citation_node_id] built from previous level
    pending_links: Dict[str, List[str]] = {}

    graph = graph_store or Neo4jPersister(
        cfg.neo4j_uri, (cfg.neo4j_user, cfg.neo4j_password)
    )
    created_store = graph_store is None
    resolver = get_resolution_port(cfg)

    try:
        for depth in range(max_depth + 1):
            print(f"--- Level {depth} Processing {len(frontier)} papers ---")

            # Resolve identifiers to canonical arxiv IDs and filter visited
            to_process: List[str] = []
            for ident in frontier:
                try:
                    aid = resolve_arxiv_id(ident)
                    if aid not in visited:
                        to_process.append(aid)
                        visited.add(aid)
                except Exception:
                    print(f"Skipping unresolvable ID: {ident}")

            if not to_process and not pending_links:
                break

            # 1) Process current level papers in parallel
            results_by_id: Dict[str, Dict[str, Any]] = {}
            with ThreadPoolExecutor(max_workers=workers) as executor:
                future_to_id = {
                    executor.submit(
                        run_single_paper,
                        pid,
                        base_dir,
                        settings=cfg,
                        graph_store=None,  # per-paper persistence uses its own store by default
                        **pipeline_kwargs,
                    ): pid
                    for pid in to_process
                }

                for future in as_completed(future_to_id):
                    pid = future_to_id[future]
                    try:
                        single_result = future.result()
                        results_by_id[pid] = {
                            "result": single_result,
                            "nodes": None,
                        }
                        print(f"Processed {pid}: status={single_result.status}")
                    except PipelineError as exc:
                        print(f"[error] Pipeline failed for {pid}: {exc.message}")
                    except Exception as exc:
                        print(f"[error] Unexpected failure for {pid}: {exc}")

            # 2) Link citations from previous level based on newly processed children
            successful_children: Set[str] = set(
                pid
                for pid, payload in results_by_id.items()
                if payload["result"].status == "ok"
            )

            if pending_links:
                print(
                    f"Linking {sum(len(v) for v in pending_links.values())} "
                    "citations from previous level..."
                )
                for child_id, cite_ids in pending_links.items():
                    if child_id in successful_children:
                        # Link each citation to the child root
                        child_root_id = f"{child_id}::ROOT"
                        for cid in cite_ids:
                            graph.link_citation_to_child_root(cid, child_root_id)
                    else:
                        # Child failed parsing or was never processed; mark citations and leave as-is
                        for cid in cite_ids:
                            graph.update_citation_node(
                                cid,
                                {"expansion_status": "parse_failed"},
                            )
                pending_links = {}

            # 3) Resolve citations for current level in bulk and decide next frontier
            combined_nodes: Dict[str, GraphNode] = {}
            for pid, payload in results_by_id.items():
                r = payload["result"]
                if r.status != "ok" or r.nodes is None:
                    continue
                # Merge nodes from all successful papers at this level
                combined_nodes.update(r.nodes)  # type: ignore[arg-type]

            next_frontier: Set[str] = set()
            next_pending_links: Dict[str, List[str]] = {}

            if combined_nodes:
                # Bulk resolve citations across all papers in this level
                resolver.resolve(combined_nodes)
            # Update citation nodes in the DB.
            for node in combined_nodes.values():
                if not isinstance(node, CitationNode) or node.node_type != NodeType.CITATION:
                    continue

                # Push resolved metadata into Neo4j
                update_fields: Dict[str, Any] = {}
                if node.title is not None:
                    update_fields["title"] = node.title
                if node.abstract is not None:
                    update_fields["abstract"] = node.abstract
                if node.venue is not None:
                    update_fields["venue"] = node.venue
                if node.year is not None:
                    update_fields["year"] = node.year
                if node.url is not None:
                    update_fields["url"] = node.url
                if node.doi is not None:
                    update_fields["doi"] = node.doi
                if node.authors:
                    update_fields["authors"] = node.authors

                if update_fields:
                    graph.update_citation_node(node.id, update_fields)

                # Skip child resolution if we've reached the max depth; avoids
                # unnecessary arXiv lookups that were causing the post-CrossRef
                # stall when no further expansion is requested.
                if depth >= max_depth:
                    continue

                # Decide whether to expand this citation
                child_id = _try_resolve_child_arxiv_id(node)
                if not child_id:
                    continue

                # Track all citations that point to this child
                if child_id not in next_pending_links:
                    next_pending_links[child_id] = []
                next_pending_links[child_id].append(node.id)

                # Only schedule processing if we haven't already seen this paper
                if child_id not in visited:
                    next_frontier.add(child_id)

            # Prepare next frontier and carry links forward
            frontier = next_frontier
            pending_links = next_pending_links

    finally:
        if created_store:
            graph.close()


