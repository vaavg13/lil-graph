import re
from typing import List, Dict, Any, Optional
from .raw_latex_processor import RawLatexProcessor

class AstProcessor:
    """
    Traverses the Pandoc JSON AST to extract structure, content, assets, and citations.
    """

    def __init__(self):
        self.sections = []  # List of {title, level, chunks}
        # Start with a generic section in case content appears before first header
        self.current_section = {"title": "Body", "level": 1, "chunks": []} 
        self.abstract_text = ""
        self.images = []  # List of image paths found
        self.tables = []  # List of {id, markdown_content, caption}
        self.citations = set() # Set of all citation keys found
        self.pandoc_api_version = [1, 20] 
        
        # Asset registry: {full_label: {"type": "image"|"table", "path": path, "content": content, "section": title, "chunk_id": id}}
        self.asset_registry = {}
        
        # Track current section for asset location
        self._current_section_title = "Body"
        
        # Raw LaTeX blocks: stored with metadata for later processing
        self.raw_latex_blocks = []  # List of {content, metadata, chunk_id}
        
        self._in_abstract = False
        self._in_bibliography = False
        self._current_figure_label = None  # Track labels within Figure blocks
        self._latex_processor = RawLatexProcessor()
        
        # Chunk ID tracking for O(1) lookups later
        self._chunk_counter = 0
        self._current_chunk_id = None

    def process(self, ast: Dict[str, Any]):
        """
        Process the entire AST.
        """
        self.pandoc_api_version = ast.get("pandoc-api-version", [1, 20])
        
        # Check metadata for abstract
        meta = ast.get("meta", {})
        if "abstract" in meta:
             self.abstract_text = self._meta_block_to_text(meta["abstract"])

        blocks = ast.get("blocks", [])
        self._process_blocks(blocks)
        
        # Add the final section if not empty and it's not the initial placeholder if unused
        if self.current_section["chunks"]:
            self.sections.append(self.current_section)
        
        # Post-process: Resolve forward references now that asset_registry is complete
        self._resolve_forward_references()

    def _meta_block_to_text(self, meta_val):
        t = meta_val.get("t", "")
        c = meta_val.get("c", [])
        if t == "MetaBlocks":
            return self._blocks_to_text(c)
        elif t == "MetaInlines":
            return self._extract_inline_text(c)
        elif isinstance(meta_val, list): 
             # Heuristic: if list of dicts with 't', treat as blocks
             if len(meta_val) > 0 and isinstance(meta_val[0], dict) and "t" in meta_val[0]:
                 return self._blocks_to_text(meta_val)
        return ""

    def _process_blocks(self, blocks: List[Dict[str, Any]]):
        """
        Recursively process a list of blocks.
        """
        for block in blocks:
            self._process_block(block)

    def _process_block(self, block: Dict[str, Any]):
        t = block.get("t", "")
        c = block.get("c", [])

        if t == "Header":
            level = c[0]
            text_content = self._extract_inline_text(c[2])
            lower_title = text_content.lower().strip()
            
            # Reset special flags
            self._in_abstract = False
            self._in_bibliography = False

            if lower_title == "abstract":
                self._in_abstract = True
                return
            
            if lower_title in ["references", "bibliography", "works cited"]:
                self._in_bibliography = True
                return

            # Save current section (even if empty - it may have subsections)
            # Don't save the initial "Body" placeholder if it's empty
            if self.current_section["chunks"] or self.current_section["title"] != "Body":
                self.sections.append(self.current_section)
            
            # Start new section
            self.current_section = {
                "title": text_content,
                "level": level,
                "chunks": []
            }
            self._current_section_title = text_content

        elif t == "Para" or t == "Plain":
            text, cites, refs = self._extract_text_and_cites(c)
            text = text.strip()
            if not text:
                return
            
            # Filter out layout artifacts (like r0.5 from wrapfigure)
            if re.match(r'^[rl]?\d*\.?\d+$', text):
                return

            if self._in_abstract:
                self.abstract_text += text + "\n"
            elif self._in_bibliography:
                return
            else:
                # Assign unique chunk ID
                chunk_id = f"chunk_{self._chunk_counter}"
                self._chunk_counter += 1
                self._current_chunk_id = chunk_id
                
                # Resolve references to get full metadata
                resolved_refs = self._resolve_references(refs)
                
                self.current_section["chunks"].append({
                    "chunk_id": chunk_id,
                    "text": text,
                    "citations": cites,
                    "references": resolved_refs
                })
                self.citations.update(cites)

        elif t == "Div":
            # Div structure: [attr, [content_blocks]]
            # attr = [id, classes, keyvals]
            content_blocks = c[1] if len(c) > 1 else []
            
            # Extract Div classes to check for special types
            div_classes = []
            if len(c) > 0 and isinstance(c[0], list) and len(c[0]) > 1:
                div_classes = c[0][1] if isinstance(c[0][1], list) else []
            
            # Try to find label: first check Div ID, then look for Span with ID inside
            label_found = None
            if len(c) > 0 and isinstance(c[0], list) and len(c[0]) > 0:
                div_id = c[0][0]
                if div_id:
                    label_found = div_id
            
            # If no label in Div ID, search for Span elements with IDs in content
            if not label_found:
                label_found = self._find_label_in_blocks(content_blocks)
            
            # For table* class Divs without labels, generate an ID based on section
            if not label_found and 'table*' in div_classes:
                label_found = f"table_{self._current_section_title.lower().replace(' ', '_')}_{len(self.asset_registry)}"
            
            # Try to extract caption from content (heuristic: long text paragraphs)
            caption_text = None
            for block in content_blocks:
                if block.get("t") in ["Para", "Plain"]:
                    text = self._blocks_to_text([block])
                    if text and len(text) > 30:  # Assume captions are longer text
                        caption_text = text
                        break
            
            # Set context for processing images inside
            if label_found:
                self._current_figure_label = label_found
            
            old_caption = getattr(self, '_current_caption', None)
            if caption_text:
                self._current_caption = caption_text
            
            # Process content blocks
            self._process_blocks(content_blocks)
            
            # Clear context
            self._current_figure_label = None
            self._current_caption = old_caption

        elif t == "Figure":
            # Figure structure: [attr, caption, [content_blocks]]
            # attr is [id, classes, key-value pairs]
            attr = c[0]
            caption_data = c[1]
            content_blocks = c[2]
            
            # Extract label from attr if present
            fig_id = attr[0] if isinstance(attr, list) and len(attr) > 0 else ""
            
            # Extract caption text
            caption_text = None
            if caption_data and len(caption_data) > 1:
                # caption_data is [short_caption, long_caption_blocks]
                caption_blocks = caption_data[1] if isinstance(caption_data, list) else caption_data
                if caption_blocks:
                    caption_text = self._blocks_to_text(caption_blocks)
            
            # Set context for processing images inside
            if fig_id:
                self._current_figure_label = fig_id
            
            # Store caption temporarily for image registration
            old_caption = getattr(self, '_current_caption', None)
            self._current_caption = caption_text
            
            # Process content blocks to find images
            self._process_blocks(content_blocks)
            
            # If this Figure has a label but no image was registered, 
            # register it anyway (e.g., for algorithms, text-only figures)
            # Also check for additional labels in content (multi-algorithm figures)
            if fig_id and fig_id not in self.asset_registry:
                # Extract content as text
                content_text = self._blocks_to_text(content_blocks)
                # Determine type based on label prefix
                asset_type = "algorithm" if fig_id.startswith("alg:") else "figure"
                self.asset_registry[fig_id] = {
                    "type": asset_type,
                    "path": None,
                    "caption": caption_text,
                    "content": content_text if content_text else None,
                    "section": self._current_section_title,
                    "chunk_id": self._current_chunk_id
                }
            
            # Handle multi-label figures (e.g., multiple algorithms in one figure* environment)
            all_labels = self._find_all_labels_in_blocks(content_blocks)
            for additional_label in all_labels:
                if additional_label and additional_label not in self.asset_registry and additional_label != fig_id:
                    content_text = self._blocks_to_text(content_blocks)
                    # Determine type based on label prefix
                    asset_type = "algorithm" if additional_label.startswith("alg:") else "figure"
                    self.asset_registry[additional_label] = {
                        "type": asset_type,
                        "path": None,
                        "caption": caption_text,  # Same caption as parent
                        "content": content_text if content_text else None,
                        "section": self._current_section_title,
                        "chunk_id": self._current_chunk_id
                    }
            
            # Clear context
            self._current_figure_label = None
            self._current_caption = old_caption

        elif t == "Table":
            from .utils import pandoc_blocks_to_markdown
            md = pandoc_blocks_to_markdown([block], self.pandoc_api_version)
            
            # Try to extract label from multiple sources:
            # 1. Current figure label context (from parent Div)
            # 2. Table attr
            # 3. Search in table content
            table_id = self._current_figure_label
            
            if not table_id and isinstance(c, list) and len(c) > 0:
                attr = c[0]
                if isinstance(attr, list) and len(attr) > 0:
                    table_id = attr[0]
            
            if not table_id:
                table_id = self._find_label_in_blocks([block])
            
            # Extract caption from table structure or context
            # Table structure: [attr, [short_caption, caption_blocks], ...]
            caption_text = getattr(self, '_current_caption', None)
            if not caption_text and isinstance(c, list) and len(c) > 1:
                caption_data = c[1]
                if caption_data and isinstance(caption_data, list) and len(caption_data) > 1:
                    caption_blocks = caption_data[1]
                    if caption_blocks:
                        caption_text = self._blocks_to_text(caption_blocks)
            
            self.tables.append({
                "content": md,
                "caption": caption_text or "",
                "label": table_id
            })
            
            # Register in asset registry
            if table_id:
                self.asset_registry[table_id] = {
                    "type": "table",
                    "content": md,
                    "caption": caption_text,
                    "section": self._current_section_title,
                    "chunk_id": self._current_chunk_id
                }

        elif t == "RawBlock":
            # Handle raw LaTeX blocks that Pandoc couldn't convert
            if c[0] == "latex":
                latex_content = c[1]
                
                # Use processor to extract metadata
                metadata = self._latex_processor.process_raw_block(latex_content)
                
                # Store the raw block with its metadata, including current chunk_id
                self.raw_latex_blocks.append({
                    "content": latex_content,
                    "metadata": metadata,
                    "chunk_id": self._current_chunk_id,
                    "section_title": self.current_section["title"]
                })
                
                # If it should create an asset node, register it
                if metadata.get('should_create_asset', False):
                    # Register images and labels in asset registry
                    for img_path in metadata.get('images', []):
                        self.images.append(img_path)
                    
                    # Associate first label with first image (simple heuristic)
                    labels = metadata.get('labels', [])
                    images = metadata.get('images', [])
                    if labels and images:
                        label = labels[0]
                        img_path = images[0]
                        self.asset_registry[label] = {
                            "type": "image",
                            "path": img_path,
                            "caption": metadata.get('caption')
                        }

        elif t in ["BlockQuote", "OrderedList", "BulletList", "DefinitionList"]:
            if t == "BlockQuote":
                self._process_blocks(c)
            elif t in ["OrderedList", "BulletList"]:
                items = c if t == "BulletList" else c[1]
                for item_blocks in items:
                    self._process_blocks(item_blocks)
            elif t == "DefinitionList":
                for term, defs in c:
                    for def_blocks in defs:
                        self._process_blocks(def_blocks)

        # Fallback
        elif isinstance(c, list) and len(c) > 0 and isinstance(c[0], dict) and "t" in c[0]:
             self._process_blocks(c)

    def _resolve_forward_references(self):
        """
        After all blocks are processed, go back and resolve references with type='unknown'.
        This handles forward references where the reference appears before the definition.
        """
        for section in self.sections:
            for chunk in section.get("chunks", []):
                references = chunk.get("references", [])
                for ref_obj in references:
                    if ref_obj.get("type") == "unknown":
                        # Try to resolve now that asset_registry is complete
                        full_label = ref_obj.get("full_label", "")
                        if full_label in self.asset_registry:
                            asset_info = self.asset_registry[full_label]
                            # Update the reference object
                            ref_obj["type"] = asset_info.get("type", "unknown")
                            ref_obj["asset_path"] = asset_info.get("path")
                            ref_obj["content"] = asset_info.get("content")
                            ref_obj["caption"] = asset_info.get("caption")
                            
                            # Update the text placeholder
                            old_placeholder = f"{{{{ref:{ref_obj['label']}}}}}"
                            if ref_obj["type"] == "image":
                                new_placeholder = f"{{{{fig:{ref_obj['label']}}}}}"
                            elif ref_obj["type"] == "algorithm":
                                new_placeholder = f"{{{{alg:{ref_obj['label']}}}}}"
                            elif ref_obj["type"] == "figure":
                                new_placeholder = f"{{{{fig:{ref_obj['label']}}}}}"
                            elif ref_obj["type"] == "table":
                                new_placeholder = f"{{{{tbl:{ref_obj['label']}}}}}"
                            else:
                                continue  # Keep as ref
                            
                            # Replace in chunk text
                            chunk["text"] = chunk["text"].replace(old_placeholder, new_placeholder)
    
    def _find_label_in_blocks(self, blocks: List[Dict[str, Any]]) -> Optional[str]:
        """
        Search for Span elements with IDs in blocks (used for finding labels).
        Returns the first label found, or None.
        """
        for block in blocks:
            if not isinstance(block, dict):
                continue
                
            t = block.get("t", "")
            c = block.get("c", [])
            
            if t in ["Para", "Plain"]:
                # Check inlines for Span with ID
                for inline in c:
                    if not isinstance(inline, dict):
                        continue
                    if inline.get("t") == "Span":
                        span_attr = inline["c"][0] if len(inline["c"]) > 0 else []
                        if isinstance(span_attr, list) and len(span_attr) > 0:
                            span_id = span_attr[0]
                            if span_id and not span_id.startswith("http"):
                                return span_id
            
            # Recursively search in nested structures
            if isinstance(c, list):
                for item in c:
                    if isinstance(item, list):
                        result = self._find_label_in_blocks(item)
                        if result:
                            return result
        
        return None
    
    def _find_all_labels_in_blocks(self, blocks: List[Dict[str, Any]]) -> List[str]:
        """
        Search for ALL Span elements with IDs in blocks.
        Returns list of all labels found.
        """
        labels = []
        
        def search(obj):
            if isinstance(obj, dict):
                if obj.get("t") == "Span":
                    span_attr = obj["c"][0] if len(obj.get("c", [])) > 0 else []
                    if isinstance(span_attr, list) and len(span_attr) > 0:
                        span_id = span_attr[0]
                        if span_id and not span_id.startswith("http"):
                            labels.append(span_id)
                
                # Recurse
                for value in obj.values():
                    search(value)
            elif isinstance(obj, list):
                for item in obj:
                    search(item)
        
        search(blocks)
        return labels
    
    def _clean_raw_tex(self, content: str) -> str:
        # Filter out common layout artifacts (e.g. from wrapfigure "r0.5")
        if re.match(r'^[rl]?\d*\.?\d+$', content.strip()):
            return ""
        return content

    def _extract_text_and_cites(self, inlines: List[Dict[str, Any]]) -> tuple[str, List[str], List[str]]:
        text_parts = []
        cites = []
        refs = []  # References to figures/tables

        def walk(nodes):
            for node in nodes:
                t = node.get("t", "")
                c = node.get("c", [])
                
                if t == "Str":
                    text_parts.append(c)
                elif t == "Space":
                    text_parts.append(" ")
                elif t == "SoftBreak":
                    text_parts.append(" ")
                elif t == "LineBreak":
                    text_parts.append("\n")
                elif t == "Cite":
                    current_cites = [cite_item.get("citationId", "") for cite_item in c[0]]
                    for cid in current_cites:
                        cites.append(cid)
                    
                    cite_key_str = ",".join(current_cites)
                    # Put display text first, then the citation marker
                    walk(c[1])
                    text_parts.append(f"{{{{cite:{cite_key_str}}}}}")

                elif t == "Code":
                    text_parts.append(f"`{c[1]}`")
                elif t == "Math":
                    text_parts.append(f"${c[1]}$")
                elif t == "Image":
                    # Image structure: [attr, alt_text, [target, title]]
                    target = c[2][0] if len(c) > 2 else ""
                    
                    # Register this image with a label if we're in a figure
                    if self._current_figure_label and target:
                        self.asset_registry[self._current_figure_label] = {
                            "type": "image",
                            "path": target,
                            "caption": getattr(self, '_current_caption', None),
                            "section": self._current_section_title,
                            "chunk_id": self._current_chunk_id
                        }
                    
                    # Track globally
                    if target:
                        self.images.append(target)
                    
                    # Don't add to text - images should only appear via references
                    
                elif t == "Link":
                    # Links might be references to figures/tables
                    # Link structure: [attr, [inline_content], [url, title]]
                    url = c[2][0] if len(c) > 2 else ""
                    
                    # Check if this is a reference (starts with #)
                    if url.startswith("#"):
                        ref_label = url[1:]  # Remove the #
                        refs.append(ref_label)
                        
                        # Resolve type immediately and insert final placeholder format
                        asset_info = self.asset_registry.get(ref_label, {})
                        asset_type = asset_info.get("type", "unknown")
                        base_label = self._strip_prefix(ref_label)
                        
                        # Insert final format based on asset type
                        if asset_type == "image":
                            text_parts.append(f"{{{{fig:{base_label}}}}}")
                        elif asset_type == "table":
                            text_parts.append(f"{{{{tbl:{base_label}}}}}")
                        else:
                            # Unknown type, use generic ref format
                            text_parts.append(f"{{{{ref:{base_label}}}}}")
                    else:
                        # Regular link, just process content
                        walk(c[1])
                        
                elif t in ["Emph", "Strong", "Strikeout", "Superscript", "Subscript", "SmallCaps", "Quoted"]:
                    content = c if t != "Quoted" else c[1]
                    walk(content)
                elif t == "RawInline":
                    if c[0] == "tex":
                        cleaned = self._clean_raw_tex(c[1])
                        if cleaned:
                            text_parts.append(cleaned)
                elif t == "Span":
                    walk(c[1])
                else:
                    pass

        walk(inlines)
        return "".join(text_parts), cites, refs

    def _extract_inline_text(self, inlines: List[Dict[str, Any]]) -> str:
        t, _, _ = self._extract_text_and_cites(inlines)
        return t

    def _blocks_to_text(self, blocks: List[Dict[str, Any]]) -> str:
        full_text = []
        for b in blocks:
             if b.get("t") in ["Para", "Plain"]:
                 t, _, _ = self._extract_text_and_cites(b.get("c", []))
                 full_text.append(t)
        return " ".join(full_text)
    
    def _strip_prefix(self, label: str) -> str:
        """Strip common prefixes like fig:, tab:, table:, figure: from labels."""
        prefixes = ["fig:", "figure:", "tab:", "table:", "tbl:"]
        label_lower = label.lower()
        for prefix in prefixes:
            if label_lower.startswith(prefix):
                return label[len(prefix):]
        return label
    
    def _resolve_references(self, ref_labels: List[str]) -> List[Dict[str, Any]]:
        """
        Resolve reference labels to full metadata objects.
        This is called during chunk creation to provide rich reference data.
        """
        resolved = []
        for label in ref_labels:
            asset_info = self.asset_registry.get(label, {})
            asset_type = asset_info.get("type", "unknown")
            base_label = self._strip_prefix(label)
            
            resolved.append({
                "full_label": label,
                "label": base_label,
                "type": asset_type,
                "asset_path": asset_info.get("path"),
                "content": asset_info.get("content"),
                "caption": asset_info.get("caption")
            })
        return resolved
