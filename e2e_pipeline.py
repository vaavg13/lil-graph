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
    
    return 0


def _emit_logs(logs: List[LogEntry]) -> None:
    for level, message in logs:
        print(f"[{level}] {message}")


if __name__ == "__main__":
    sys.exit(main())