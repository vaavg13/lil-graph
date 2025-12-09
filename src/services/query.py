from typing import Optional

from ..indexing.graph.interface import GraphStore
from ..indexing.graph.neo4j_impl import Neo4jPersister
from ..settings import PipelineSettings


def get_neighborhood(
    node_id: str,
    depth: int = 1,
    graph_store: Optional[GraphStore] = None,
    settings: Optional[PipelineSettings] = None,
):
    """
    Return a neighborhood subgraph around node_id up to depth.
    """
    if depth < 0:
        depth = 0
    cfg = settings or PipelineSettings.from_env()
    store = graph_store or Neo4jPersister(cfg.neo4j_uri, (cfg.neo4j_user, cfg.neo4j_password))
    try:
        return store.query_subgraph(node_id, depth=depth)
    finally:
        if graph_store is None:
            try:
                store.close()
            except Exception:
                pass
