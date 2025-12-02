import json
import math
import os
from typing import Any, Dict, Tuple

from PIL import Image, ImageDraw, ImageFont  # type: ignore

try:  # pragma: no cover - optional dependency
    import matplotlib.pyplot as plt  # type: ignore
    import networkx as nx  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    plt = None  # type: ignore
    nx = None  # type: ignore

from src.indexing.models import NodeType


def print_ascii_tree(nodes: Dict[str, Any]) -> None:
    root_id = _find_root(nodes)
    if root_id is None:
        print("(no root)")
        return

    def label_for(node) -> str:
        node_type = getattr(node, "node_type", getattr(node, "type", ""))
        if node_type == NodeType.SECTION:
            title = getattr(node, "title", "") or "(untitled)"
            return f"{node_type}: {title}"
        if node_type == NodeType.TEXT_CHUNK:
            text = (getattr(node, "text", "") or "").replace("\n", " ")
            preview = text[:80]
            suffix = "..." if len(text) > 80 else ""
            return f"{node_type}: {preview}{suffix}"
        if node_type in [NodeType.FIGURE, NodeType.TABLE]:
            path = getattr(node, "asset_path", "") or "(asset)"
            return f"{node_type}: {os.path.basename(path)}"
        if node_type == NodeType.CITATION:
            title = getattr(node, "title", "") or "(citation)"
            return f"{node_type}: {title}"
        return f"{node_type}"

    def dfs(node_id: str, depth: int) -> None:
        node = nodes[node_id]
        print("  " * depth + "- " + label_for(node))
        for child_id in getattr(node, "children_ids", []) or []:
            dfs(child_id, depth + 1)

    dfs(root_id, 0)


def render_tree_image(nodes: Dict[str, Any], out_path: str) -> None:
    root_id = _find_root(nodes)
    if root_id is None:
        raise ValueError("No root node found in tree")

    lines = []

    def label_for(node) -> str:
        node_type = getattr(node, "node_type", getattr(node, "type", ""))
        if node_type == NodeType.SECTION:
            title = getattr(node, "title", "") or "(untitled)"
            return f"{node_type}: {title}"
        if node_type == NodeType.TEXT_CHUNK:
            text = (getattr(node, "text", "") or "").replace("\n", " ")
            if len(text) > 80:
                text = text[:77] + "..."
            return f"{node_type}: {text}"
        if node_type in [NodeType.FIGURE, NodeType.TABLE]:
            path = getattr(node, "asset_path", "") or "(asset)"
            return f"{node_type}: {os.path.basename(path)}"
        if node_type == NodeType.CITATION:
            title = getattr(node, "title", "") or "(citation)"
            return f"{node_type}: {title}"
        return f"{node_type}"

    def dfs(node_id: str, depth: int) -> None:
        node = nodes[node_id]
        lines.append((depth, label_for(node)))
        for child_id in getattr(node, "children_ids", []) or []:
            dfs(child_id, depth + 1)

    dfs(root_id, 0)

    font = ImageFont.load_default()
    margin_x = 16
    margin_y = 12
    indent_px = 24
    line_spacing = 4

    tmp = Image.new("RGB", (1, 1), color=(255, 255, 255))
    draw = ImageDraw.Draw(tmp)
    max_w = 0
    total_h = margin_y
    sizes = []
    for depth, text in lines:
        bbox = draw.textbbox((0, 0), text, font=font)
        width = bbox[2] - bbox[0]
        height = bbox[3] - bbox[1]
        sizes.append((width, height))
        max_w = max(max_w, margin_x + depth * indent_px + width)
        total_h += height + line_spacing
    total_h += margin_y

    image_width = max(320, max_w + margin_x)
    image_height = max(200, total_h)
    image = Image.new("RGB", (image_width, image_height), color=(255, 255, 255))
    draw = ImageDraw.Draw(image)
    y = margin_y
    for (depth, text), (width, height) in zip(lines, sizes):
        x = margin_x + depth * indent_px
        draw.text((x, y), text, fill=(0, 0, 0), font=font)
        y += height + line_spacing

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    image.save(out_path)


