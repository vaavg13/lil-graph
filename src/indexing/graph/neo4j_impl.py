import os
from typing import Dict, Any, List
from .interface import GraphPersister
from ..models import PaperNode, NodeType

# Try importing neo4j driver, handle if missing
try:
    from neo4j import GraphDatabase
    HAS_NEO4J = True
except ImportError:
    HAS_NEO4J = False


class Neo4jPersister(GraphPersister):
    """
    Production-grade Graph Database adapter.
    """

    def __init__(self, uri: str, auth: tuple):
        if not HAS_NEO4J:
            raise ImportError("neo4j package not found. Install it with: pip install neo4j")
        self.driver = GraphDatabase.driver(uri, auth=auth)

    def close(self):
        self.driver.close()

    def persist_nodes(self, nodes: Dict[str, PaperNode]) -> None:
        with self.driver.session() as session:
            # Batch write for performance
            session.execute_write(self._create_nodes_tx, nodes)
            session.execute_write(self._create_rels_tx, nodes)

    def _create_nodes_tx(self, tx, nodes: Dict[str, PaperNode]):
        # Group nodes by their specific label (from node_type)
        # to execute cleaner MERGE (n:Label ...) queries.
        nodes_by_type: Dict[str, List[Dict]] = {}

        for node in nodes.values():
            props = node.model_dump(exclude={"children_ids", "parent_id"})

            # Ensure complex types are serialized (e.g. metadata dict to string or flattened)
            if props.get("metadata"):
                # Flatten metadata into main props with 'meta_' prefix for simplicity in Neo4j
                for k, v in props["metadata"].items():
                    props[f"meta_{k}"] = str(v)
                del props["metadata"]

            # Serialize extracted_data dictionary for CitationNodes
            if props.get("extracted_data"):
                import json

                # Store as JSON string
                props["extracted_data"] = json.dumps(props["extracted_data"])

            # Convert enums to string
            props["node_type"] = props["node_type"].value

            # Group by node type (Label)
            label = props["node_type"]
            if label not in nodes_by_type:
                nodes_by_type[label] = []

            nodes_by_type[label].append({"id": node.id, "props": props})

        # Execute batch merge for each label
        for label, batch in nodes_by_type.items():
            # MERGE on specific Label ensures we use specific indexes if available
            # and avoids generic :Node contention.
            query = f"""
            UNWIND $batch AS row
            MERGE (n:{label} {{id: row.id}})
            SET n += row.props
            SET n:Node
            """
            tx.run(query, batch=batch)

    def _create_rels_tx(self, tx, nodes: Dict[str, PaperNode]):
        # Cypher to create hierarchy
        query = """
        UNWIND $rels AS rel
        MATCH (parent:Node {id: rel.parent_id})
        MATCH (child:Node {id: rel.child_id})
        MERGE (parent)-[:HAS_CHILD]->(child)
        """

        rels = []
        for node in nodes.values():
            for child_id in node.children_ids:
                if child_id in nodes:
                    rels.append({"parent_id": node.id, "child_id": child_id})

        if rels:
            tx.run(query, rels=rels)

    def update_citation_node(self, citation_node_id: str, fields: Dict[str, Any]) -> None:
        """
        Update properties on an existing citation node.
        """
        if not fields:
            return
        with self.driver.session() as session:
            session.execute_write(self._update_citation_tx, citation_node_id, fields)

    def _update_citation_tx(self, tx, citation_node_id: str, fields: Dict[str, Any]):
        query = """
        MATCH (c:CITATION {id: $cid})
        SET c += $fields
        """
        tx.run(query, cid=citation_node_id, fields=fields)

    def link_citation_to_child_root(self, citation_node_id: str, child_root_id: str) -> None:
        """
        Replace a citation node with a link to the child paper's root node.
        """
        with self.driver.session() as session:
            session.execute_write(self._link_citation_tx, citation_node_id, child_root_id)

    def _link_citation_tx(self, tx, citation_node_id: str, child_root_id: str):
        # Attach parent directly to the child root, then remove the citation node.
        query = """
        MATCH (parent:Node)-[r:HAS_CHILD]->(cite:CITATION {id: $cid})
        MATCH (child:ROOT {id: $child_root_id})
        MERGE (parent)-[:CITES_GRAPH]->(child)
        DELETE r
        DETACH DELETE cite
        """
        tx.run(query, cid=citation_node_id, child_root_id=child_root_id)

    def query_subgraph(self, root_id: str, depth: int = 1) -> Dict[str, Any]:
        # TODO: Implement Cypher return
        return {}

