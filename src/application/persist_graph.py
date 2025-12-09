import json
import os
from typing import Dict, Optional, List

from pydantic import TypeAdapter

from .types import LogEntry, PipelineError
from ..config.settings import PipelineSettings
from ..ports.repositories import GraphStore
from ..adapters.repositories.neo4j_store import Neo4jPersister
from ..domain.nodes import GraphNode


def write_tree_json(paper_dir: str, nodes: Dict[str, GraphNode]) -> str:
    index_dir = os.path.join(paper_dir, "index")
    os.makedirs(index_dir, exist_ok=True)
    tree_path = os.path.join(index_dir, "tree.json")
    with open(tree_path, "w", encoding="utf-8") as f:
        # Pydantic models with inheritance are serialized same way
        json.dump({k: v.model_dump() for k, v in nodes.items()}, f, ensure_ascii=False, indent=2)
    return tree_path


def read_tree_json(paper_dir: str) -> Dict[str, GraphNode]:
    tree_path = os.path.join(paper_dir, "index", "tree.json")
    if not os.path.exists(tree_path):
        raise FileNotFoundError(tree_path)
    with open(tree_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    # Use TypeAdapter to handle polymorphic deserialization
    adapter = TypeAdapter(Dict[str, GraphNode])
    return adapter.validate_python(data)


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
            with open(abstract_path, "r", encoding="utf-8") as f:
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
