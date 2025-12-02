import re
from typing import List, Dict, Any, Optional

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
        
        self._in_abstract = False
        self._in_bibliography = False

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

            # Save current section if it has content
            if self.current_section["chunks"]:
                self.sections.append(self.current_section)
            
            # Start new section
            self.current_section = {
                "title": text_content,
                "level": level,
                "chunks": []
            }

        elif t == "Para" or t == "Plain":
            text, cites = self._extract_text_and_cites(c)
            text = text.strip()
            if not text:
                return

            if self._in_abstract:
                self.abstract_text += text + "\n"
            elif self._in_bibliography:
                return
            else:
                self.current_section["chunks"].append({
                    "text": text,
                    "citations": cites
                })
                self.citations.update(cites)

        elif t == "Div":
            # Check for bibliography class
            # attr = [id, classes, keyvals]
            classes = []
            if len(c) > 0 and isinstance(c[0], list) and len(c[0]) > 1:
                classes = c[0][1]
            
            self._process_blocks(c[1])

        elif t == "Figure":
            _, caption_data, content_blocks = c
            self._process_blocks(content_blocks)

        elif t == "Table":
            from .utils import pandoc_blocks_to_markdown
            md = pandoc_blocks_to_markdown([block], self.pandoc_api_version)
            self.tables.append({
                "content": md,
                "caption": "" 
            })

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

    def _extract_text_and_cites(self, inlines: List[Dict[str, Any]]) -> tuple[str, List[str]]:
        text_parts = []
        cites = []

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
                    for cite_item in c[0]:
                        cites.append(cite_item.get("citationId", ""))
                    walk(c[1]) 
                elif t == "Code":
                    text_parts.append(f"`{c[1]}`")
                elif t == "Math":
                    text_parts.append(f"${c[1]}$")
                elif t == "Image":
                    target = c[2][0]
                    self.images.append(target)
                    text_parts.append(f"![Image]({target})")
                elif t == "Link":
                    walk(c[1]) 
                elif t in ["Emph", "Strong", "Strikeout", "Superscript", "Subscript", "SmallCaps", "Quoted"]:
                    content = c if t != "Quoted" else c[1]
                    walk(content)
                elif t == "RawInline":
                    if c[0] == "tex":
                        text_parts.append(c[1])
                elif t == "Span":
                    walk(c[1])
                else:
                    pass

        walk(inlines)
        return "".join(text_parts), cites

    def _extract_inline_text(self, inlines: List[Dict[str, Any]]) -> str:
        t, _ = self._extract_text_and_cites(inlines)
        return t

    def _blocks_to_text(self, blocks: List[Dict[str, Any]]) -> str:
        full_text = []
        for b in blocks:
             if b.get("t") in ["Para", "Plain"]:
                 t, _ = self._extract_text_and_cites(b.get("c", []))
                 full_text.append(t)
        return " ".join(full_text)
