import os
import sys
from typing import Iterable, List, Tuple

BASE_DIR = "/home/avgerinos/Projects/engine_v2"
SRC_DIR = os.path.join(BASE_DIR, "src")
OUT_DIR = BASE_DIR
IDENTIFIER =   "1706.03762"#"1806.03762"#"1706.03762" # or "1806.03762"
STRIP_COMMENTS = True
KEEP_EXTRACTED = True

if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from src.pipeline import PipelineError, run_pipeline
from src.visualization import (
    print_ascii_tree,
    render_hierarchical_tree,
    render_nodes_graph,
    render_tree_image,
)


LogEntry = Tuple[str, str]


def main() -> int:
    try:
        result = run_pipeline(
            identifier=IDENTIFIER,
            base_dir=BASE_DIR,
            strip_comments=STRIP_COMMENTS,
            keep_extracted=KEEP_EXTRACTED,
            out_dir=OUT_DIR,
        )
    except PipelineError as exc:
        _emit_logs(exc.logs)
        print(f"[error] {exc.message}")
        return 1

    _emit_logs(result.logs)

    if result.nodes:
        print("\n[tree]\n")
        try:
            print_ascii_tree(result.nodes)
        except Exception as exc:  # pragma: no cover - best effort
            print(f"[warn] ASCII visualization failed: {exc}")

        try:
            if result.paper_dir:
                ascii_image_path = os.path.join(result.paper_dir, "index", "tree_ascii.png")
                render_tree_image(result.nodes, ascii_image_path)
                print(f"[ok] Tree ASCII image -> {ascii_image_path}")
        except Exception as exc:  # pragma: no cover - best effort
            print(f"[warn] Tree ASCII image failed: {exc}")

        try:
            if result.paper_dir:
                graph_path = os.path.join(result.paper_dir, "index", "tree_nodes.json")
                render_nodes_graph(result.nodes, graph_path)
                print(f"[ok] Tree nodes data -> {graph_path}")
        except Exception as exc:  # pragma: no cover - best effort
            print(f"[warn] Tree nodes graph failed: {exc}")

        try:
            if result.paper_dir:
                radial_path = os.path.join(result.paper_dir, "index", "tree.png")
                render_hierarchical_tree(result.nodes, radial_path)
                print(f"[ok] Tree graph -> {radial_path}")
        except Exception as exc:  # pragma: no cover - best effort
            print(f"[warn] Tree graph failed: {exc}")

    return 0


def _emit_logs(logs: List[LogEntry]) -> None:
    for level, message in logs:
        print(f"[{level}] {message}")


if __name__ == "__main__":
    sys.exit(main())