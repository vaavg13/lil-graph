#!/usr/bin/env python3

"""Interactive Dash visualization for paper node graphs.

Run with:

    python visualize_paper.py PAPER/1806.03762

This script expects the pipeline to have produced `index/tree.json` inside the
paper directory. If `index/tree_nodes.json` is present (generated via
`render_nodes_graph`), it will be reused; otherwise, the Cytoscape payload is
generated on the fly.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, Dict

try:
    import dash
    from dash import Input, Output, html
    import dash_cytoscape as cyto
except ModuleNotFoundError as exc:  # pragma: no cover - runtime feedback
    raise SystemExit(
        "Dash dependencies missing. Install them with 'pip install dash dash-cytoscape'."
    ) from exc


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.join(BASE_DIR, "src")

if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from src.visualization import build_cytoscape_data  # noqa: E402


def _load_nodes(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as fp:
        data = json.load(fp)
    if not isinstance(data, dict):
        raise ValueError(f"Expected mapping of nodes in {path}")
    return data


def _resolve_payload(paper_dir: str, rebuild: bool) -> Dict[str, Any]:
    index_dir = os.path.join(paper_dir, "index")
    nodes_json_path = os.path.join(index_dir, "tree_nodes.json")
    tree_json_path = os.path.join(index_dir, "tree.json")

    if not os.path.isdir(index_dir):
        raise FileNotFoundError(f"Index directory not found: {index_dir}")

    if not rebuild and os.path.exists(nodes_json_path):
        with open(nodes_json_path, "r", encoding="utf-8") as fp:
            payload = json.load(fp)
        if not isinstance(payload, dict) or "elements" not in payload:
            raise ValueError(f"Invalid Cytoscape payload in {nodes_json_path}")
        return payload

    if not os.path.exists(tree_json_path):
        raise FileNotFoundError(
            "tree.json not found. Run the pipeline first or provide --rebuild after generating nodes."
        )

    nodes = _load_nodes(tree_json_path)
    payload = build_cytoscape_data(nodes)

    with open(nodes_json_path, "w", encoding="utf-8") as fp:
        json.dump(payload, fp, indent=2)

    return payload


def _format_node_details(data: Dict[str, Any]) -> list[Any]:
    if not data:
        return [
            html.H2(
                "Node Details",
                style={"margin": "0 0 12px", "fontSize": "18px", "color": "#0f172a"},
            ),
            html.P("Click a node to see its metadata.", style={"margin": 0, "color": "#475569"}),
        ]

    title = data.get("label") or data.get("title") or data.get("id", "Node")

    lines = []
    lines.append(
        html.H2(
            title,
            style={
                "margin": "0 0 12px",
                "fontSize": "18px",
                "color": "#0f172a",
                "wordBreak": "break-word",
            },
        )
    )

    badge = html.Span(
        data.get("type", "UNKNOWN"),
        style={
            "display": "inline-block",
            "marginBottom": "12px",
            "padding": "2px 8px",
            "borderRadius": "999px",
            "background": "#e2e8f0",
            "color": "#1e293b",
            "fontSize": "12px",
            "fontWeight": 600,
        },
    )
    lines.append(badge)

    fields = [
        ("Node ID", data.get("id")),
        ("Paper ID", data.get("paper_id")),
        ("Title", data.get("title")),
        ("Level", data.get("level")),
        ("Parent", data.get("parent_id")),
        ("Children", ", ".join(data.get("children_ids", []) or [])),
    ]

    if data.get("asset_path"):
        fields.append(("Asset Path", data.get("asset_path")))
    if data.get("asset_name"):
        fields.append(("Asset Name", data.get("asset_name")))

    for key, value in fields:
        if value:
            lines.append(
                html.P(
                    [
                        html.Strong(f"{key}: ", style={"color": "#1e293b"}),
                        html.Span(str(value), style={"color": "#334155"}),
                    ],
                    style={"margin": "0 0 8px", "whiteSpace": "pre-wrap"},
                )
            )

    summary = data.get("summary")
    if summary:
        lines.append(
            html.Div(
                [
                    html.Strong("Summary", style={"display": "block", "marginBottom": "4px"}),
                    html.P(summary, style={"margin": 0, "color": "#475569", "whiteSpace": "pre-wrap"}),
                ],
                style={"margin": "16px 0"},
            )
        )

    text_body = data.get("text")
    if text_body:
        lines.append(
            html.Details(
                children=[
                    html.Summary("Full Text", style={"cursor": "pointer", "color": "#2563eb"}),
                    html.Pre(
                        text_body,
                        style={
                            "margin": "12px 0 0",
                            "whiteSpace": "pre-wrap",
                            "background": "#f8fafc",
                            "padding": "12px",
                            "borderRadius": "6px",
                            "border": "1px solid #e2e8f0",
                            "maxHeight": "300px",
                            "overflow": "auto",
                        },
                    ),
                ],
                style={"margin": "16px 0"},
            )
        )

    metadata = data.get("metadata")
    if isinstance(metadata, dict) and metadata:
        items = []
        for meta_key, meta_value in metadata.items():
            items.append(
                html.Tr(
                    [
                        html.Th(meta_key, style={"textAlign": "left", "padding": "4px 8px", "color": "#475569"}),
                        html.Td(str(meta_value), style={"padding": "4px 8px", "color": "#1e293b"}),
                    ]
                )
            )
        lines.append(
            html.Div(
                [
                    html.Strong("Metadata", style={"display": "block", "marginBottom": "4px"}),
                    html.Table(items, style={"borderCollapse": "collapse", "width": "100%"}),
                ],
                style={"margin": "16px 0"},
            )
        )

    return lines


def _register_callbacks(app: dash.Dash) -> None:
    @app.callback(Output("node-details", "children"), Input("paper-tree", "tapNodeData"))
    def _display_details(node_data: Dict[str, Any] | None) -> list[Any]:
        return _format_node_details(node_data or {})


def _create_app(payload: Dict[str, Any], paper_dir: str) -> dash.Dash:
    metadata = payload.get("metadata") or {}
    paper_id = metadata.get("paper_id") or os.path.basename(os.path.abspath(paper_dir))

    external_stylesheets = [
        {
            "href": "https://fonts.googleapis.com/css2?family=Inter:wght@400;600&display=swap",
            "rel": "stylesheet",
        }
    ]

    app = dash.Dash(__name__, external_stylesheets=external_stylesheets)

    app.layout = html.Div(
        children=[
            html.H1(
                children=f"Paper Graph: {paper_id}",
                style={
                    "margin": "0 0 16px",
                    "fontFamily": "sans-serif",
                    "fontSize": "24px",
                    "color": "#111827",
                },
            ),
            cyto.Cytoscape(
                id="paper-tree",
                elements=payload.get("elements", []),
                stylesheet=payload.get("stylesheet", []),
                layout=payload.get("layout", {"name": "preset"}),
                style={
                    "width": "100%",
                    "height": "85vh",
                    "backgroundColor": "#f8fafc",
                    "border": "1px solid #e5e7eb",
                    "borderRadius": "8px",
                },
                zoomingEnabled=True,
                minZoom=0.1,
                maxZoom=5,
            ),
            html.Div(
                id="node-details",
                style={
                    "marginTop": "24px",
                    "padding": "16px",
                    "background": "white",
                    "borderRadius": "8px",
                    "boxShadow": "0 1px 2px rgba(15, 23, 42, 0.08)",
                    "fontFamily": "Inter, sans-serif",
                },
                children=[
                    html.H2(
                        "Node Details",
                        style={
                            "margin": "0 0 12px",
                            "fontSize": "18px",
                            "color": "#0f172a",
                        },
                    ),
                    html.P(
                        "Click a node to see its metadata.",
                        style={"margin": 0, "color": "#475569"},
                    ),
                ],
            ),
        ],
        style={
            "padding": "24px",
            "height": "100vh",
            "boxSizing": "border-box",
            "background": "#f1f5f9",
        },
    )

    _register_callbacks(app)
    return app


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run Dash visualization for a paper directory")
    parser.add_argument("paper_dir", help="Path to the paper directory produced by the pipeline")
    parser.add_argument("--host", default="127.0.0.1", help="Host interface to bind (default: %(default)s)")
    parser.add_argument("--port", type=int, default=8050, help="Port to bind (default: %(default)s)")
    parser.add_argument(
        "--rebuild",
        action="store_true",
        help="Regenerate Cytoscape data from tree.json even if tree_nodes.json exists",
    )

    args = parser.parse_args(argv)

    paper_dir = os.path.abspath(args.paper_dir)
    if not os.path.isdir(paper_dir):
        parser.error(f"Paper directory does not exist: {paper_dir}")

    payload = _resolve_payload(paper_dir, args.rebuild)
    app = _create_app(payload, paper_dir)

    print(f"[viz] Serving graph for {paper_dir} on http://{args.host}:{args.port}")
    app.run(host=args.host, port=args.port, debug=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

