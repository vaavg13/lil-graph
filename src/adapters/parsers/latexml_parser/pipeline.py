import json
from pathlib import Path
from typing import Any, Dict

from ..pandoc_parser.assets_preparer import copy_assets
from ..parser_interface import ParserInterface
from ..common.latex_bibliography_extractor import extract_bibliography_from_latex
from .shell import LaTeXMLRunner
from .xml_processor import LaTeXMLProcessor

try:
    from ..pandoc_parser.bibliography_parser import parse_bib_file
except ImportError:
    parse_bib_file = None

class LaTeXMLParser(ParserInterface):
    """
    Parser implementation using LaTeXML for converting LaTeX to structured data.
    """
    
    def run(self) -> Dict[str, Any]:
        """
        Run the LaTeXML parsing pipeline.
        
        Returns:
            A dictionary with the standardized structure defined in ParserInterface.
        """
        print(f"Starting LaTeXML parsing pipeline for: {self.source_dir}")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.assets_dir.mkdir(parents=True, exist_ok=True)
        
        # 1. Find Main File (reusing simple heuristic or finding .tex file)
        main_file = self._find_main_file()
        if not main_file:
            print("Error: No main .tex file found.")
            return {"error": "No main .tex file found"}
            
        print(f"Main LaTeX file found: {main_file}")
        
        # 2. Run LaTeXML
        runner = LaTeXMLRunner()
        success, xml_path, log = runner.run(main_file, self.output_dir)
        
        if not success or not xml_path:
            print(f"LaTeXML failed:\n{log}")
            return {"error": f"LaTeXML failed: {log[:500]}..."}
            
        print(f"LaTeXML XML generated at: {xml_path}")
        
        # 3. Process XML
        processor = LaTeXMLProcessor()
        try:
            processor.process(xml_path)
            print(f"XML processed. Found {len(processor.sections)} sections.")
        except Exception as e:
            print(f"Error processing XML: {e}")
            import traceback
            traceback.print_exc()
            return {"error": f"XML processing failed: {str(e)}"}
            
        # 4. Handle Bibliography (Reuse existing logic or extracting from XML)
        bib_data = {}
        bib_files = list(self.source_dir.glob("*.bib"))
        
        if bib_files and parse_bib_file:
            print(f"Found .bib files: {[f.name for f in bib_files]}")
            for bib_f in bib_files:
                entries = parse_bib_file(str(bib_f), processor.citations)
                bib_data.update(entries)
        else:
            # Fallback to embedded bibliography in LaTeX source
            if not bib_files:
                print("No .bib files found. Scanning LaTeX sources for embedded bibliography.")
            
            # Check if LaTeXML extracted bibliography
            if processor.bibliography:
                print(f"Using LaTeXML extracted bibliography ({len(processor.bibliography)} entries)")
                bib_data.update(processor.bibliography)
            else:
                # Use regex extractor
                extracted_bib = extract_bibliography_from_latex(self.source_dir)
                if extracted_bib:
                    print(f"Extracted {len(extracted_bib)} bibliography entries from LaTeX sources.")
                    bib_data.update(extracted_bib)
                else:
                    print("Warning: No bibliography found.")
        
        # 5. Handle Assets
        # Copy images referenced in asset registry
        copy_assets(self.source_dir, self.assets_dir, processor.images)
        print(f"Copied {len(processor.images)} assets.")

        # 6. Construct Result
        result = {
            "metadata": processor.metadata,
            "abstract": processor.abstract_text,
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
            
        print(f"LaTeXML parsing complete. Saved to {output_json}")
        return result

    def _find_main_file(self) -> Path:
        """Simple heuristic to find main tex file."""
        # Check for explicitly named files often used as main
        candidates = ["main.tex", "ms.tex", "paper.tex", "article.tex"]
        for c in candidates:
            p = self.source_dir / c
            if p.exists():
                return p
        
        # If not found, look for file with \documentclass
        tex_files = list(self.source_dir.glob("*.tex"))
        for f in tex_files:
            try:
                content = f.read_text(encoding="utf-8", errors="ignore")
                if "\\documentclass" in content:
                    return f
            except:
                continue
                
        # Fallback to first tex file
        return tex_files[0] if tex_files else None

