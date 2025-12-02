from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any
from ..models import PaperNode

class GraphPersister(ABC):
    """
    Abstract interface for persisting paper nodes to a Graph Database.
    This abstracts away whether we are using Neo4j, NetworkX, or FalkorDB.
    """

    @abstractmethod
    def persist_nodes(self, nodes: Dict[str, PaperNode]) -> None:
        """
        Write a batch of nodes and their relationships to the graph.
        """
        pass

    @abstractmethod
    def query_subgraph(self, root_id: str, depth: int = 1) -> Dict[str, Any]:
        """
        Retrieve a subgraph starting from a node.
        """
        pass
    
    @abstractmethod
    def close(self):
        """Clean up connections."""
        pass

