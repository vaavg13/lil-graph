import os
import json
import re
from pathlib import Path
from typing import Optional, List, Any
import pypandoc

def find_main_tex_file(source_dir: str) -> str:
    """
    Find the main .tex file in the source directory.
    Heuristics:
    1. Look for \documentclass
    2. Look for common names (main.tex, ms.tex, etc.)
    3. Look for file with most \include/\input
    4. Largest file
    """
    source_path = Path(source_dir)
    if not source_path.exists():
        raise ValueError(f"Source directory does not exist: {source_dir}")

    tex_files = list(source_path.glob("**/*.tex"))
    if not tex_files:
        raise ValueError("No .tex files found in source directory")

    # Read all contents
    file_contents = {}
    for f in tex_files:
        try:
            file_contents[f] = f.read_text(encoding='utf-8', errors='ignore')
        except Exception:
            continue

    # 1. Look for \documentclass
    for f, content in file_contents.items():
        if r'\documentclass' in content:
            return str(f)

    # 2. Common names
    common_names = ['ms.tex', 'main.tex', 'paper.tex', 'article.tex']
    for name in common_names:
        candidate = source_path / name
        if candidate.exists():
            return str(candidate)

    # 3. Most includes
    candidates = []
    for f, content in file_contents.items():
        count = len(re.findall(r'\\(?:include|input)\s*\{', content))
        candidates.append((f, count))
    
    candidates.sort(key=lambda x: x[1], reverse=True)
    if candidates and candidates[0][1] > 0:
        return str(candidates[0][0])

    # 4. Largest file
    largest = max(tex_files, key=lambda f: f.stat().st_size)
    return str(largest)

def get_pandoc_ast(input_file: str) -> dict:
    """
    Convert an input file (LaTeX) to Pandoc JSON AST.
    Runs in the directory of the input file to resolve relative includes.
    """
    input_path = Path(input_file).resolve()
    source_dir = input_path.parent
    
    cwd = os.getcwd()
    try:
        os.chdir(source_dir)
        # Use relative path for pandoc to keep internal paths relative if possible
        output = pypandoc.convert_file(input_path.name, to='json', format='latex')
        return json.loads(output)
    finally:
        os.chdir(cwd)

def pandoc_blocks_to_markdown(blocks: List[Any], api_version: List[int] = None) -> str:
    """
    Convert a list of Pandoc AST blocks back to Markdown.
    Wraps the blocks in a dummy document structure for Pandoc to process.
    """
    if api_version is None:
        api_version = [1, 20] # Default fallback
        
    # Create a minimal AST wrapper
    doc = {
        "pandoc-api-version": api_version,
        "meta": {},
        "blocks": blocks
    }
    json_str = json.dumps(doc)
    return pypandoc.convert_text(json_str, to='markdown', format='json')
