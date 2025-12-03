#!/usr/bin/env python3
"""Debug table AST structure."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from src.parsing.utils import get_pandoc_ast

source_dir = "/home/avgerinos/Projects/engine_v2/PAPER/2512.02008/source_extracted"
main_file = f"{source_dir}/main.tex"

ast = get_pandoc_ast(main_file)

print("=== TABLE BLOCKS ===")
for i, block in enumerate(ast.get('blocks', [])):
    if block.get('t') == 'Table':
        print(f"\n\nTable Block {i}:")
        print(json.dumps(block, indent=2)[:2000])  # First 2000 chars
        print("\n... (truncated)")
        break

