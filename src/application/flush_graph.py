from typing import Optional

from ..config.settings import PipelineSettings
from ..ports.repositories import GraphStore
from ..adapters.repositories.neo4j_store import Neo4jPersister
from ..adapters.repositories.memory_store import InMemoryGraphStore


def flush_graph(store: GraphStore) -> None:
    """
    Remove all nodes/edges from the provided GraphStore.
    """
    store.clear()


def flush_default_store(
    target: str = "neo4j",
    settings: Optional[PipelineSettings] = None,
) -> None:
    """
    Flush the configured graph store (neo4j or in-memory).
    """
    cfg = settings or PipelineSettings.from_env()

    if target == "neo4j":
        store: GraphStore = Neo4jPersister(cfg.neo4j_uri, (cfg.neo4j_user, cfg.neo4j_password))
    elif target == "memory":
        store = InMemoryGraphStore()
    else:
        raise ValueError(f"Unsupported store target: {target}")

    try:
        store.clear()
    finally:
        try:
            store.close()
        except Exception:
            pass
