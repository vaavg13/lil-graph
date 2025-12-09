import sys
from pathlib import Path
from unittest import TestCase

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from src.application.build_graph import build_nodes_from_parsed_data  # noqa: E402
from src.domain.nodes import ChunkNode, CitationNode  # noqa: E402


class BuildNodesTests(TestCase):
    def test_merge_section_chunks_combines_chunks(self) -> None:
        parsed_data = {
            "abstract": "Abstract text",
            "sections": [
                {
                    "title": "Intro",
                    "level": 1,
                    "chunks": [
                        {
                            "chunk_id": "chunk_0",
                            "text": "First part.",
                            "citations": ["refA"],
                            "references": []
                        },
                        {
                            "chunk_id": "chunk_1",
                            "text": "Second part.",
                            "citations": ["refB"],
                            "references": []
                        },
                    ],
                }
            ],
            "bibliography": {
                "refA": {"key": "refA"},
                "refB": {"key": "refB"},
            },
        }

        nodes = build_nodes_from_parsed_data(
            arxiv_id="paper",
            parsed_data=parsed_data,
            paper_title="Paper",
            merge_section_chunks=True,
        )

        chunk_nodes = [node for node in nodes.values() if isinstance(node, ChunkNode)]
        self.assertEqual(len(chunk_nodes), 1)
        self.assertIn("First part.", chunk_nodes[0].text)
        self.assertIn("Second part.", chunk_nodes[0].text)

        citation_nodes = [
            node for node in nodes.values() if isinstance(node, CitationNode)
        ]
        self.assertEqual(len(citation_nodes), 2)
        keys = {node.extracted_data.get("citation_key") for node in citation_nodes}
        self.assertEqual(keys, {"refA", "refB"})

