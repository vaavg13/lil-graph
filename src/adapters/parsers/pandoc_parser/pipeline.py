import os
import shutil
import json
import re
from pathlib import Path
from typing import Dict, Any, Optional

from ..parser_interface import ParserInterface
from ..common.latex_bibliography_extractor import extract_bibliography_from_latex
from .utils import find_main_tex_file, get_pandoc_ast
from .ast_processor import AstProcessor
from .assets_preparer import copy_assets

try:
    from .bibliography_parser import parse_bib_file
except ImportError:
    parse_bib_file = None

class PandocParser(ParserInterface):
    """
    Orchestrates the parsing of a LaTeX project into a structured JSON representation using Pandoc.
    """
    
    def run(self) -> Dict[str, Any]:
        """
        Run the full parsing pipeline.
        Returns the structured data.
        """
        print(f"Starting parsing pipeline for: {self.source_dir}")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.assets_dir.mkdir(parents=True, exist_ok=True)
        
        # 1. Find Main File
        try:
            main_file = find_main_tex_file(str(self.source_dir))
            print(f"Main LaTeX file found: {main_file}")
        except Exception as e:
            print(f"Error finding main file: {e}")
            return {"error": str(e)}

        # 2. Generate AST
        try:
            ast = get_pandoc_ast(main_file)
            print("Pandoc AST generated successfully.")
        except Exception as e:
            print(f"Error generating AST: {e}")
            return {"error": f"Pandoc failed: {str(e)}"}

        # 3. Process AST
        processor = AstProcessor()
        processor.process(ast)
        print(f"AST processed. Found {len(processor.sections)} sections, {len(processor.citations)} citations, {len(processor.images)} images.")

        # 4. Handle Bibliography
        bib_data = {}
        bib_files = list(self.source_dir.glob("*.bib"))
        
        if bib_files and parse_bib_file:
            print(f"Found .bib files: {[f.name for f in bib_files]}")
            for bib_f in bib_files:
                entries = parse_bib_file(str(bib_f), processor.citations)
                bib_data.update(entries)
        else:
            if not bib_files:
                print("No .bib files found. Scanning LaTeX sources for embedded bibliography.")
            bib_data = extract_bibliography_from_latex(self.source_dir)
            if bib_data:
                print(f"Extracted {len(bib_data)} bibliography entries from LaTeX sources.")
            else:
                print("Warning: No bibliography found in LaTeX sources.")

        # 5. Handle Assets
        copy_assets(self.source_dir, self.assets_dir, processor.images)
        print("Assets copied.")

        # 6. Construct Final Output
        result = {
            "metadata": ast.get("meta", {}),
            "abstract": processor.abstract_text.strip(),
            "sections": processor.sections,
            "bibliography": bib_data,
            "tables": processor.tables,
            "images": processor.images,
            "asset_registry": processor.asset_registry,
            "raw_latex_blocks": processor.raw_latex_blocks
        }
        
        # Save result
        output_json = self.output_dir / "parsed_document.json"
        with open(output_json, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
            
        print(f"Parsing complete. Saved to {output_json}")
        return result


# Backward compatibility alias
ParsingPipeline = PandocParser
