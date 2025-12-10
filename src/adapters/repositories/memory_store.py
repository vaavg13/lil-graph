from typing import Any, Dict, List, Set, Tuple

from ...ports.repositories import GraphStore
from ...domain.nodes import GraphNode


class InMemoryGraphStore(GraphStore):
    """
    Lightweight GraphStore useful for tests and local tooling. Not intended for
    production scale or concurrency.
    """

    def __init__(self):
        self.nodes: Dict[str, GraphNode] = {}
        self.edges: Set[Tuple[str, str]] = set()  # (parent, child)

    def close(self):
        # Nothing to clean up for in-memory usage.
        return None

    def clear(self) -> None:
        self.nodes.clear()
        self.edges.clear()

    def persist_nodes(self, nodes: Dict[str, GraphNode]) -> None:
        self.nodes.update(nodes)
        for node in nodes.values():
            for child_id in node.children_ids:
                self.edges.add((node.id, child_id))

    def query_subgraph(self, root_id: str, depth: int = 1) -> Dict[str, Any]:
        """
        Return a minimal subgraph representation with node ids and adjacency,
        including all nodes up to `depth` hops from the root.
        """
        max_depth = max(depth, 0)
        visited: Set[str] = set()
        frontier: Set[str] = {root_id}
        result_nodes: Dict[str, GraphNode] = {}
        result_edges: List[Tuple[str, str]] = []

        # Depth 0 should still return the root; iterate depth+1 levels.
        for _ in range(max_depth + 1):
            next_frontier: Set[str] = set()
            for nid in frontier:
                if nid in visited:
                    continue
                visited.add(nid)
                if nid in self.nodes:
                    result_nodes[nid] = self.nodes[nid]
                for parent, child in self.edges:
                    if parent == nid:
                        result_edges.append((parent, child))
                        if child not in visited:
                            next_frontier.add(child)
            frontier = next_frontier
            if not frontier:
                break

        return {"nodes": result_nodes, "edges": result_edges}

    def update_citation_node(self, citation_node_id: str, fields: Dict[str, Any]) -> None:
        node = self.nodes.get(citation_node_id)
        if not node or not fields:
            return
        for key, value in fields.items():
            if hasattr(node, key):
                setattr(node, key, value)

    def link_citation_to_child_root(self, citation_node_id: str, child_root_id: str) -> None:
        """
        Simulate replacing a citation with a CITES_GRAPH edge to the child root.
        """
        # Find parent edge
        parent_id = None
        for parent, child in list(self.edges):
            if child == citation_node_id:
                parent_id = parent
                self.edges.discard((parent, child))
        # Remove citation node
        self.nodes.pop(citation_node_id, None)

        if parent_id:
            self.edges.add((parent_id, child_root_id))
