import os
from typing import Dict, Any
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
        # Cypher query to merge nodes
        query = """
        UNWIND $batch AS row
        MERGE (n:Node {id: row.id})
        SET n += row.props
        """
        
        batch = []
        for node in nodes.values():
            props = node.model_dump(exclude={"children_ids", "parent_id", "embedding"})
            # Ensure complex types are serialized (e.g. metadata dict to string or flattened)
            if props.get("metadata"):
                 # Flatten metadata into main props with 'meta_' prefix for simplicity in Neo4j
                for k, v in props["metadata"].items():
                    props[f"meta_{k}"] = str(v)
                del props["metadata"]
            
            # Convert enums to string
            props["node_type"] = props["node_type"].value
            
            # Add specific Label based on type (e.g. :Paper, :Section)
            # Note: The Cypher above uses generic :Node. Ideally we dynamic label.
            # For simplicity in this batch, we stick to :Node and use a property 'type'
            
            batch.append({"id": node.id, "props": props})
            
        tx.run(query, batch=batch)
        
        # Second pass: Add specific labels
        # This is efficient enough for batching
        for label in set(n.node_type.value for n in nodes.values()):
            label_query = f"""
            UNWIND $ids AS id
            MATCH (n:Node {{id: id}})
            SET n :{label}
            """
            ids = [n.id for n in nodes.values() if n.node_type.value == label]
            if ids:
                tx.run(label_query, ids=ids)

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

    def query_subgraph(self, root_id: str, depth: int = 1) -> Dict[str, Any]:
        # TODO: Implement Cypher return
        return {}

