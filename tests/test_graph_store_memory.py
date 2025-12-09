from pathlib import Path
import json

from src.adapters.repositories.memory_store import InMemoryGraphStore
from src.domain.nodes import (
    CitationNode,
    ChunkNode,
    PaperNode,
    SectionNode,
)
from src.application.persist_graph import persist_nodes


def _sample_nodes():
    root = PaperNode(
        id="p::ROOT",
        paper_id="p",
        title="Paper",
        abstract="Abstract",
        children_ids=[],
    )
    sec = SectionNode(
        id="p::SEC::0",
        paper_id="p",
        title="Intro",
        level=1,
        parent_id=root.id,
        children_ids=[],
    )
    root.children_ids.append(sec.id)
    return root, sec, {root.id: root, sec.id: sec}


def test_inmemory_persist_and_query_subgraph():
    store = InMemoryGraphStore()
    root, sec, nodes = _sample_nodes()

    store.persist_nodes(nodes)
    result = store.query_subgraph(root.id, depth=1)

    assert root.id in result["nodes"]
    assert sec.id in result["nodes"]
    assert (root.id, sec.id) in set(result["edges"])


def test_link_citation_replaces_edge():
    store = InMemoryGraphStore()
    chunk = ChunkNode(
        id="p::CHUNK::0",
        paper_id="p",
        text="chunk text",
        parent_id=None,
        children_ids=[],
    )
    cite = CitationNode(
        id="p::CHUNK::0::CITE::c1",
        paper_id="p",
        parent_id=chunk.id,
        extracted_data={},
        children_ids=[],
    )
    chunk.children_ids.append(cite.id)

    store.persist_nodes({chunk.id: chunk, cite.id: cite})
    store.link_citation_to_child_root(cite.id, "child::ROOT")

    assert cite.id not in store.nodes
    assert (chunk.id, cite.id) not in store.edges
    assert (chunk.id, "child::ROOT") in store.edges


def test_persist_nodes_uses_graph_store(tmp_path: Path):
    paper_dir = tmp_path / "paper"
    paper_dir.mkdir()
    root, sec, nodes = _sample_nodes()

    logs = []
    store = InMemoryGraphStore()
    tree_path = persist_nodes(nodes, str(paper_dir), "p", logs, graph_store=store)

    assert tree_path is not None
    assert Path(tree_path).exists()
    with open(tree_path, "r", encoding="utf-8") as f:
        saved = json.load(f)
    assert "p::ROOT" in saved and "p::SEC::0" in saved
    assert store.nodes
    assert any(entry[0] == "ok" for entry in logs)
