import os
import networkx as nx
import pickle
from typing import Dict, Any
from .interface import GraphPersister
from ..models import PaperNode, NodeType

class NetworkXPersister(GraphPersister):
    """
    Local filesystem-backed NetworkX graph.
    Good for MVP and local development without running a Docker container.
    """
    
    def __init__(self, storage_path: str):
        self.storage_path = storage_path
        self.graph = nx.DiGraph()
        self._load()

    def _load(self):
        if os.path.exists(self.storage_path):
            try:
                with open(self.storage_path, "rb") as f:
                    self.graph = pickle.load(f)
            except Exception:
                self.graph = nx.DiGraph()

    def _save(self):
        os.makedirs(os.path.dirname(self.storage_path), exist_ok=True)
        with open(self.storage_path, "wb") as f:
            pickle.dump(self.graph, f)

    def persist_nodes(self, nodes: Dict[str, PaperNode]) -> None:
        """
        Converts PaperNodes to NetworkX nodes/edges and saves.
        """
        # 1. Add Nodes
        for node_id, node in nodes.items():
            # Convert Pydantic model to dict, exclude complex types if needed
            data = node.model_dump(exclude={"embedding", "children_ids", "parent_id"})
            # Flatten metadata for easier graph querying
            if node.metadata:
                for k, v in node.metadata.items():
                    data[f"meta_{k}"] = v
                del data["metadata"]
            
            self.graph.add_node(node_id, **data)

        # 2. Add Edges (Parent-Child Hierarchy)
        for node_id, node in nodes.items():
            # HIERARCHY Edge
            for child_id in node.children_ids:
                if child_id in nodes:
                    self.graph.add_edge(node_id, child_id, type="HAS_CHILD")
            
            # CITATION Edge (Logical Link)
            if node.node_type == NodeType.CITATION:
                # In a real graph, we would link to the TARGET paper here.
                # For now, we just exist as a child of the chunk.
                pass
        
        self._save()

    def query_subgraph(self, root_id: str, depth: int = 1) -> Dict[str, Any]:
        # Basic BFS traversal
        if root_id not in self.graph:
            return {}
        nodes = list(nx.bfs_tree(self.graph, root_id, depth_limit=depth))
        return {n: self.graph.nodes[n] for n in nodes}

    def close(self):
        self._save()

