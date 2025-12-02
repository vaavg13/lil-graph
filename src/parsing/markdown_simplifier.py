"""
Simplify Pandoc Markdown to clean, uniform markdown for easier indexing.

Converts:
- HTML <figure> tags → standard markdown images
- Pandoc fenced divs with tables → simplified table markers
- Pandoc attribute syntax {#id .class} → clean text
- Complex multi-element figures → multiple simple images
"""

import re
from typing import List, Tuple
from bs4 import BeautifulSoup


def simplify_markdown(pandoc_md: str) -> str:
    """
    Convert Pandoc Markdown to simplified, uniform markdown.
    
    Args:
        pandoc_md: Raw Pandoc markdown content
        
    Returns:
        Simplified markdown with uniform figure/table syntax
    """
    # Step 1: Convert HTML figures to markdown
    md = _convert_html_figures_to_markdown(pandoc_md)
    
    # Step 2: Simplify Pandoc fenced div tables
    md = _simplify_fenced_tables(md)
    
    # Step 3: Clean up Pandoc attribute syntax from images
    md = _clean_image_attributes(md)
    
    # Step 4: Clean up heading attributes
    md = _clean_heading_attributes(md)
    
    # Step 5: Normalize whitespace
    md = _normalize_whitespace(md)
    
    return md


def _convert_html_figures_to_markdown(text: str) -> str:
    """Convert HTML <figure> blocks to standard markdown images."""
    soup = BeautifulSoup(text, 'html.parser')
    
    for figure in soup.find_all('figure'):
        # Extract all embed/img sources
        sources = []
        for tag in figure.find_all(['embed', 'img']):
            src = tag.get('src', '')
            if src:
                sources.append(src)
        
        # Extract caption from figcaption or p tags
        caption = ''
        figcaption = figure.find('figcaption')
        if figcaption:
            caption = figcaption.get_text(strip=True)
        elif figure.find('p'):
            # Sometimes caption is in <p> tag
            caption = figure.find('p').get_text(strip=True)
        
        # Get figure ID if present
        fig_id = figure.get('id', '')
        
        # Build markdown replacement
        markdown_images = []
        for i, src in enumerate(sources):
            # Use caption for first image, modified caption for subsequent
            img_caption = caption if i == 0 else f"{caption} (part {i+1})"
            img_md = f"![{img_caption}]({src})"
            # ALL parts get the same ID so they're all attached when referenced
            if fig_id:
                img_md += f" {{#{fig_id}}}"
            markdown_images.append(img_md)
        
        # Replace figure with markdown
        replacement = '\n\n' + '\n\n'.join(markdown_images) + '\n\n'
        figure.replace_with(replacement)
    
    return str(soup)


def _simplify_fenced_tables(text: str) -> str:
    """
    Simplify Pandoc fenced div tables to markdown tables with metadata markers.
    
    Converts:
        :::: center
        ::: {#tab:id}
        | col1 | col2 |
        :::::
        
    To:
        <!-- TABLE_BEGIN: tab:id -->
        <!-- TABLE: tab:id -->
        | col1 | col2 |
        <!-- TABLE_CAPTION: caption text -->
        <!-- TABLE_END: tab:id -->
    """
    # Pattern to match fenced table blocks
    # Matches :::: (optional: center) through ::::
    pattern = r':::+\s*(?:center)?\s*\n::: \{#([^\}]+)\}[^\n]*\n(.*?)(?::\s*([^\n]+))?\n:::+\s*\n:::+'
    
    def replace_table(match):
        table_id = match.group(1)
        table_content = match.group(2).strip()
        caption = match.group(3) or ''
        
        result = []
        if table_id:
            result.append(f'<!-- TABLE_BEGIN: {table_id} -->')
            result.append(f'<!-- TABLE: {table_id} -->')
        result.append(table_content)
        if caption:
            result.append(f'<!-- TABLE_CAPTION: {caption} -->')
        if table_id:
            result.append(f'<!-- TABLE_END: {table_id} -->')
        
        return '\n\n' + '\n'.join(result) + '\n\n'
    
    text = re.sub(pattern, replace_table, text, flags=re.DOTALL)
    
    # Also handle simpler nested fenced divs (without center wrapper)
    pattern2 = r'::: \{#(tab:[^\}]+)\}[^\n]*\n(.*?)\n:::'
    
    def replace_simple_table(match):
        table_id = match.group(1)
        content = match.group(2).strip()
        
        # Check if content has a caption line (starts with :)
        lines = content.split('\n')
        caption = ''
        table_lines = []
        
        for line in lines:
            if line.strip().startswith(':') and not caption:
                caption = line.strip().lstrip(':').strip()
            else:
                table_lines.append(line)
        
        result = []
        if table_id:
            result.append(f'<!-- TABLE_BEGIN: {table_id} -->')
            result.append(f'<!-- TABLE: {table_id} -->')
        result.append('\n'.join(table_lines))
        if caption:
            result.append(f'<!-- TABLE_CAPTION: {caption} -->')
        if table_id:
            result.append(f'<!-- TABLE_END: {table_id} -->')
        
        return '\n\n' + '\n'.join(result) + '\n\n'
    
    text = re.sub(pattern2, replace_simple_table, text, flags=re.DOTALL)
    
    return text


def _clean_image_attributes(text: str) -> str:
    """
    Clean Pandoc attribute syntax from markdown images but preserve ID.
    
    Converts:
        ![caption](path){#fig:id .class width=50%}
    To:
        ![caption](path) {#fig:id}
    """
    # Pattern: ![...](...){...}
    # Keep only the ID attribute, remove others
    pattern = r'(!\[[^\]]*\]\([^\)]+\))\s*\{([^\}]+)\}'
    
    def clean_attrs(match):
        img_part = match.group(1)
        attrs = match.group(2)
        
        # Extract ID (starts with #)
        id_match = re.search(r'#([^\s\.]+)', attrs)
        if id_match:
            return f'{img_part} {{#{id_match.group(1)}}}'
        return img_part
    
    return re.sub(pattern, clean_attrs, text)


def _clean_heading_attributes(text: str) -> str:
    """
    Remove Pandoc attribute syntax from headings.
    
    Converts:
        # Heading {#id .unnumbered}
    To:
        # Heading
    """
    # Pattern: heading line ending with {...}
    pattern = r'^(#+\s+.*?)\s*\{[^\}]+\}\s*$'
    return re.sub(pattern, r'\1', text, flags=re.MULTILINE)


def _normalize_whitespace(text: str) -> str:
    """Normalize excessive blank lines and whitespace."""
    # Replace 3+ blank lines with 2
    text = re.sub(r'\n{4,}', '\n\n\n', text)
    
    # Remove trailing whitespace from lines
    text = re.sub(r'[ \t]+$', '', text, flags=re.MULTILINE)
    
    return text


def simplify_markdown_file(input_path: str, output_path: str) -> None:
    """
    Simplify a Pandoc markdown file and write to output.
    
    Args:
        input_path: Path to Pandoc markdown file
        output_path: Path to write simplified markdown
    """
    with open(input_path, 'r', encoding='utf-8') as f:
        pandoc_md = f.read()
    
    simplified = simplify_markdown(pandoc_md)
    
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(simplified)

