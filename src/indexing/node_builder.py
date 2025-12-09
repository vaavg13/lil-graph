from typing import Dict, List, Tuple, Any, Optional

from .models import (
    NodeType,
    PaperNode,
    SectionNode,
    ChunkNode,
    FigureNode,
    ImageNode,
    TableNode,
    CitationNode,
    RawLatexNode,
    AlgorithmNode,
    EquationNode,
    ProofNode,
    BlockNode,
    GraphNode,
)


class NodeBuilder:
    """
    Builds a PaperNode graph from parsed AST data.
    Converts hierarchical sections/chunks into a flat dictionary of nodes with parent-child relationships.
    """
    
    def __init__(
        self,
        arxiv_id: str,
        parsed_data: Dict[str, Any],
        paper_title: Optional[str] = None,
        published_date: Optional[str] = None,
        updated_date: Optional[str] = None,
        merge_section_chunks: bool = True,
    ):
        self.arxiv_id = arxiv_id
        self.parsed_data = parsed_data
        self.paper_title = paper_title
        self.published_date = published_date
        self.updated_date = updated_date
        self.merge_section_chunks = merge_section_chunks
        
        self.nodes: Dict[str, GraphNode] = {}
        self.chunk_id_to_node_id: Dict[str, str] = {}
        self.node_id_to_chunk_id: Dict[str, str] = {}
        self.chunk_data_map: Dict[str, Dict[str, Any]] = {}
        self.raw_label_index: Dict[str, List[Dict[str, Any]]] = {}
        self.used_labels: set[str] = set()
        
        self.section_counter = 0
        self.chunk_counter = 0
        self.raw_latex_counter = 0
    
    def build(self) -> Dict[str, GraphNode]:
        """Build and return the complete node graph."""
        self._create_root_node()
        self._prepare_chunk_data_map()
        self._process_sections()
        self._prepare_raw_label_index()
        self._process_raw_latex_blocks()
        self._attach_raw_latex_by_reference()
        self._collect_used_labels()
        self._process_standalone_tables()
        return self.nodes
    
    def _create_root_node(self):
        """Create the root node for the paper."""
        root_id = f"{self.arxiv_id}::ROOT"
        abstract_text = self.parsed_data.get("abstract")
        
        root_node = PaperNode(
            id=root_id,
            paper_id=self.arxiv_id,
            title=self.paper_title or self.parsed_data.get("metadata", {}).get("title", "Untitled"),
            abstract=abstract_text,
            publication_date=self.published_date,
            update_date=self.updated_date,
            children_ids=[]
        )
        self.nodes[root_id] = root_node

    def _prepare_chunk_data_map(self):
        """Precompute chunk_id -> chunk_data (including merged ids)."""
        chunk_data_map: Dict[str, Dict[str, Any]] = {}
        for section in self.parsed_data.get("sections", []):
            for chunk in section.get("chunks", []):
                if "chunk_id" in chunk:
                    chunk_data_map[chunk["chunk_id"]] = chunk
                for merged_id in chunk.get("_merged_from", []):
                    chunk_data_map[merged_id] = chunk
        self.chunk_data_map = chunk_data_map
    
    def _process_sections(self):
        """Process all sections and their chunks."""
        root_id = f"{self.arxiv_id}::ROOT"
        section_stack: List[Tuple[str, int]] = [(root_id, 0)]
        
        for section_data in self.parsed_data.get("sections", []):
            title = section_data.get("title", "")
            level = section_data.get("level", 1)
            section_chunks = section_data.get("chunks", [])
            
            # Merge chunks if requested
            if self.merge_section_chunks and section_chunks:
                section_chunks = self._merge_chunks(section_chunks)
            
            # Determine parent section
            while len(section_stack) > 1 and section_stack[-1][1] >= level:
                section_stack.pop()
            
            parent_id, _ = section_stack[-1]
            
            # Create section node
            section_id = self._create_section_node(title, level, parent_id)
            section_stack.append((section_id, level))
            
            # Process chunks in this section
            for chunk_data in section_chunks:
                if chunk_data.get("text", "").strip():
                    self._create_chunk_node(chunk_data, section_id)
    
    def _merge_chunks(self, chunks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Merge multiple chunks into a single chunk."""
        merged_text_parts: List[str] = []
        merged_citations: List[str] = []
        merged_references: List[Dict[str, Any]] = []
        merged_chunk_ids: List[str] = []
        
        for chunk_data in chunks:
            text_fragment = chunk_data.get("text", "")
            if text_fragment.strip():
                merged_text_parts.append(text_fragment.strip())
            merged_citations.extend(chunk_data.get("citations", []))
            merged_references.extend(chunk_data.get("references", []))
            if "chunk_id" in chunk_data:
                merged_chunk_ids.append(chunk_data["chunk_id"])
        
        if not merged_text_parts:
            return []
        
        return [{
            "chunk_id": merged_chunk_ids[0] if merged_chunk_ids else f"merged_{self.chunk_counter}",
            "text": "\n\n".join(merged_text_parts),
            "citations": merged_citations,
            "references": merged_references,
            "_merged_from": merged_chunk_ids
        }]
    
    def _create_section_node(self, title: str, level: int, parent_id: str) -> str:
        """Create a section node and add it to the graph."""
        section_id = f"{self.arxiv_id}::SEC::{self.section_counter}"
        self.section_counter += 1
        
        section_node = SectionNode(
            id=section_id,
            paper_id=self.arxiv_id,
            title=title,
            level=level,
            parent_id=parent_id,
            children_ids=[]
        )
        self.nodes[section_id] = section_node
        self.nodes[parent_id].children_ids.append(section_id)
        
        return section_id
    
    def _create_chunk_node(self, chunk_data: Dict[str, Any], parent_id: str):
        """Create a chunk node with its associated assets and citations."""
        chunk_id = f"{self.arxiv_id}::CHUNK::{self.chunk_counter}"
        self.chunk_counter += 1
        
        # Track mapping for O(1) lookup later
        original_chunk_id = chunk_data.get("chunk_id")
        if original_chunk_id:
            self.chunk_id_to_node_id[original_chunk_id] = chunk_id
            self.node_id_to_chunk_id[chunk_id] = original_chunk_id
        
        # Handle merged chunks
        merged_from = chunk_data.get("_merged_from", [])
        for merged_id in merged_from:
            self.chunk_id_to_node_id[merged_id] = chunk_id
        if chunk_id not in self.node_id_to_chunk_id:
            self.node_id_to_chunk_id[chunk_id] = original_chunk_id or chunk_id
        
        # Create chunk node
        chunk_node = ChunkNode(
            id=chunk_id,
            paper_id=self.arxiv_id,
            text=chunk_data.get("text", ""),
            parent_id=parent_id,
            children_ids=[]
        )
        self.nodes[chunk_id] = chunk_node
        self.nodes[parent_id].children_ids.append(chunk_id)
        
        # Process references (now with full metadata)
        self._attach_references(chunk_data.get("references", []), chunk_id, chunk_node)
        
        # Process citations
        self._attach_citations(chunk_data.get("citations", []), chunk_id, chunk_node)
    
    def _attach_references(self, references: List[Dict[str, Any]], chunk_id: str, chunk_node: ChunkNode):
        """Attach figure/table nodes based on references."""
        for ref_obj in references:
            ref_type = ref_obj.get("type", "unknown")
            base_label = ref_obj.get("label", "")
            
            if ref_type == "image":
                # Use ImageNode for actual images
                img_id = f"{chunk_id}::IMG::{base_label}"
                img_node = ImageNode(
                    id=img_id,
                    paper_id=self.arxiv_id,
                    asset_path=ref_obj.get("asset_path", ""),
                    caption=ref_obj.get("caption"),
                    parent_id=chunk_id
                )
                self.nodes[img_id] = img_node
                chunk_node.children_ids.append(img_id)
            
            elif ref_type == "algorithm":
                alg_id = f"{chunk_id}::ALG::{base_label}"
                alg_node = AlgorithmNode(
                    id=alg_id,
                    paper_id=self.arxiv_id,
                    text=ref_obj.get("content") or "",  # Empty string if no content
                    parent_id=chunk_id
                )
                self.nodes[alg_id] = alg_node
                chunk_node.children_ids.append(alg_id)
            
            elif ref_type == "figure":
                # Generic figure (text-only figures, etc.)
                fig_id = f"{chunk_id}::FIG::{base_label}"
                fig_node = FigureNode(
                    id=fig_id,
                    paper_id=self.arxiv_id,
                    caption=ref_obj.get("caption"),
                    content=ref_obj.get("content"),
                    parent_id=chunk_id
                )
                self.nodes[fig_id] = fig_node
                chunk_node.children_ids.append(fig_id)
                
            elif ref_type == "table":
                table_content = ref_obj.get("content") or ""
                if not table_content.strip():
                    continue  # Parser should not emit empty table refs
                tbl_id = f"{chunk_id}::TBL::{base_label}"
                tbl_node = TableNode(
                    id=tbl_id,
                    paper_id=self.arxiv_id,
                    table_content=table_content,
                    caption=ref_obj.get("caption"),
                    parent_id=chunk_id
                )
                self.nodes[tbl_id] = tbl_node
                chunk_node.children_ids.append(tbl_id)
            
            elif ref_type == "equation":
                eq_id = f"{chunk_id}::EQ::{base_label}"
                eq_node = EquationNode(
                    id=eq_id,
                    paper_id=self.arxiv_id,
                    text=ref_obj.get("content") or "",
                    parent_id=chunk_id,
                )
                self.nodes[eq_id] = eq_node
                chunk_node.children_ids.append(eq_id)

            elif ref_type == "proof":
                proof_id = f"{chunk_id}::PROOF::{base_label}"
                proof_node = ProofNode(
                    id=proof_id,
                    paper_id=self.arxiv_id,
                    text=ref_obj.get("content") or "",
                    parent_id=chunk_id,
                )
                self.nodes[proof_id] = proof_node
                chunk_node.children_ids.append(proof_id)

            elif ref_type in {"theorem", "logical-block", "block"}:
                block_content = ref_obj.get("content") or ""
                if not block_content.strip():
                    continue  # Skip blocks with no content
                blk_id = f"{chunk_id}::BLK::{base_label}"
                blk_node = BlockNode(
                    id=blk_id,
                    paper_id=self.arxiv_id,
                    text=block_content,
                    block_type=ref_type,
                    parent_id=chunk_id,
                )
                self.nodes[blk_id] = blk_node
                chunk_node.children_ids.append(blk_id)
    
    def _attach_citations(self, citations: List[str], chunk_id: str, chunk_node: ChunkNode):
        """Attach citation nodes to a chunk."""
        bibliography = self.parsed_data.get("bibliography", {})

        for cite_key in citations:
            cite_node_id = f"{chunk_id}::CITE::{cite_key}"

            # Get extracted data from bibliography
            bib_entry = bibliography.get(cite_key, {})
            extracted_data = dict(bib_entry) if isinstance(bib_entry, dict) else {}
            if cite_key:
                extracted_data.setdefault("key", cite_key)
                extracted_data.setdefault("citation_key", cite_key)

            # NOTE: title/year/authors/doi will be resolved via CrossRef later
            cite_node = CitationNode(
                id=cite_node_id,
                paper_id=self.arxiv_id,
                parent_id=chunk_id,
                extracted_data=extracted_data,
                title=None,
                year=None,
                authors=[],
                children_ids=[]
            )
            self.nodes[cite_node_id] = cite_node
            chunk_node.children_ids.append(cite_node_id)
    
    def _process_raw_latex_blocks(self):
        """Process raw LaTeX blocks and attach them to chunks where they appear."""
        raw_latex_blocks = self.parsed_data.get("raw_latex_blocks", [])
        
        for raw_block in raw_latex_blocks:
            metadata = raw_block["metadata"]
            
            # Skip blocks that created asset nodes (already handled as FigureNode/TableNode)
            if metadata.get('should_create_asset', False):
                continue
            
            # Use chunk_id for O(1) lookup
            chunk_id_str = raw_block.get("chunk_id")
            if not chunk_id_str or chunk_id_str not in self.chunk_id_to_node_id:
                continue
            
            parent_node_id = self.chunk_id_to_node_id[chunk_id_str]
            
            # Create RawLatexNode
            raw_id = f"{parent_node_id}::RAW::{self.raw_latex_counter}"
            self.raw_latex_counter += 1
            
            raw_node = RawLatexNode(
                id=raw_id,
                paper_id=self.arxiv_id,
                parent_id=parent_node_id,
                content=raw_block["content"],
                env_type=metadata.get("env_type"),
                extracted_labels=metadata.get("labels", []),
                extracted_images=metadata.get("images", []),
                caption=metadata.get("caption")
            )
            self.nodes[raw_id] = raw_node
            self.nodes[parent_node_id].children_ids.append(raw_id)

    def _prepare_raw_label_index(self):
        """Index raw LaTeX blocks by label for O(1) lookup."""
        index: Dict[str, List[Dict[str, Any]]] = {}
        for raw_block in self.parsed_data.get("raw_latex_blocks", []):
            metadata = raw_block.get("metadata", {})
            if metadata.get("should_create_asset", False):
                continue
            for label in metadata.get("labels", []):
                index.setdefault(label, []).append(raw_block)
        self.raw_label_index = index
    
    def _attach_raw_latex_by_reference(self):
        """
        Attach raw LaTeX blocks to chunks that reference their labels.
        This handles cases where a chunk references a figure/table that exists as raw LaTeX.
        """
        raw_label_index = self.raw_label_index

        # For each chunk, check if it has unresolved references
        for node_id, node in list(self.nodes.items()):
            if node.node_type != NodeType.TEXT_CHUNK:
                continue
            
            # Get original chunk data to access references
            chunk_data = self._find_chunk_data_fast(node_id)
            if not chunk_data:
                continue
            
            references = chunk_data.get("references", [])
            for ref_obj in references:
                # Skip already resolved references
                if ref_obj.get("type") in ["image", "table"]:
                    continue
                
                # Check if this unresolved reference matches a raw latex label
                full_label = ref_obj.get("full_label", "")
                base_label = ref_obj.get("label", "")
                
                # Try both full and base label
                matching_blocks = raw_label_index.get(full_label) or raw_label_index.get(base_label)
                
                if matching_blocks:
                    # Attach raw latex node for this reference
                    for raw_block in matching_blocks:
                        metadata = raw_block["metadata"]
                        
                        raw_id = f"{node_id}::RAW::{self.raw_latex_counter}"
                        self.raw_latex_counter += 1
                        
                        raw_node = RawLatexNode(
                            id=raw_id,
                            paper_id=self.arxiv_id,
                            parent_id=node_id,
                            content=raw_block["content"],
                            env_type=metadata.get("env_type"),
                            extracted_labels=metadata.get("labels", []),
                            extracted_images=metadata.get("images", []),
                            caption=metadata.get("caption")
                        )
                        self.nodes[raw_id] = raw_node
                        node.children_ids.append(raw_id)
    
    def _collect_used_labels(self):
        """Collect labels already referenced to avoid duplicate asset attachments."""
        used: set[str] = set()
        for section in self.parsed_data.get("sections", []):
            for chunk in section.get("chunks", []):
                for ref in chunk.get("references", []):
                    fl = ref.get("full_label")
                    if fl:
                        used.add(fl)
                    lbl = ref.get("label")
                    if lbl:
                        used.add(lbl)
        self.used_labels = used
    
    def _find_chunk_data_fast(self, node_id: str) -> Optional[Dict[str, Any]]:
        """Fast lookup of chunk data using pre-built maps."""
        cid = self.node_id_to_chunk_id.get(node_id)
        if not cid:
            for candidate_cid, nid in self.chunk_id_to_node_id.items():
                if nid == node_id:
                    cid = candidate_cid
                    self.node_id_to_chunk_id[node_id] = cid
                    break
        if cid:
            return self.chunk_data_map.get(cid)
        return None

    def _find_chunk_data_by_node_id(self, node_id: str) -> Optional[Dict[str, Any]]:
         # Kept for compatibility but should be avoided in loops
         return self._find_chunk_data_fast(node_id)

    
    def _process_standalone_tables(self):
        """
        Process standalone tables/figures that weren't referenced.
        Attach them to the chunk/section where they appear in the document.
        """
        asset_registry = self.parsed_data.get("asset_registry", {})
        if not asset_registry:
            return
        
        # Process unreferenced assets
        for label, asset_info in asset_registry.items():
            if label in self.used_labels:
                continue  # Already attached via reference
            
            asset_type = asset_info.get("type")
            asset_chunk_id = asset_info.get("chunk_id")
            asset_section = asset_info.get("section")
            
            # Try to attach to the chunk where it appears
            parent_id = None
            if asset_chunk_id and asset_chunk_id in self.chunk_id_to_node_id:
                parent_id = self.chunk_id_to_node_id[asset_chunk_id]
            elif asset_section:
                # Find section node by title
                for node_id, node in self.nodes.items():
                    if node.node_type == NodeType.SECTION and node.title == asset_section:
                        parent_id = node_id
                        break
            
            if not parent_id:
                continue  # Can't find where to attach
            
            # Create appropriate node
            if asset_type == "image":
                img_id = f"{parent_id}::IMG::{label}"
                img_node = ImageNode(
                    id=img_id,
                    paper_id=self.arxiv_id,
                    asset_path=asset_info.get("path", ""),
                    caption=asset_info.get("caption"),
                    parent_id=parent_id
                )
                self.nodes[img_id] = img_node
                self.nodes[parent_id].children_ids.append(img_id)
            
            elif asset_type == "algorithm":
                alg_content = asset_info.get("content") or ""
                alg_id = f"{parent_id}::ALG::{label}"
                alg_node = AlgorithmNode(
                    id=alg_id,
                    paper_id=self.arxiv_id,
                    text=alg_content,
                    parent_id=parent_id
                )
                self.nodes[alg_id] = alg_node
                self.nodes[parent_id].children_ids.append(alg_id)
            
            elif asset_type == "figure":
                fig_id = f"{parent_id}::FIG::{label}"
                fig_node = FigureNode(
                    id=fig_id,
                    paper_id=self.arxiv_id,
                    caption=asset_info.get("caption"),
                    content=asset_info.get("content"),
                    parent_id=parent_id
                )
                self.nodes[fig_id] = fig_node
                self.nodes[parent_id].children_ids.append(fig_id)
                
            elif asset_type == "table":
                table_content = asset_info.get("content") or ""
                if not table_content.strip():
                    continue  # Skip tables with no content
                tbl_id = f"{parent_id}::TBL::{label}"
                tbl_node = TableNode(
                    id=tbl_id,
                    paper_id=self.arxiv_id,
                    table_content=table_content,
                    caption=asset_info.get("caption"),
                    parent_id=parent_id
                )
                self.nodes[tbl_id] = tbl_node
                self.nodes[parent_id].children_ids.append(tbl_id)

            # Equation handling removed as per requirement:
            # unreferenced equations are not extracted as standalone nodes
            
            elif asset_type == "proof":
                proof_content = asset_info.get("content") or ""
                proof_id = f"{parent_id}::PROOF::{label}"
                proof_node = ProofNode(
                    id=proof_id,
                    paper_id=self.arxiv_id,
                    text=proof_content,
                    parent_id=parent_id,
                )
                self.nodes[proof_id] = proof_node
                self.nodes[parent_id].children_ids.append(proof_id)

            elif asset_type in {"theorem", "logical-block", "block"}:
                block_content = asset_info.get("content") or ""
                if not block_content.strip():
                    continue  # Skip blocks with no content
                blk_id = f"{parent_id}::BLK::{label}"
                blk_node = BlockNode(
                    id=blk_id,
                    paper_id=self.arxiv_id,
                    text=block_content,
                    block_type=asset_type,
                    parent_id=parent_id,
                )
                self.nodes[blk_id] = blk_node
                self.nodes[parent_id].children_ids.append(blk_id)


def build_nodes_from_parsed_data(
    arxiv_id: str,
    parsed_data: Dict[str, Any],
    paper_title: Optional[str] = None,
    published_date: Optional[str] = None,
    updated_date: Optional[str] = None,
    merge_section_chunks: bool = True,
) -> Dict[str, PaperNode]:
    """
    Convert the parsed AST data into the flat dictionary of Node objects
    expected by the indexing/persistence layer.
    
    This is a convenience function that creates a NodeBuilder and returns the result.
    """
    builder = NodeBuilder(
        arxiv_id=arxiv_id,
        parsed_data=parsed_data,
        paper_title=paper_title,
        published_date=published_date,
        updated_date=updated_date,
        merge_section_chunks=merge_section_chunks
    )
    return builder.build()
