import os
from typing import Dict, List, Optional

from ..indexing.graph.interface import GraphStore
from ..indexing.graph.neo4j_impl import Neo4jPersister
from ..indexing.models import GraphNode
from ..indexing.persist import write_tree_json
from ..pipeline_types import LogEntry, PipelineError
from ..settings import PipelineSettings


def persist_nodes(
    nodes: Dict[str, GraphNode],
    paper_dir: str,
    arxiv_id: str,
    logs: List[LogEntry],
    settings: Optional[PipelineSettings] = None,
    graph_store: Optional[GraphStore] = None,
) -> Optional[str]:
    tree_path = None
    created_store = False
    store: Optional[GraphStore] = graph_store
    try:
        # Check abstract fallback
        abstract_path = os.path.join(paper_dir, "abstract.txt")
        root_node = nodes.get(f"{arxiv_id}::ROOT")
        if root_node and not root_node.abstract and os.path.exists(abstract_path):
             with open(abstract_path, 'r', encoding='utf-8') as f:
                 root_node.abstract = f.read().strip()

        # JSON Persistence
        tree_path = write_tree_json(paper_dir, nodes)
        logs.append(("ok", f"Tree persisted -> {tree_path}"))

        # Neo4j Persistence
        try:
            cfg = settings or PipelineSettings.from_env()
            if store is None:
                store = Neo4jPersister(cfg.neo4j_uri, (cfg.neo4j_user, cfg.neo4j_password))
                created_store = True

            store.persist_nodes(nodes)
            logs.append(("ok", "Nodes persisted to GraphStore"))
        except Exception as graph_exc:
            logs.append(("warn", f"Graph persistence failed: {graph_exc}"))
        finally:
            if created_store and store is not None:
                try:
                    store.close()
                except Exception:
                    pass
            
    except Exception as exc:
        logs.append(("error", f"Persistence failed: {exc}"))
        raise PipelineError(f"Persistence failed: {exc}", logs)
        
    return tree_path

