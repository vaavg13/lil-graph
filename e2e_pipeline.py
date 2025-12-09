import os
import sys
from typing import Iterable, List, Tuple

BASE_DIR = "/home/avgerinos/Projects/engine_v2"
SRC_DIR = os.path.join(BASE_DIR, "src")
OUT_DIR = BASE_DIR
IDENTIFIER =   "1706.03762"     #"806.03762","1706.03762" # or "1806.03762"
KEEP_EXTRACTED = True
VERIFY_GRAPH = False
VERIFIER_MODEL = "gpt-5.1"
MERGE_SECTION_CHUNKS = True
EXPANSION_DEPTH = 1
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from src.citation_expansion import run_parallel_pipeline

LogEntry = Tuple[str, str]


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser(description="Run the parallel paper processing pipeline.")
    parser.add_argument("identifier", nargs="?", default=IDENTIFIER, help="arXiv ID or title")
    parser.add_argument("--parser", default="latexml", choices=["latexml", "pandoc"], help="Parser type to use")
    parser.add_argument("--level", type=int, default=EXPANSION_DEPTH, help="Citation expansion depth")
    parser.add_argument("--merge-sections", action="store_true", default=MERGE_SECTION_CHUNKS, help="Merge section chunks")
    parser.add_argument("--no-merge-sections", action="store_false", dest="merge_sections", help="Do not merge section chunks")
    
    args = parser.parse_args()

    try:
        run_parallel_pipeline(
            root_identifier=args.identifier,
            base_dir=BASE_DIR,
            max_depth=args.level,
            workers=4,
            keep_extracted=KEEP_EXTRACTED,
            out_dir=OUT_DIR,
            verify_graph=VERIFY_GRAPH,
            verifier_model=VERIFIER_MODEL,
            merge_section_chunks=args.merge_sections,
            parser_type=args.parser, # Passed to pipeline_kwargs
        )
    except Exception as exc:
        print(f"[error] Pipeline failed: {exc}")
        return 1

    return 0


def _emit_logs(logs: List[LogEntry]) -> None:
    for level, message in logs:
        print(f"[{level}] {message}")


if __name__ == "__main__":
    sys.exit(main())