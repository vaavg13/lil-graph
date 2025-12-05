import os
from typing import Dict, Optional, List
from ..indexing.persist import write_tree_json
from ..indexing.graph.neo4j_impl import Neo4jPersister
from ..indexing.models import PaperNode
from ..pipeline_types import PipelineError, LogEntry

def persist_nodes(nodes: Dict[str, PaperNode], paper_dir: str, arxiv_id: str, logs: List[LogEntry]) -> Optional[str]:
    tree_path = None
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
            neo4j_uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
            neo4j_auth = (os.getenv("NEO4J_USER", "neo4j"), os.getenv("NEO4J_PASSWORD", "password"))
            
            graph_db = Neo4jPersister(neo4j_uri, neo4j_auth)
            graph_db.persist_nodes(nodes)
            graph_db.close()
            logs.append(("ok", f"Nodes pushed to Neo4j Graph DB at {neo4j_uri}"))
        except Exception as graph_exc:
            logs.append(("warn", f"Graph persistence failed: {graph_exc}"))
            
    except Exception as exc:
        logs.append(("error", f"Persistence failed: {exc}"))
        raise PipelineError(f"Persistence failed: {exc}", logs)
        
    return tree_path