def build_cytoscape_data(nodes: Dict[str, Any]) -> Dict[str, Any]:
    if nx is None:
        raise RuntimeError("networkx not available")

    def _node_attr(node: Any, name: str, default: Any = None) -> Any:
        if hasattr(node, name):
            return getattr(node, name)
        if isinstance(node, dict):
            return node.get(name, default)
        return default

    root_id = _find_root(nodes)
    if root_id is None:
        raise ValueError("No root node found in tree")

    graph = nx.DiGraph()
    for node_id, node in nodes.items():
        graph.add_node(node_id)
        for child_id in _node_attr(node, "children_ids", []) or []:
            if child_id in nodes:
                graph.add_edge(node_id, child_id)

    positions = _radial_layout(graph, root_id)
    if root_id not in positions:
        positions[root_id] = (0.0, 0.0)

    scaled_positions = {
        node_id: (coords[0] * 140.0, coords[1] * 140.0)
        for node_id, coords in positions.items()
    }

    color_map = {
        NodeType.ROOT: "#4a5568",
        NodeType.SECTION: "#3b82f6",
        NodeType.TEXT_CHUNK: "#10b981",
        NodeType.FIGURE: "#f59e0b",
        NodeType.TABLE: "#8b5cf6",
        NodeType.CITATION: "#f97316",
        NodeType.ALGORITHM: "#ef4444",
        NodeType.EQUATION: "#6366f1",
        NodeType.PROOF: "#14b8a6",
    }

    elements = []
    for node_id, node in nodes.items():
        node_type = _node_attr(node, "node_type", _node_attr(node, "type", ""))
        if isinstance(node_type, str):
            try:
                node_type = NodeType(node_type)
            except ValueError:
                node_type = NodeType.SECTION if node_id == root_id else NodeType.TEXT_CHUNK

        if node_type == NodeType.SECTION:
            label = _node_attr(node, "title", "") or "(untitled)"
        elif node_type == NodeType.TEXT_CHUNK:
            text = (_node_attr(node, "text", "") or "").replace("\n", " ")
            label = text[:80] + ("..." if len(text) > 80 else "")
        elif node_type in (NodeType.FIGURE, NodeType.TABLE):
            path = _node_attr(node, "asset_path", "") or "(asset)"
            label = os.path.basename(path)
        elif node_type == NodeType.CITATION:
            label = _node_attr(node, "title", "") or "CITATION"
        else:
            label = str(node_type)

        x, y = scaled_positions.get(node_id, (0.0, 0.0))
        node_data = {
            "id": node_id,
            "label": label,
            "type": node_type.value,
        }

        paper_ref = _node_attr(node, "paper_id")
        if paper_ref is not None:
            node_data["paper_id"] = paper_ref

        title_value = _node_attr(node, "title")
        if title_value:
            node_data["title"] = title_value

        text_value = _node_attr(node, "text")
        if text_value:
            node_data["text"] = text_value

        asset_path = _node_attr(node, "asset_path")
        if asset_path:
            node_data["asset_path"] = asset_path
            node_data["asset_name"] = os.path.basename(asset_path)

        level_value = _node_attr(node, "level")
        if level_value is not None:
            node_data["level"] = level_value

        parent_value = _node_attr(node, "parent_id")
        if parent_value is not None:
            node_data["parent_id"] = parent_value

        children_value = list(_node_attr(node, "children_ids", []) or [])
        node_data["children_ids"] = children_value

        summary_value = _node_attr(node, "summary")
        if summary_value:
            node_data["summary"] = summary_value

        metadata_value = _node_attr(node, "metadata")
        if metadata_value:
            node_data["metadata"] = metadata_value

        elements.append(
            {
                "data": node_data,
                "position": {"x": x, "y": y},
                "classes": node_type.value.lower(),
            }
        )

    for source_id, node in nodes.items():
        for target_id in _node_attr(node, "children_ids", []) or []:
            if target_id in nodes:
                elements.append(
                    {
                        "data": {
                            "id": f"{source_id}__{target_id}",
                            "source": source_id,
                            "target": target_id,
                        },
                        "classes": "edge",
                    }
                )

    stylesheet = [
        {
            "selector": "node",
            "style": {
                "content": "data(label)",
                "font-size": "12px",
                "text-wrap": "wrap",
                "text-max-width": "160px",
                "background-color": "#9ca3af",
                "color": "#111827",
                "border-width": 1,
                "border-color": "#1f2937",
            },
        },
        {
            "selector": ".edge",
            "style": {
                "curve-style": "bezier",
                "target-arrow-shape": "triangle",
                "width": 1,
                "line-color": "#9ca3af",
                "target-arrow-color": "#9ca3af",
            },
        },
    ]

    for node_type, color in color_map.items():
        stylesheet.append(
            {
                "selector": f".{node_type.value.lower()}",
                "style": {"background-color": color},
            }
        )

    paper_id = None
    if root_id in nodes:
        paper_id = _node_attr(nodes[root_id], "paper_id")

    return {
        "elements": elements,
        "stylesheet": stylesheet,
        "layout": {"name": "preset", "padding": 50},
        "metadata": {"root_id": root_id, "paper_id": paper_id},
    }


