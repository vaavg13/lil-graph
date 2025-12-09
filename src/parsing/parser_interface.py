from abc import ABC, abstractmethod
from typing import Dict, Any, List
from pathlib import Path


class ParserInterface(ABC):
    """
    Abstract base class defining the interface that all parsers must implement.
    
    Parsers (e.g., PandocParser, LaTeXMLParser) should subclass this and implement
    the run() method to return a standardized parsed_data dictionary structure.
    
    The parsed_data structure is consumed by the indexing layer via build_nodes_from_parsed_data.
    """
    
    def __init__(self, source_dir: str, output_dir: str):
        """
        Initialize the parser.
        
        Args:
            source_dir: Directory containing the LaTeX source files
            output_dir: Directory where parsed output and assets should be stored
        """
        self.source_dir = Path(source_dir)
        self.output_dir = Path(output_dir)
        self.assets_dir = self.output_dir / "assets"
    
    @abstractmethod
    def run(self) -> Dict[str, Any]:
        """
        Run the parsing pipeline and return structured data.
        
        Returns:
            A dictionary with the following required keys:
            - metadata: Dict[str, Any] - Document metadata (title, authors, etc.)
            - abstract: str - The abstract text
            - sections: List[Dict[str, Any]] - List of section dictionaries, each containing:
                - title: str - Section title
                - level: int - Section level (1, 2, 3, ...)
                - chunks: List[Dict[str, Any]] - List of text chunks, each containing:
                    - chunk_id: str - Unique identifier for the chunk
                    - text: str - The chunk text content
                      (may include cross‑reference placeholders of the form
                      ``{{label}}`` where ``label`` is the exact LaTeX label
                      string, e.g. ``fig:results``)
                    - citations: List[str] - Citation keys referenced in this chunk
                    - references: List[Dict[str, Any]] - Figure/table/algorithm references, each containing:
                        - type: Optional[str] - Asset type as classified by the parser
                          (e.g., "image", "figure", "table", "algorithm",
                          "equation", "theorem", "proof", "logical-block",
                          "block")
                        - label: str - The label string used in the document
                          and in the ``{{label}}`` placeholder (e.g., "fig:results")
                        - full_label: str - Same as ``label``; kept for backward
                          compatibility and convenience
                        - caption: Optional[str] - Caption text
                        - content: Optional[str] - Asset content (e.g., table
                          markdown, algorithm/theorem body text)
                        - asset_path: Optional[str] - Path to image file
            - bibliography: Dict[str, Dict[str, Any]] - Mapping from citation key to metadata
            - tables: List[Dict[str, Any]] - Table metadata
            - images: List[str] - List of image paths
            - asset_registry: Dict[str, Dict[str, Any]] - Registry of all assets,
              keyed by the exact LaTeX label string. The parser, not the node
              builder, is responsible for classifying asset ``type``; callers
              should not infer type from the textual placeholders.
            - raw_latex_blocks: List[Dict[str, Any]] - Raw LaTeX blocks, each containing:
                - content: str - The raw LaTeX content
                - chunk_id: str - Which chunk this block appeared in
                - metadata: Dict[str, Any] - Metadata about the block, including:
                    - env_type: str - LaTeX environment type
                    - labels: List[str] - Extracted labels
                    - images: List[str] - Extracted image references
                    - caption: Optional[str] - Extracted caption
                    - should_create_asset: bool - Whether this should create an asset node
        """
        pass


