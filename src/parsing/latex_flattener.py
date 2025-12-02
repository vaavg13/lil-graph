import os
import re
from pathlib import Path
from typing import Dict, Set

try:
    import pypandoc  # type: ignore
except Exception:  # pragma: no cover - optional at runtime
    pypandoc = None


class LatexFlattener:
    """Flattens LaTeX documents by replacing \include and \input commands with file contents."""

    def __init__(self, source_dir: str):
        self.source_dir = Path(source_dir)
        if not self.source_dir.exists():
            raise ValueError(f"Source directory does not exist: {source_dir}")

        self.tex_files: Dict[str, str] = {}  # filename -> content
        self.processed_files: Set[str] = set()
        self._load_tex_files()

    def _load_tex_files(self) -> None:
        """Load all .tex files from the source directory."""
        for tex_file in self.source_dir.glob("**/*.tex"):
            try:
                content = tex_file.read_text(encoding='utf-8', errors='ignore')
                # Use relative path as key
                rel_path = tex_file.relative_to(self.source_dir)
                self.tex_files[str(rel_path)] = content
            except Exception as e:
                print(f"Warning: Could not read {tex_file}: {e}")

    def _find_main_tex_file(self) -> str:
        """Find the main .tex file."""
        if not self.tex_files:
            raise ValueError("No .tex files found in source directory")

        # Priority: files with \documentclass (main files)
        for filename, content in self.tex_files.items():
            if r'\documentclass' in content:
                return filename

        # Fallback: common main file names
        main_names = ['ms.tex', 'main.tex', 'paper.tex', 'article.tex']
        for name in main_names:
            if name in self.tex_files:
                return name

        # Last resort: largest file (but prefer files with includes/inputs)
        candidates = []
        for filename, content in self.tex_files.items():
            if re.search(r'\\(?:include|input)\s*\{', content):
                candidates.append((filename, len(content)))

        if candidates:
            return max(candidates, key=lambda x: x[1])[0]

        # Final fallback: just the largest file
        return max(self.tex_files.keys(), key=lambda f: len(self.tex_files[f]))

    def _strip_comments(self, content: str) -> str:
        """Strip LaTeX comments from content."""
        lines = content.split('\n')
        cleaned_lines = []

        for line in lines:
            # Remove comments from lines
            # Find the first % that's not escaped
            comment_pos = -1
            i = 0
            while i < len(line):
                if line[i] == '%' and (i == 0 or line[i-1] != '\\'):
                    comment_pos = i
                    break
                i += 1

            if comment_pos >= 0:
                # Keep only the part before the comment
                cleaned_line = line[:comment_pos].rstrip()
                if cleaned_line:  # Only add non-empty lines
                    cleaned_lines.append(cleaned_line)
            else:
                # No comment, keep the whole line
                cleaned_lines.append(line)

        return '\n'.join(cleaned_lines)

    def _resolve_file_path(self, include_path: str, current_file_dir: str) -> str:
        """Resolve relative include paths to actual file paths."""
        # Remove .tex extension if present
        if include_path.endswith('.tex'):
            include_path = include_path[:-4]

        # Try different path combinations
        candidates = [
            include_path + '.tex',
            os.path.join(current_file_dir, include_path + '.tex'),
            include_path,  # already has .tex
            os.path.join(current_file_dir, include_path),
        ]

        for candidate in candidates:
            if candidate in self.tex_files:
                return candidate

        # If not found, return as-is (will cause error later)
        return include_path + ('.tex' if not include_path.endswith('.tex') else '')

    def _process_includes(self, content: str, current_file: str) -> str:
        """Recursively process \include and \input commands in content."""
        current_dir = os.path.dirname(current_file)

        def replace_include(match):
            command = match.group(1)  # 'include' or 'input'
            filename = match.group(2).strip()

            resolved_path = self._resolve_file_path(filename, current_dir)

            if resolved_path not in self.tex_files:
                print(f"Warning: Included file not found: {resolved_path}")
                return match.group(0)  # Keep original command

            if resolved_path in self.processed_files:
                print(f"Warning: Circular include detected for {resolved_path}")
                return f"% Circular include skipped: {resolved_path}\n"

            self.processed_files.add(resolved_path)
            included_content = self.tex_files[resolved_path]

            # Strip comments from included content first
            included_content = self._strip_comments(included_content)

            # Recursively process includes in the included content
            processed_content = self._process_includes(included_content, resolved_path)

            # Just return the processed content without markers
            return processed_content

        # Process \include and \input commands
        pattern = r'\\(include|input)\s*\{([^}]+)\}'
        return re.sub(pattern, replace_include, content)

    def flatten(self, output_file: str = None, strip_comments: bool = False) -> str:
        """Flatten the LaTeX document and return/save the result."""
        main_file = self._find_main_tex_file()
        print(f"Using main file: {main_file}")

        self.processed_files.clear()
        self.processed_files.add(main_file)

        main_content = self.tex_files[main_file]
        # Strip comments from main content first
        if strip_comments:
            main_content = self._strip_comments(main_content)
        flattened_content = self._process_includes(main_content, main_file)

        if output_file:
            output_path = Path(output_file)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(flattened_content, encoding='utf-8')
            print(f"Flattened LaTeX saved to: {output_file}")

            # Also produce Markdown normalization to paper.md via pandoc
            md_path = output_path.parent / "paper.md"
            if pypandoc is not None:
                try:
                    md_text = pypandoc.convert_text(
                        flattened_content,
                        to="md",
                        format="latex",
                    )
                    md_path.write_text(md_text, encoding="utf-8")
                    print(f"Markdown saved to: {md_path}")
                except Exception as pandoc_exc:
                    print(f"[warn] Failed to generate Markdown via pandoc: {pandoc_exc}")
            else:
                print("[warn] pypandoc not available; skipping paper.md generation")

            # Optionally extract abstract text for later root summary
            abstract_text = self._extract_abstract(flattened_content)
            if abstract_text:
                abstract_path = output_path.parent / "abstract.txt"
                try:
                    abstract_path.write_text(abstract_text.strip() + "\n", encoding="utf-8")
                    print(f"Abstract saved to: {abstract_path}")
                except Exception as abstract_exc:
                    print(f"[warn] Failed to write abstract.txt: {abstract_exc}")

        return flattened_content

    def _extract_abstract(self, flattened_content: str) -> str | None:
        """Extract abstract text from flattened LaTeX content if present.

        Tries standard environments and common section headings.
        """
        # 1) \begin{abstract} ... \end{abstract}
        env_match = re.search(r"\\begin\{abstract\}([\s\S]*?)\\end\{abstract\}", flattened_content, re.IGNORECASE)
        if env_match:
            return env_match.group(1).strip()

        # 2) \section*{Abstract} ... until next section
        sec_star = re.search(
            r"\\section\*\{\s*Abstract\s*\}([\s\S]*?)(?=\\section|\\subsection|\\begin\{|$)",
            flattened_content,
            re.IGNORECASE,
        )
        if sec_star:
            return sec_star.group(1).strip()

        # 3) \section{Abstract} ... until next section
        sec = re.search(
            r"\\section\{\s*Abstract\s*\}([\s\S]*?)(?=\\section|\\subsection|\\begin\{|$)",
            flattened_content,
            re.IGNORECASE,
        )
        if sec:
            return sec.group(1).strip()

        return None


def flatten_latex(source_dir: str, output_file: str = None, strip_comments: bool = False) -> str:
    """Convenience function to flatten LaTeX from a directory."""
    flattener = LatexFlattener(source_dir)
    return flattener.flatten(output_file, strip_comments=strip_comments)
