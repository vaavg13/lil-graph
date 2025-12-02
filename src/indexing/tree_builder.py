import os
import uuid
from typing import Dict, List, Tuple, Union

from indexing.models import NodeType, PaperNode


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
) -> Dict[str, PaperNode]:
    """
    Build a PaperNode tree. Returns mapping node_id -> PaperNode.
    Root contains top-level sections as children. Figure/Table/Citation nodes are attached under the chunk node that mentions them.
    Unreferenced figures/tables are attached to their containing section.
    """
    nodes: Dict[str, PaperNode] = {}
    section_nodes_by_title: Dict[str, str] = {}  # Track section titles to node IDs
    referenced_assets: set = set()  # Track which assets were referenced

    root_id = f"{paper_id}::ROOT"
    root = PaperNode(
        id=root_id, 
        paper_id=paper_id, 
        node_type=NodeType.ROOT, 
        title=f"Paper {paper_id}",
        publication_date=published_date,
        update_date=updated_date
    )
    nodes[root_id] = root

    def add_section(section: Dict[str, Union[int, str, list]], parent_id: str) -> str:
        node_id = str(uuid.uuid4())
        level = int(section.get("level", 1))
        title = str(section.get("title", ""))
        
        # Special handling for bibliography (level=0) - always attach to root
        if level == 0 and "bibliography" in title.lower():
            parent_id = root_id
            
        node = PaperNode(
            id=node_id,
            paper_id=paper_id,
            node_type=NodeType.SECTION,  # All sections use the same type; hierarchy is in the tree structure
            title=title,
            level=level if level > 0 else 1,  # Store as level 1 but we know it's bibliography
            parent_id=parent_id,
        )
        nodes[node_id] = node
        nodes[parent_id].children_ids.append(node_id)
        
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
        node = PaperNode(
            id=node_id,
            paper_id=paper_id,
            node_type=NodeType.TEXT_CHUNK,
            text=text,
            parent_id=parent_id,
        )
        nodes[node_id] = node
        nodes[parent_id].children_ids.append(node_id)

        # attach figures/tables/citations mentioned in this chunk
        for mention in mentions_by_chunk.get(chunk_id, []):
            if mention.get("type") == "FIGURE":
                asset = mention.get("asset") or _resolve_asset_for_mention(mention, figtab_maps, kind="figure")
                # Only create a FIGURE node when we have a resolvable asset path
                if not asset or not str(asset).strip():
                    continue
                referenced_assets.add(asset)
                node_meta = {}
                if "caption" in mention:
                    node_meta["caption"] = mention["caption"]
                if "label" in mention:
                    node_meta["label"] = mention["label"]
                add_named_asset_node(
                    parent_id=node_id,
                    asset_path=asset,
                    kind=NodeType.FIGURE,
                    metadata=node_meta or None,
                )
            elif mention.get("type") == "TABLE":
                # Populate TABLE nodes with full markdown text and optional caption
                label = mention.get("label")
                table_text = ""
                if label:
                    table_text = figtab_maps.get("table_blocks", {}).get(label, "")
                # Fallback caption from maps if not present on mention
                caption = mention.get("caption")
                if not caption and label:
                    caption = figtab_maps.get("table_captions", {}).get(label)
                node_meta = {}
                if label:
                    node_meta["label"] = label
                # Create a TABLE node carrying its markdown text; title is caption if known
                add_table_node(
                    parent_id=node_id,
                    text=table_text or (caption or "Table"),
                    title=caption,
                    metadata=node_meta or None,
                )
            elif mention.get("type") == "CITATION":
                # Add citation node with bibliography data
                cite_key = mention.get("key")
                if cite_key and citation_db:
                    bib_entry = citation_db.get(cite_key)
                    if bib_entry:
                        add_citation_node(
                            parent_id=node_id,
                            citation_key=cite_key,
                            bib_entry=bib_entry,
                        )
        return node_id

    def add_asset_node(parent_id: str, asset_path: str, kind: NodeType) -> str:
        node_id = str(uuid.uuid4())
        node = PaperNode(
            id=node_id,
            paper_id=paper_id,
            node_type=kind,
            asset_path=asset_path,
            parent_id=parent_id,
        )
        nodes[node_id] = node
        nodes[parent_id].children_ids.append(node_id)
        return node_id

    def add_named_asset_node(parent_id: str, asset_path: str, kind: NodeType, metadata: Dict[str, str] | None) -> str:
        node_id = str(uuid.uuid4())
        title = None
        if metadata and "caption" in metadata:
            title = metadata["caption"]
        node = PaperNode(
            id=node_id,
            paper_id=paper_id,
            node_type=kind,
            title=title,
            asset_path=asset_path,
            parent_id=parent_id,
            metadata=metadata,
        )
        nodes[node_id] = node
        nodes[parent_id].children_ids.append(node_id)
        return node_id

    def add_table_node(parent_id: str, text: str, title: str | None, metadata: Dict[str, str] | None) -> str:
        node_id = str(uuid.uuid4())
        node = PaperNode(
            id=node_id,
            paper_id=paper_id,
            node_type=NodeType.TABLE,
            title=title,
            text=text,
            parent_id=parent_id,
            metadata=metadata,
        )
        nodes[node_id] = node
        nodes[parent_id].children_ids.append(node_id)
        return node_id
    
    def add_citation_node(parent_id: str, citation_key: str, bib_entry: Dict[str, str]) -> str:
        node_id = str(uuid.uuid4())
        # Use authors + year as title if available
        title = None
        if bib_entry.get('authors') and bib_entry.get('year'):
            title = f"{bib_entry['authors']}, {bib_entry['year']}"
        elif bib_entry.get('title'):
            title = bib_entry['title']
        
        # Store full bibliography text in the node's text field
        metadata = {
            'citation_key': citation_key,
            'authors': bib_entry.get('authors', ''),
            'year': bib_entry.get('year', ''),
            'title': bib_entry.get('title', ''),
        }
        
        node = PaperNode(
            id=node_id,
            paper_id=paper_id,
            node_type=NodeType.CITATION,
            title=title,
            text=bib_entry.get('text', ''),
            parent_id=parent_id,
            metadata=metadata,
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
                for asset_info in assets:
                    # Skip if already referenced
                    if asset_info.get("asset") in referenced_assets:
                        continue
                    
                    asset_type = NodeType.FIGURE if asset_info.get("type") == "FIGURE" else NodeType.TABLE
                    metadata = {}
                    if "caption" in asset_info:
                        metadata["caption"] = asset_info["caption"]
                    if "label" in asset_info:
                        metadata["label"] = asset_info["label"]
                    
                    asset_path = asset_info.get("asset", "")
                    # For unreferenced assets, also require non-empty asset path
                    if not asset_path or not str(asset_path).strip():
                        continue
                    add_named_asset_node(
                        parent_id=section_node_id,
                        asset_path=asset_path,
                        kind=asset_type,
                        metadata=metadata or None,
                    )

    return nodes
