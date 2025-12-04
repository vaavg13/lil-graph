import shutil
import subprocess
import os
from pathlib import Path
from typing import Tuple, Optional

class LaTeXMLRunner:
    """
    Wraps the latexml and latexmlpost commands to convert LaTeX to semantic XML.
    """
    
    def __init__(self, timeout: int = 600):
        self.timeout = timeout
        if not shutil.which("latexml"):
            # We don't raise immediately to allow importing the class, 
            # but run() will fail if tools are missing.
            pass

    def run(self, tex_file: Path, output_dir: Path) -> Tuple[bool, Optional[Path], str]:
        """
        Runs the latexml -> latexmlpost pipeline.
        
        Args:
            tex_file: Path to the main LaTeX file
            output_dir: Directory where output should be generated
            
        Returns:
            Tuple of (success, path_to_xml, log_output)
        """
        if not shutil.which("latexml"):
            return False, None, "Error: 'latexml' command not found. Please install LaTeXML."
            
        tex_file = Path(tex_file).resolve()
        output_dir = Path(output_dir).resolve()
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Intermediate and final files
        xml_stem = tex_file.stem
        latexml_out = output_dir / f"{xml_stem}.latexml.xml"
        final_xml = output_dir / f"{xml_stem}.xml"
        
        logs = []
        
        # 1. Run latexml (LaTeX -> Intermediate XML)
        # We use --nocomments to reduce noise, and ensure we point to the file
        cmd_latexml = [
            "latexml",
            f"--dest={latexml_out}",
            "--quiet",  # Reduce verbosity
            f"--path={tex_file.parent}",
            str(tex_file),
        ]
        
        success, log = self._run_command(cmd_latexml, cwd=tex_file.parent)
        logs.append("=== latexml output ===")
        logs.append(log)
        
        if not success or not latexml_out.exists():
            return False, None, "\n".join(logs)
            
        # 2. Run latexmlpost (Intermediate XML -> Final Semantic XML)
        # We enable Cross-referencing, splitting (none), and math formats
        cmd_post = [
            "latexmlpost",
            f"--dest={final_xml}",
            "--format=xml",       # We want semantic XML, not HTML
            "--splitnaming=id",   # Naming scheme if we were splitting (we aren't)
            "--nosplit",          # Keep as single document
            "--pmml",             # Generate Presentation MathML
            "--cmml",             # Generate Content MathML (good for semantic understanding)
            "--mathtex",          # Keep original TeX for math
            "--quiet",
            str(latexml_out)
        ]
        
        success, log = self._run_command(cmd_post, cwd=output_dir)
        logs.append("\n=== latexmlpost output ===")
        logs.append(log)
        
        if not success or not final_xml.exists():
            return False, None, "\n".join(logs)
            
        return True, final_xml, "\n".join(logs)

    def _run_command(self, cmd: list, cwd: Path) -> Tuple[bool, str]:
        try:
            result = subprocess.run(
                cmd,
                cwd=str(cwd),
                capture_output=True,
                text=True,
                timeout=self.timeout,
                check=False  # We handle return codes manually
            )
            
            # LaTeXML often returns status 1 for "warnings" which are not fatal errors.
            # We assume fatal error if status > 1 or if output file missing (checked by caller)
            # Actually, let's just capture output and let caller verify file existence.
            # Status 0 is clean, 1 is warning, 2 is error, 3 fatal.
            is_success = result.returncode <= 1
            
            log_output = f"Command: {' '.join(cmd)}\nExit Code: {result.returncode}\n"
            log_output += f"STDOUT:\n{result.stdout}\n"
            log_output += f"STDERR:\n{result.stderr}\n"
            
            return is_success, log_output
            
        except subprocess.TimeoutExpired:
            return False, f"Command timed out after {self.timeout}s: {' '.join(cmd)}"
        except Exception as e:
            return False, f"Exception running command: {e}"