def render_nodes_graph(nodes: Dict[str, Any], out_path: str) -> None:
    payload = build_cytoscape_data(nodes)

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2)


def render_hierarchical_tree(nodes: Dict[str, Any], out_path: str) -> None:
    if nx is None or plt is None:
        raise RuntimeError("networkx/matplotlib not available")

    root_id = _find_root(nodes)
    if root_id is None:
        raise ValueError("No root node found in tree")

    graph = nx.DiGraph()
    for node_id, node in nodes.items():
        graph.add_node(node_id)
        for child_id in getattr(node, "children_ids", []) or []:
            graph.add_edge(node_id, child_id)

    position = _radial_layout(graph, root_id)

    def label_for(node) -> str:
        node_type = getattr(node, "type", "")
        if node_type == NodeType.SECTION:
            title = getattr(node, "title", "") or "(untitled)"
            return title
        if node_type == NodeType.TEXT_CHUNK:
            return "TEXT_CHUNK"
        if node_type in [NodeType.FIGURE, NodeType.TABLE]:
            path = getattr(node, "asset_path", "") or "(asset)"
            return os.path.basename(path)
        if node_type == NodeType.CITATION:
            title = getattr(node, "title", "") or "CITATION"
            return title if len(title) <= 50 else title[:47] + "..."
        return str(node_type)

    labels = {}
    for node_id, node in nodes.items():
        node_type = getattr(node, "node_type", getattr(node, "type", ""))
        if node_type == NodeType.TEXT_CHUNK:
            continue
        label = label_for(node)
        if label:
            labels[node_id] = label if len(label) <= 32 else label[:29] + "..."

    node_order = list(graph.nodes())
    colors = []
    for node_id in node_order:
        node = nodes.get(node_id)
        node_type = getattr(node, "node_type", getattr(node, "type", ""))
        if node_type == NodeType.SECTION:
            colors.append("#b5d0ff")
        elif node_type == NodeType.TEXT_CHUNK:
            colors.append("#c6f6d5")
        elif node_type == NodeType.FIGURE:
            colors.append("#ffd699")
        elif node_type == NodeType.TABLE:
            colors.append("#d9b3ff")
        elif node_type == NodeType.CITATION:
            colors.append("#ffd6d6")
        else:
            colors.append("#dddddd")

    size = max(40, min(80, int(len(nodes) ** 0.6) + 30))
    plt.figure(figsize=(size, size))
    nx.draw_networkx_edges(
        graph,
        position,
        arrows=False,
        width=1.2,
        edge_color="#888888",
        alpha=0.6,
    )
    nx.draw_networkx_nodes(
        graph,
        position,
        node_size=300,
        node_color=colors,
        linewidths=0.5,
        edgecolors="#333333",
    )
    if labels:
        nx.draw_networkx_labels(graph, position, labels=labels, font_size=7)
    plt.axis("off")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    plt.tight_layout()
    plt.savefig(out_path, dpi=200)
    plt.close()


def _find_root(nodes: Dict[str, Any]) -> str:
    for node_id, node in nodes.items():
        if getattr(node, "node_type", getattr(node, "type", None)) == NodeType.ROOT:
            return node_id
    for node_id, node in nodes.items():
        if getattr(node, "parent_id", None) is None:
            return node_id
    return None  # type: ignore[return-value]


def _radial_layout(graph, root):
    positions: Dict[Any, Tuple[float, float]] = {}

    def count_descendants(node):
        children = list(graph.successors(node))
        if not children:
            return 1
        return 1 + sum(count_descendants(child) for child in children)

    descendant_counts = {node: count_descendants(node) for node in graph.nodes()}

    positions[root] = (0.0, 0.0)

    def position_subtree(node, level, angle_start, angle_end):
        children = list(graph.successors(node))
        if not children:
            return

        radius = level * 5.0
        angle_range = angle_end - angle_start
        total_descendants = sum(descendant_counts[child] for child in children)

        current_angle = angle_start
        for child in children:
            child_weight = descendant_counts[child] / total_descendants
            child_angle_range = angle_range * child_weight
            child_angle_end = current_angle + child_angle_range
            child_angle = (current_angle + child_angle_end) / 2.0

            x = radius * math.cos(child_angle)
            y = radius * math.sin(child_angle)
            positions[child] = (x, y)

            position_subtree(child, level + 1, current_angle, child_angle_end)
            current_angle = child_angle_end

    position_subtree(root, 1, 0, 2 * math.pi)
    return positions

