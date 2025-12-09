import shutil
import sys
import tempfile
from pathlib import Path
from unittest import TestCase, skipUnless

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from src.parsing.latexml_parser.pipeline import LaTeXMLParser  # noqa: E402


FIXTURE_DIR = PROJECT_ROOT / "tests" / "data" / "latexml_fixture"


@skipUnless(shutil.which("latexml"), "LaTeXML is not installed; skipping integration test.")
class LaTeXMLIntegrationTests(TestCase):
    def test_latexml_pipeline_preserves_key_blocks_and_labels(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)

            parser = LaTeXMLParser(
                source_dir=str(FIXTURE_DIR),
                output_dir=str(output_dir),
            )
            parsed = parser.run()

            # Pipeline should succeed without returning an error key.
            self.assertIsInstance(parsed, dict)
            self.assertNotIn("error", parsed)

            asset_registry = parsed.get("asset_registry", {})
            sections = parsed.get("sections", [])

            # We expect at least one asset of the main structural types to be present.
            types_present = {info.get("type") for info in asset_registry.values()}
            self.assertIn("image", types_present)
            self.assertIn("figure", types_present)
            self.assertIn("table", types_present)
            self.assertIn("equation", types_present)

            # Check that our explicit asset labels survived unchanged.
            for label in ["fig:image-one", "fig:tikz", "fig:algo-block", "tab:one", "eq:one", "thm:main"]:
                self.assertIn(label, asset_registry, msg=f"Missing asset for label {label}")

            image_figure_asset = asset_registry["fig:image-one"]
            # With a real (placeholder) image file present, this should be
            # classified as an image and carry a path.
            self.assertEqual(image_figure_asset["type"], "image")
            self.assertIsInstance(image_figure_asset.get("path"), str)
            self.assertIn("caption", image_figure_asset)

            # TikZ figure: no graphics path, but still a generic figure.
            tikz_figure_asset = asset_registry["fig:tikz"]
            self.assertEqual(tikz_figure_asset["type"], "figure")
            self.assertIsNone(tikz_figure_asset.get("path"))

            algo_figure_asset = asset_registry["fig:algo-block"]
            # This should remain a generic figure, not misclassified as algorithm.
            self.assertEqual(algo_figure_asset["type"], "figure")
            self.assertIsNone(algo_figure_asset.get("path"))

            table_asset = asset_registry["tab:one"]
            self.assertEqual(table_asset["type"], "table")
            self.assertTrue(table_asset.get("content"))

            equation_asset = asset_registry["eq:one"]
            self.assertEqual(equation_asset["type"], "equation")
            self.assertIn("$$", equation_asset.get("content", ""))

            theorem_asset = asset_registry["thm:main"]
            self.assertEqual(theorem_asset["type"], "theorem")
            self.assertIn("Every foo is a bar.", theorem_asset.get("content", ""))

            # Ensure that the introduction text contains raw-label placeholders
            # for the main references, and that references are resolved to assets.
            intro_section = next(
                (
                    s
                    for s in sections
                    if "introduction" in s.get("title", "").lower()
                ),
                None,
            )
            self.assertIsNotNone(intro_section, "Missing Introduction section in parsed output")
            intro_text = " ".join(chunk["text"] for chunk in intro_section.get("chunks", []))

            for label in ["fig:image-one", "tab:one", "eq:one", "thm:main"]:
                self.assertIn(f"{{{{{label}}}}}", intro_text)

            # Collect all references in the introduction and make sure they are typed.
            intro_refs = []
            for chunk in intro_section.get("chunks", []):
                intro_refs.extend(chunk.get("references", []))

            # We expect at least one reference whose label matches each of our main labels.
            labels_in_refs = {r.get("full_label") for r in intro_refs}
            for label in ["fig:image-one", "tab:one", "eq:one", "thm:main"]:
                self.assertIn(label, labels_in_refs)

            # And the reference objects should carry type/path metadata from asset_registry.
            ref_by_label = {r["full_label"]: r for r in intro_refs}
            self.assertEqual(ref_by_label["fig:image-one"]["type"], "image")
            self.assertEqual(ref_by_label["tab:one"]["type"], "table")
            self.assertEqual(ref_by_label["eq:one"]["type"], "equation")
            self.assertEqual(ref_by_label["thm:main"]["type"], "theorem")


