import os
import uuid
from typing import Dict, List, Tuple, Union

from indexing.models import (
    NodeType, PaperNode, RootNode, SectionNode, ChunkNode, 
    FigureNode, TableNode, CitationNode
)


def build_tree(
    paper_id: str,
    sections: List[Dict[str, Union[int, str, list]]],
    chunks: Dict[str, str],
    mentions_by_chunk: Dict[str, List[Dict[str, str]]],
    figtab_maps: Dict[str, Dict[str, str]],
    unreferenced_by_section: Dict[str, List[Dict[str, str]]] = None,
    citation_db: Dict[str, Dict[str, str]] = None,
    published_date: str = None,
    updated_date: str = None,
    paper_title: str = None,
) -> Dict[str, PaperNode]:
    """
    Build a PaperNode tree. Returns mapping node_id -> PaperNode.
    Root contains top-level sections as children. Figure/Table/Citation nodes are attached under the chunk node that mentions them.
    Unreferenced figures/tables are attached to their containing section.
    IDs are deterministic.
    """
    nodes: Dict[str, PaperNode] = {}
    section_nodes_by_title: Dict[str, str] = {}  # Track section titles to node IDs
    referenced_assets: set = set()  # Track which assets were referenced

    root_id = f"{paper_id}::ROOT"
    root = RootNode(
        id=root_id, 
        paper_id=paper_id, 
        node_type=NodeType.ROOT, 
        title=paper_title or f"Paper {paper_id}",
        publication_date=published_date,
        update_date=updated_date
    )
    nodes[root_id] = root

    # Counters for deterministic IDs
    section_counter = 0

    def get_section_id(index: int) -> str:
        return f"{paper_id}::SECTION::{index}"

    def add_section(section: Dict[str, Union[int, str, list]], parent_id: str) -> str:
        nonlocal section_counter
        section_counter += 1
        
        node_id = get_section_id(section_counter)
        level = int(section.get("level", 1))
        title = str(section.get("title", ""))
        
        # Special handling for bibliography (level=0) - always attach to root
        real_parent_id = parent_id
        if level == 0 and "bibliography" in title.lower():
            real_parent_id = root_id
            
        node = SectionNode(
            id=node_id,
            paper_id=paper_id,
            node_type=NodeType.SECTION,
            title=title,
            level=level if level > 0 else 1,
            parent_id=real_parent_id,
        )
        nodes[node_id] = node
        nodes[real_parent_id].children_ids.append(node_id)
        
        # Track section titles for unreferenced asset attachment
        nonlocal section_nodes_by_title
        section_nodes_by_title[title] = node_id

        for child in section.get("children", []) or []:
            if isinstance(child, dict) and "chunk_id" in child:  # text chunk placeholder
                chunk_id = str(child["chunk_id"])  # type: ignore[index]
                add_chunk(chunk_id, parent_id=node_id)
            else:
                add_section(child, parent_id=node_id)  # type: ignore[arg-type]
        return node_id

    def add_chunk(chunk_id: str, parent_id: str) -> str:
        nonlocal referenced_assets
        
        node_id = f"{paper_id}::CHUNK::{chunk_id}"
        text = chunks.get(chunk_id, "")
        node = ChunkNode(
            id=node_id,
            paper_id=paper_id,
            node_type=NodeType.TEXT_CHUNK,
            text=text,
            parent_id=parent_id,
        )
        nodes[node_id] = node
        nodes[parent_id].children_ids.append(node_id)

        # attach figures/tables/citations mentioned in this chunk
        mentions = mentions_by_chunk.get(chunk_id, [])
        for idx, mention in enumerate(mentions):
            mention_type = mention.get("type")
            
            if mention_type == "FIGURE":
                asset = mention.get("asset") or _resolve_asset_for_mention(mention, figtab_maps, kind="figure")
                if not asset or not str(asset).strip():
                    continue
                referenced_assets.add(asset)
                
                caption = mention.get("caption")
                node_meta = {}
                if caption:
                    node_meta["caption"] = caption
                if "label" in mention:
                    node_meta["label"] = mention["label"]
                
                add_figure_node(
                    parent_id=node_id,
                    asset_path=asset,
                    metadata=node_meta or None,
                    index=idx
                )
            
            elif mention_type == "TABLE":
                label = mention.get("label")
                table_text = ""
                if label:
                    table_text = figtab_maps.get("table_blocks", {}).get(label, "")
                
                caption = mention.get("caption")
                if not caption and label:
                    caption = figtab_maps.get("table_captions", {}).get(label)
                
                node_meta = {}
                if label:
                    node_meta["label"] = label
                if caption:
                    node_meta["caption"] = caption

                add_table_node(
                    parent_id=node_id,
                    text=table_text or (caption or "Table"),
                    caption=caption,
                    metadata=node_meta or None,
                    index=idx
                )
            
            elif mention_type == "CITATION":
                cite_key = mention.get("key")
                if cite_key and citation_db:
                    bib_entry = citation_db.get(cite_key)
                    if bib_entry:
                        add_citation_node(
                            parent_id=node_id,
                            citation_key=cite_key,
                            bib_entry=bib_entry,
                            index=idx
                        )
        return node_id

    def add_figure_node(parent_id: str, asset_path: str, metadata: Dict[str, str] | None, index: int) -> str:
        # ID: parent::FIGURE::index
        node_id = f"{parent_id}::FIGURE::{index}"
        
        caption = None
        if metadata and "caption" in metadata:
            caption = metadata["caption"]
        
        node = FigureNode(
            id=node_id,
            paper_id=paper_id,
            node_type=NodeType.FIGURE,
            caption=caption,
            asset_path=asset_path,
            parent_id=parent_id,
            metadata=metadata,
        )
        nodes[node_id] = node
        nodes[parent_id].children_ids.append(node_id)
        return node_id

    def add_table_node(parent_id: str, text: str, caption: str | None, metadata: Dict[str, str] | None, index: int) -> str:
        node_id = f"{parent_id}::TABLE::{index}"
        node = TableNode(
            id=node_id,
            paper_id=paper_id,
            node_type=NodeType.TABLE,
            caption=caption,
            table_content=text,
            parent_id=parent_id,
            metadata=metadata,
        )
        nodes[node_id] = node
        nodes[parent_id].children_ids.append(node_id)
        return node_id
    
    def add_citation_node(parent_id: str, citation_key: str, bib_entry: Dict[str, str], index: int) -> str:
        node_id = f"{parent_id}::CITATION::{index}"
        
        # Populate extracted_data dictionary with all raw info and hints
        extraction = {
            'text': bib_entry.get('text', ''),
            'citation_key': citation_key,
            'extracted_authors': bib_entry.get('authors', ''),
            'extracted_year': bib_entry.get('year', ''),
            'extracted_title': bib_entry.get('title', ''),
        }
        
        # Metadata field on BasePaperNode can be used for other things or left empty
        # We put extraction info in extracted_data
        
        node = CitationNode(
            id=node_id,
            paper_id=paper_id,
            node_type=NodeType.CITATION,
            extracted_data=extraction,
            parent_id=parent_id,
            # metadata=None # metadata defaults to None or can be used for non-extraction stuff
        )
        nodes[node_id] = node
        nodes[parent_id].children_ids.append(node_id)
        return node_id

    def _resolve_asset_for_mention(mention: Dict[str, str], maps: Dict[str, Dict[str, str]], kind: str) -> str:
        if "label" in mention:
            label = mention["label"]
            key = f"{kind}_labels"
            return maps.get(key, {}).get(label, "")
        if "number" in mention:
            number = mention["number"]
            key = f"{kind}_numbers"
            return maps.get(key, {}).get(number, "")
        return ""

    # Build sections under root
    for sec in sections:
        add_section(sec, parent_id=root_id)

    # Attach unreferenced figures/tables to their sections
    if unreferenced_by_section:
        for section_title, assets in unreferenced_by_section.items():
            section_node_id = section_nodes_by_title.get(section_title)
            if section_node_id:
                for idx, asset_info in enumerate(assets):
                    # Skip if already referenced
                    if asset_info.get("asset") in referenced_assets:
                        continue
                    
                    asset_type = asset_info.get("type")
                    metadata = {}
                    caption = None
                    if "caption" in asset_info:
                        caption = asset_info["caption"]
                        metadata["caption"] = caption
                    if "label" in asset_info:
                        metadata["label"] = asset_info["label"]
                    
                    asset_path = asset_info.get("asset", "")
                    if not asset_path or not str(asset_path).strip():
                        continue

                    if asset_type == "FIGURE":
                        add_figure_node(
                            parent_id=section_node_id,
                            asset_path=asset_path,
                            metadata=metadata or None,
                            index=idx
                        )
                    elif asset_type == "TABLE":
                         add_table_node(
                            parent_id=section_node_id,
                            text=caption or "Table", # Fallback text
                            caption=caption,
                            metadata=metadata or None,
                            index=idx
                        )

    return nodes
