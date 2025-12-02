import os
import re
import uuid
from typing import Dict, List, Optional, Tuple, Union


Section = Dict[str, Union[int, str, List["Section"], List[Dict[str, str]]]]


def _split_paragraph_into_chunks(paragraph: str, chunk_char_limit: Optional[int]) -> List[str]:
    if not paragraph:
        return []
    # Paragraph-based chunking only: do not split further
    if chunk_char_limit is None or chunk_char_limit <= 0:
        return [paragraph]
    return [paragraph]


def extract_markdown_structure(
    paper_md_path: str,
    chunk_char_limit: Optional[int] = None,
) -> Tuple[List[Section], Dict[str, str], str]:
    """
    Parse a markdown file into a hierarchy of sections/subsections and text chunks.

    Returns:
        sections: list of top-level sections with nested children. Each section dict:
            {"level": int, "title": str, "children": List[Union[Section, {"chunk_id": str}]]}
        chunks: mapping chunk_id -> text
        bibliography: raw bibliography text (or empty string if none)
    """
    if not os.path.exists(paper_md_path):
        raise FileNotFoundError(paper_md_path)

    heading_re = re.compile(r"^(#{1,6})\s+(.*?)(\s+#+\s*)?$")
    # Regex for detecting standalone markdown images (to skip them as text chunks)
    standalone_image_re = re.compile(r"^!\[([^\]]*)\]\(([^\)]+)\)(?:\s*\{#([^\}]+)\})?\s*$")
    # Regex for HTML comment markers (to skip)
    comment_marker_re = re.compile(r"^<!--.*-->\s*$")
    
    sections_stack: List[Section] = []
    top_sections: List[Section] = []
    chunks: Dict[str, str] = {}

    with open(paper_md_path, "r", encoding="utf-8") as f:
        lines = f.read().splitlines()

    paragraph_lines: List[str] = []
    in_bibliography = False
    bibliography_lines: List[str] = []
    bibliography_text = ""

    def flush_paragraph_as_chunks() -> None:
        nonlocal paragraph_lines
        if not paragraph_lines:
            return
        paragraph = "\n".join(paragraph_lines).strip()
        paragraph_lines = []
        if not paragraph:
            return
        
        # Skip if paragraph is ONLY a markdown image (possibly multi-line)
        # Images will be attached to chunks that REFERENCE them, not where they appear
        if paragraph.startswith("![") and (paragraph.endswith(")") or re.search(r"\)\s*\{#[^\}]+\}\s*$", paragraph)):
            image_pattern = r"^!\[([^\]]*)\]\(([^\)]+)\)(?:\s*\{#([^\}]+)\})?\s*$"
            if re.match(image_pattern, paragraph, re.DOTALL):
                # Skip standalone images - they'll be attached via references only
                return
        
        # Skip if paragraph is ONLY an HTML comment marker (table markers, etc.)
        if paragraph.startswith("<!--") and paragraph.endswith("-->"):
            return
            
        for chunk_text in _split_paragraph_into_chunks(paragraph, chunk_char_limit):
            chunk_id = str(uuid.uuid4())
            chunks[chunk_id] = chunk_text
            
            # attach chunk to current section (or create implicit section if none)
            carrier: Optional[Section] = sections_stack[-1] if sections_stack else None
            if carrier is None:
                # create an implicit root-level section to hold leading content
                carrier = {"level": 1, "title": "Preamble", "children": []}  # type: ignore[assignment]
                top_sections.append(carrier)
                sections_stack.append(carrier)
            children: List[Union[Section, Dict[str, str]]] = carrier.setdefault("children", [])  # type: ignore[assignment]
            children.append({"chunk_id": chunk_id})

    for raw_line in lines:
        line = raw_line.rstrip()
        
        # Skip standalone markdown images (they'll be attached as FIGURE nodes via mentions)
        if standalone_image_re.match(line):
            flush_paragraph_as_chunks()
            continue
        
        # Skip HTML comment markers (TABLE markers, captions, etc.)
        if comment_marker_re.match(line):
            flush_paragraph_as_chunks()
            continue
        
        # Detect bibliography fenced block start (3 colons)
        if not in_bibliography and line.strip().startswith("::: thebibliography"):
            # Flush any open paragraph and start capturing bibliography
            flush_paragraph_as_chunks()
            in_bibliography = True
            bibliography_lines = []
            continue
        # Inside bibliography block, capture until closing ':::' (3 colons, standalone)
        if in_bibliography:
            if line.strip() == ":::":
                # Store bibliography text but don't create a section for it
                # Bibliography entries will be attached to chunks where they're cited
                bibliography_text = "\n".join(bibliography_lines).strip()
                in_bibliography = False
                continue
            bibliography_lines.append(line)
            continue

        m = heading_re.match(line)
        if m:
            # flush pending paragraph when encountering a heading
            flush_paragraph_as_chunks()
            level = len(m.group(1))
            title = _clean_heading_title(m.group(2).strip())
            new_section: Section = {"level": level, "title": title, "children": []}

            # adjust stack to correct level
            while sections_stack and int(sections_stack[-1]["level"]) >= level:
                sections_stack.pop()
            if sections_stack:
                parent = sections_stack[-1]
                parent_children: List[Union[Section, Dict[str, str]]] = parent.setdefault("children", [])  # type: ignore[assignment]
                parent_children.append(new_section)
            else:
                top_sections.append(new_section)
            sections_stack.append(new_section)
        else:
            # accumulate paragraph lines; blank line flushes paragraph
            if line.strip() == "":
                flush_paragraph_as_chunks()
            else:
                paragraph_lines.append(line)

    # flush any trailing paragraph
    flush_paragraph_as_chunks()

    return top_sections, chunks, bibliography_text


def _clean_heading_title(title: str) -> str:
    """Normalize heading titles from pandoc conversion artifacts.

    - Remove trailing attribute blocks like {#id} or {reference-type="ref" ...}
    - Replace markdown links [text](url) with just 'text'
    - Collapse excessive whitespace
    """
    # Strip one or more trailing brace blocks
    while True:
        new_title = re.sub(r"\s*\{[^{}]*\}\s*$", "", title)
        if new_title == title:
            break
        title = new_title

    # Replace inline markdown links with their text content
    title = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", title)

    # Collapse whitespace
    title = re.sub(r"\s+", " ", title).strip()
    return title


