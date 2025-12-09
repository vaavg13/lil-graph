from src.indexing.node_builder import build_nodes_from_parsed_data
from src.indexing.models import NodeType


def test_node_builder_attaches_assets_and_raw_latex():
    parsed = {
        "metadata": {"title": "T"},
        "sections": [
            {
                "title": "Intro",
                "level": 1,
                "chunks": [
                    {
                        "chunk_id": "c1",
                        "text": "hello world",
                        "citations": ["cite1"],
                        "references": [
                            {"type": "figure", "label": "fig-ref", "caption": "Cap"},
                            {"type": "equation", "label": "eq1"},
                        ],
                    }
                ],
            }
        ],
        "bibliography": {"cite1": {"text": "Doe 2020"}},
        "raw_latex_blocks": [
            {
                "chunk_id": "c1",
                "content": "E=mc^2",
                "metadata": {
                    "labels": ["eq1"],
                    "env_type": "equation",
                    "images": [],
                    "should_create_asset": False,
                },
            }
        ],
        "asset_registry": {
            "fig-standalone": {
                "type": "figure",
                "chunk_id": "c1",
                "caption": "Standalone",
                "content": "Standalone figure",
            }
        },
    }

    nodes = build_nodes_from_parsed_data("p", parsed, paper_title="T")

    root_id = "p::ROOT"
    sec_id = "p::SEC::0"
    chunk_id = "p::CHUNK::0"

    assert root_id in nodes
    assert sec_id in nodes[root_id].children_ids
    assert chunk_id in nodes[sec_id].children_ids

    chunk_children = nodes[chunk_id].children_ids
    assert any(cid.endswith("CITE::cite1") for cid in chunk_children)
    assert any(f"{chunk_id}::FIG::fig-ref" == cid for cid in chunk_children)
    assert any(f"{chunk_id}::EQ::eq1" == cid for cid in chunk_children)
    assert any("RAW::" in cid for cid in chunk_children)
    assert any("FIG::fig-standalone" in cid for cid in chunk_children)
