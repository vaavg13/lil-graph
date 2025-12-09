import sys
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from src.domain.nodes import CitationNode  # noqa: E402
from src.adapters.resolvers.crossref_resolver import CrossRefResolver  # noqa: E402


class CrossRefResolverTests(TestCase):
    def test_resolve_citations_processes_citation_nodes(self) -> None:
        citation_node = CitationNode(
            id="paper::CHUNK::0::CITE::ref",
            paper_id="paper",
            parent_id="paper::CHUNK::0",
            extracted_data={"text": "Example reference"},
        )
        nodes = {
            citation_node.id: citation_node,
        }

        resolver = CrossRefResolver()

        with patch.object(CrossRefResolver, "_resolve_single_node", autospec=True) as mock_resolve:
            resolver.resolve_citations(nodes)

        mock_resolve.assert_called_once_with(resolver, citation_node)

    def test_resolve_citations_dedupes_reference_keys(self) -> None:
        node_a = CitationNode(
            id="paper::CHUNK::0::CITE::ref",
            paper_id="paper",
            parent_id="paper::CHUNK::0",
            extracted_data={"text": "Example reference", "key": "ref", "citation_key": "ref"},
        )
        node_b = CitationNode(
            id="paper::CHUNK::1::CITE::ref",
            paper_id="paper",
            parent_id="paper::CHUNK::1",
            extracted_data={"text": "Example reference", "key": "ref", "citation_key": "ref"},
        )
        nodes = {
            node_a.id: node_a,
            node_b.id: node_b,
        }

        resolver = CrossRefResolver()

        def fake_resolve(self, node):
            paper = {
                "title": ["Sample"],
                "author": [{"given": "A", "family": "B"}],
            }
            CrossRefResolver._update_node_with_paper_data(self, node, paper)
            return paper

        with patch.object(CrossRefResolver, "_resolve_single_node", autospec=True, side_effect=fake_resolve) as mock_resolve:
            resolver.resolve_citations(nodes)

        self.assertEqual(mock_resolve.call_count, 1)
        self.assertEqual(node_a.title, node_b.title)

