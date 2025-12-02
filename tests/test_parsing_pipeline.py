import sys
import tempfile
from pathlib import Path
from unittest import TestCase

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from src.parsing.pipeline import extract_bibliography_from_latex  # noqa: E402


class ExtractBibliographyTests(TestCase):
    def test_extracts_bibitems_from_latex(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tex_path = Path(tmpdir) / "paper.tex"
            tex_path.write_text(
                r"""
\begin{document}
\begin{thebibliography}{99}
\bibitem{Smith2017a} John Smith and Jane Doe. Awesome Paper. 2017.
\bibitem{Lee2019} Alice Lee. Follow-up. 2019.
\end{thebibliography}
\end{document}
""",
                encoding="utf-8",
            )

            entries = extract_bibliography_from_latex(Path(tmpdir))

            self.assertEqual(set(entries.keys()), {"Smith2017a", "Lee2019"})
            self.assertIn("John Smith", entries["Smith2017a"]["text"])
            self.assertIn("Alice Lee", entries["Lee2019"]["text"])

