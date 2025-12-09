from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from ..domain.nodes import GraphNode


class GraphPersister(ABC):
    """
    Abstract interface for persisting and mutating paper graphs in a Graph DB.
    """

    @abstractmethod
    def persist_nodes(self, nodes: Dict[str, GraphNode]) -> None:
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
    def update_citation_node(self, citation_node_id: str, fields: Dict[str, Any]) -> None:
        """
        Update an existing citation node with resolved metadata or status flags.
        """
        pass

    @abstractmethod
    def link_citation_to_child_root(self, citation_node_id: str, child_root_id: str) -> None:
        """
        Connect the parent of a citation node to the root node of an expanded
        paper and remove the original citation node if appropriate.
        """
        pass

    @abstractmethod
    def close(self):
        """Clean up connections."""
        pass

    @abstractmethod
    def clear(self) -> None:
        """
        Remove all nodes and relationships from the backing store.
        """
        pass


class GraphStore(GraphPersister):
    """
    Alias for graph storage port. New code should depend on GraphStore while
    legacy code can continue to import GraphPersister. Both share the same
    contract today.
    """

    pass
