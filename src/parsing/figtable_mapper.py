import os
import re
from typing import Dict, List, Optional, Tuple


def parse_simplified_markdown_figures(simplified_md_path: str) -> Dict[str, str]:
    """
    Scan simplified markdown for image declarations with IDs.
    Returns mapping: figure_id -> asset_path
    
    Looks for: ![caption](path){#fig:id}
    """
    if not os.path.exists(simplified_md_path):
        return {}
    
    figure_map: Dict[str, str] = {}
    image_pattern = re.compile(r"!\[([^\]]*)\]\(([^\)]+)\)(?:\s*\{#([^\}]+)\})?", re.MULTILINE | re.DOTALL)
    
    with open(simplified_md_path, "r", encoding="utf-8") as f:
        content = f.read()
        
    for match in image_pattern.finditer(content):
        path = match.group(2).strip()
        fig_id = match.group(3) if match.lastindex >= 3 else None
        if fig_id:
            figure_map[fig_id] = path
    
    return figure_map


def parse_simplified_markdown_tables(simplified_md_path: str) -> Dict[str, Dict[str, str]]:
    """
    Scan simplified markdown for table blocks marked by TABLE_BEGIN/TABLE_END.

    Returns mapping: table_id -> {"text": <markdown table>, "caption": <optional>}
    """
    if not os.path.exists(simplified_md_path):
        return {}

    with open(simplified_md_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Match balanced blocks with the same id for BEGIN/END
    # Capture everything in between non-greedily
    block_re = re.compile(
        r"<!--\s*TABLE_BEGIN:\s*([^\s]+)\s*-->\s*"  # id in group 1
        r"(.*?)"                                        # inner content in group 2
        r"<!--\s*TABLE_END:\s*\1\s*-->",            # backref to same id
        re.DOTALL,
    )

    tables: Dict[str, Dict[str, str]] = {}

    for m in block_re.finditer(content):
        tab_id = m.group(1).strip()
        inner = m.group(2)

        # Extract caption if present
        caption_match = re.search(r"<!--\s*TABLE_CAPTION:\s*(.+?)\s*-->", inner)
        caption = caption_match.group(1).strip() if caption_match else ""
        if not caption:
            # Also support colon-prefixed caption lines just before TABLE_END
            colon_caps = re.findall(r"^\s*:\s*(.+?)\s*$", inner, flags=re.MULTILINE)
            if colon_caps:
                caption = colon_caps[-1].strip()

        # Remove inner comment marker lines, keep only the actual table markdown
        cleaned_lines: List[str] = []
        for line in inner.splitlines():
            if re.match(r"<!--\s*TABLE:\s*[^\s]+\s*-->", line):
                continue
            if re.match(r"<!--\s*TABLE_CAPTION:\s*.*-->", line):
                continue
            # Drop colon-prefixed caption line from the table text
            if re.match(r"^\s*:\s+.+", line):
                continue
            # Preserve the actual markdown table content (including pipes and separators)
            cleaned_lines.append(line)
        table_text = "\n".join(cleaned_lines).strip()

        tables[tab_id] = {"text": table_text, "caption": caption}

    return tables

def find_unreferenced_figures_in_sections(
    simplified_md_path: str,
    sections: List[Dict],
    chunks: Dict[str, str],
    referenced_assets: set
) -> Dict[str, List[Dict[str, str]]]:
    """
    Find figures/tables that appear in sections but are not referenced.
    Returns mapping: section_title -> list of unreferenced assets
    """
    if not os.path.exists(simplified_md_path):
        return {}
    
    with open(simplified_md_path, "r", encoding="utf-8") as f:
        content = f.read()
    
    unreferenced_by_section: Dict[str, List[Dict[str, str]]] = {}
    
    # Split by headings to track sections
    heading_pattern = re.compile(r"^(#+)\s+(.+?)(?:\s*\{[^\}]+\})?\s*$", re.MULTILINE)
    image_pattern = re.compile(r"!\[([^\]]*)\]\(([^\)]+)\)(?:\s*\{#([^\}]+)\})?", re.DOTALL)
    
    # Find all headings and their positions
    headings = []
    for match in heading_pattern.finditer(content):
        level = len(match.group(1))
        title = match.group(2).strip()
        pos = match.start()
        headings.append((pos, level, title))
    
    # Find all images and map them to sections
    for img_match in image_pattern.finditer(content):
        caption = img_match.group(1) or ""
        path = img_match.group(2).strip()
        fig_id = img_match.group(3) if img_match.lastindex >= 3 else None
        img_pos = img_match.start()
        
        # Find which section this image belongs to
        current_section = "Preamble"  # Default for content before first heading
        for heading_pos, level, title in reversed(headings):
            if heading_pos < img_pos:
                current_section = title
                break
        
        # Check if this asset was already referenced
        if path not in referenced_assets:
            if current_section not in unreferenced_by_section:
                unreferenced_by_section[current_section] = []
            
            asset_info = {
                "type": "FIGURE",
                "asset": path,
                "caption": caption.replace('\n', ' ').strip(),
            }
            if fig_id:
                asset_info["label"] = fig_id
            
            unreferenced_by_section[current_section].append(asset_info)
    
    return unreferenced_by_section


def parse_latex_figures_tables(flattened_tex_path: str) -> Dict[str, Dict[str, str]]:
    """
    Scan a flattened LaTeX file and extract figure/table labels and associated asset paths.

    Returns a dict with keys:
      - figure_labels: label -> asset_path
      - table_labels: label -> asset_path (may be empty string if none)
      - figure_numbers: str(number) -> asset_path
      - table_numbers: str(number) -> asset_path
    """
    if not os.path.exists(flattened_tex_path):
        raise FileNotFoundError(flattened_tex_path)

    figure_labels: Dict[str, str] = {}
    table_labels: Dict[str, str] = {}
    figure_numbers: Dict[str, str] = {}
    table_numbers: Dict[str, str] = {}

    in_figure = False
    in_table = False
    current_asset: Optional[str] = None
    current_label: Optional[str] = None
    figure_index = 0
    table_index = 0

    include_re = re.compile(r"\\includegraphics[^\{]*\{([^}]+)\}")
    label_re = re.compile(r"\\label\{([^}]+)\}")

    with open(flattened_tex_path, "r", encoding="utf-8") as f:
        for raw_line in f:
            line = raw_line.strip()
            if line.startswith("\\begin{figure"):
                in_figure = True
                in_table = False
                current_asset = None
                current_label = None
                continue
            if line.startswith("\\begin{table"):
                in_figure = False
                in_table = True
                current_asset = None
                current_label = None
                continue
            if line.startswith("\\end{figure") and in_figure:
                figure_index += 1
                key = str(figure_index)
                if current_label:
                    if current_asset:
                        figure_labels[current_label] = current_asset
                    else:
                        figure_labels[current_label] = ""
                if current_asset:
                    figure_numbers[key] = current_asset
                in_figure = False
                current_asset = None
                current_label = None
                continue
            if line.startswith("\\end{table") and in_table:
                table_index += 1
                key = str(table_index)
                if current_label:
                    table_labels[current_label] = current_asset or ""
                if current_asset:
                    table_numbers[key] = current_asset
                in_table = False
                current_asset = None
                current_label = None
                continue

            # Within environments, capture includegraphics and label
            if in_figure or in_table:
                m_inc = include_re.search(line)
                if m_inc:
                    asset = m_inc.group(1).strip()
                    # normalize missing extension: leave as-is; assets_preparer should ensure accessibility
                    current_asset = asset
                m_lab = label_re.search(line)
                if m_lab:
                    current_label = m_lab.group(1).strip()

    return {
        "figure_labels": figure_labels,
        "table_labels": table_labels,
        "figure_numbers": figure_numbers,
        "table_numbers": table_numbers,
    }


def detect_chunk_mentions(
    chunks: Dict[str, str]
) -> Dict[str, List[Dict[str, str]]]:
    """
    For each chunk, find references to figures/tables/citations via LaTeX refs and textual mentions.
    Returns mapping: chunk_id -> list of mentions where each mention is
      {"type": "FIGURE"|"TABLE"|"CITATION", "label": <optional>, "number": <optional>, "raw": <snippet>}
    """
    refs_fig = re.compile(r"\\ref\{(fig:[^}]+)\}")
    refs_tab = re.compile(r"\\ref\{(tab:[^}]+)\}")
    fig_num = re.compile(r"\b[Ff]igure\s+(\d+)\b")
    tab_num = re.compile(r"\b[Tt]able\s+(\d+)\b")
    # Markdown reference links: Figure [1](#fig:id) or Table [2](#tab:id)
    # Allow optional trailing Pandoc attribute blocks after the link
    md_fig_ref = re.compile(r"[Ff]igure\s+\[(\d+)\]\(#(fig:[^\)]+)\)\s*(?:\{[^}]*\})?")
    md_tab_ref = re.compile(r"[Tt]able\s+\[(\d+)\]\(#(tab:[^\)]+)\)\s*(?:\{[^}]*\})?")
    # Simplified markdown table markers: <!-- TABLE: id -->
    table_marker = re.compile(r"<!--\s*TABLE:\s*([^\s]+)\s*-->")
    table_caption_marker = re.compile(r"<!--\s*TABLE_CAPTION:\s*(.+?)\s*-->")
    # Citation patterns: [@key] or [@key1; @key2; @key3]
    # Allow any characters except closing bracket; multiple keys will be split by ',' or ';'
    citation_pattern = re.compile(r"\[@([^\]]+)\]")

    result: Dict[str, List[Dict[str, str]]] = {}
    for chunk_id, text in chunks.items():
        mentions: List[Dict[str, str]] = []
        # LaTeX refs
        for m in refs_fig.findall(text):
            mentions.append({"type": "FIGURE", "label": m, "raw": f"\\ref{{{m}}}"})
        for m in refs_tab.findall(text):
            mentions.append({"type": "TABLE", "label": m, "raw": f"\\ref{{{m}}}"})
        
        # Markdown reference links: Figure [1](#fig:id)
        for match in md_fig_ref.finditer(text):
            number = match.group(1)
            fig_id = match.group(2)
            mentions.append({"type": "FIGURE", "label": fig_id, "number": number, "raw": match.group(0)})
        for match in md_tab_ref.finditer(text):
            number = match.group(1)
            tab_id = match.group(2)
            mentions.append({"type": "TABLE", "label": tab_id, "number": number, "raw": match.group(0)})
        
        # Textual mentions (plain text, no markdown links)
        for m in fig_num.findall(text):
            mentions.append({"type": "FIGURE", "number": m, "raw": f"Figure {m}"})
        for m in tab_num.findall(text):
            mentions.append({"type": "TABLE", "number": m, "raw": f"Table {m}"})
        
        # NOTE: We no longer detect standalone markdown images in chunks
        # Images are only attached where they are REFERENCED (semantic links, not document order)
        # Markdown images and HTML embeds are skipped during chunk creation
        
        # Simplified markdown table markers: <!-- TABLE: id -->
        for match in table_marker.finditer(text):
            table_id = match.group(1)
            mentions.append({"type": "TABLE", "label": table_id, "raw": match.group(0)})
        
        # Table captions (attach to last table mention if present)
        captions = list(table_caption_marker.finditer(text))
        if captions and mentions:
            # Find last table mention and add caption
            for i in range(len(mentions) - 1, -1, -1):
                if mentions[i].get("type") == "TABLE":
                    mentions[i]["caption"] = captions[-1].group(1)
                    break
        
        # Citations: [@key] or [@key1; @key2]
        for match in citation_pattern.finditer(text):
            citation_content = match.group(1).strip()
            # Split by semicolon to handle multiple citations
            cite_keys = [k.strip().lstrip('@') for k in re.split(r'[;,]', citation_content)]
            for cite_key in cite_keys:
                cite_key = cite_key.strip()
                if cite_key:
                    mentions.append({"type": "CITATION", "key": cite_key, "raw": match.group(0)})
        
        if mentions:
            result[chunk_id] = mentions
    return result


