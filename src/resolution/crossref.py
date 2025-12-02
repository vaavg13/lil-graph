import time
import requests
from collections import OrderedDict
from typing import Dict, List, Optional, Any
from ..indexing.models import PaperNode, CitationNode, NodeType

# CrossRef API
# Doc: https://github.com/CrossRef/rest-api-doc
# Good etiquette: include 'mailto' in headers
CROSSREF_API_URL = "https://api.crossref.org/works"

class CrossRefResolver:
    def __init__(self, email: str = "your_email@example.com"):
        self.email = email
        self.headers = {
            "User-Agent": f"EngineV2/1.0 (mailto:{self.email})"
        }
        # CrossRef is generous but likes polite users. 
        # No strict rate limit for "Polite" pool if we send mailto.
        # But we should still be gentle.
        self.delay = 0.2 

    def resolve_citations(self, nodes: Dict[str, PaperNode]) -> None:
        """
        Iterate over all CitationNodes in the tree and attempt to resolve them online via CrossRef.
        Updates the node fields in-place.
        """
        citation_nodes: List[CitationNode] = [
            node
            for node in nodes.values()
            if isinstance(node, CitationNode) and node.node_type == NodeType.CITATION
        ]
        
        if not citation_nodes:
            print("Resolving 0 citations via CrossRef...")
            return
        
        keyed_nodes: "OrderedDict[str, List[CitationNode]]" = OrderedDict()
        unkeyed_nodes: List[CitationNode] = []
        
        for node in citation_nodes:
            ref_key = self._reference_key(node)
            if ref_key:
                if ref_key not in keyed_nodes:
                    keyed_nodes[ref_key] = []
                keyed_nodes[ref_key].append(node)
            else:
                unkeyed_nodes.append(node)
        
        if keyed_nodes:
            print(
                f"Resolving {len(keyed_nodes)} unique references "
                f"across {len(citation_nodes)} citation nodes via CrossRef..."
            )
        else:
            print(f"Resolving {len(citation_nodes)} citations via CrossRef...")
        
        for index, (ref_key, nodes_for_key) in enumerate(keyed_nodes.items(), start=1):
            paper = self._resolve_single_node(nodes_for_key[0])
            if paper and len(nodes_for_key) > 1:
                for duplicate in nodes_for_key[1:]:
                    self._update_node_with_paper_data(duplicate, paper)
            time.sleep(self.delay)
            if index % 10 == 0 or index == len(keyed_nodes):
                print(f"Processed {index}/{len(keyed_nodes)} references...")
        
        if unkeyed_nodes:
            print(f"Resolving {len(unkeyed_nodes)} citation nodes without reference keys via CrossRef...")
            for index, node in enumerate(unkeyed_nodes, start=1):
                self._resolve_single_node(node)
                time.sleep(self.delay)
                if index % 10 == 0 or index == len(unkeyed_nodes):
                    print(f"Processed {index}/{len(unkeyed_nodes)} unkeyed citations...")

    def _resolve_single_node(self, node: CitationNode) -> Optional[Dict[str, Any]]:
        query = None
        
        # Use extracted hints from extracted_data if available
        # Extraction dict is guaranteed to exist by model default
        if node.extracted_data.get("extracted_title"):
            query = node.extracted_data["extracted_title"]
        elif node.extracted_data.get("text"):
            # Fallback to raw text
            query = node.extracted_data["text"][:200]
        
        if not query or len(query.strip()) < 5:
            return

        try:
            # Use 'query.bibliographic' for raw citation text matching
            # or 'query.title' if we are sure it's a title.
            # Using query.bibliographic is safer for raw dumps.
            params = {
                "query.bibliographic": query,
                "rows": 1,
                "select": "DOI,title,abstract,container-title,published-print,published-online,author,URL"
            }
            
            response = requests.get(
                CROSSREF_API_URL, 
                params=params, 
                headers=self.headers, 
                timeout=10
            )
            
            if response.status_code == 200:
                data = response.json()
                items = data.get("message", {}).get("items", [])
                if items:
                    paper = items[0]
                    self._update_node_with_paper_data(node, paper)
                    return paper
            elif response.status_code == 429:
                print("Rate limit hit for CrossRef. Backing off...")
                time.sleep(5)
            else:
                pass
                
        except Exception as e:
            print(f"Error resolving citation {node.id}: {e}")
        return None

    def _update_node_with_paper_data(self, node: CitationNode, paper: Dict[str, Any]) -> None:
        # Title is often a list in CrossRef
        title_list = paper.get("title", [])
        if title_list:
            node.title = title_list[0]
        
        # Abstract is often missing or XML-escaped in CrossRef
        # but we check anyway.
        node.abstract = paper.get("abstract")
        
        container_title = paper.get("container-title", [])
        if container_title:
            node.venue = container_title[0]
            
        # Date handling
        pub_date = paper.get("published-print") or paper.get("published-online")
        if pub_date and "date-parts" in pub_date:
            parts = pub_date["date-parts"]
            if parts and parts[0]:
                node.year = parts[0][0]
        
        node.url = paper.get("URL")
        node.doi = paper.get("DOI")
        
        if paper.get("author"):
            node.authors = [
                f"{a.get('given', '')} {a.get('family', '')}".strip() 
                for a in paper["author"]
            ]

    def _reference_key(self, node: CitationNode) -> Optional[str]:
        data = node.extracted_data or {}
        for field in ("citation_key", "key"):
            value = data.get(field)
            if value and isinstance(value, str):
                return value
        return None


