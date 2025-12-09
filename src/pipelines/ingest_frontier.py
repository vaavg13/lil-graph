from typing import Iterable, List

from ..application.ingest_paper import run_single_paper
from ..application.types import SinglePaperResult
from ..config.settings import PipelineSettings


def ingest_frontier(
    identifiers: Iterable[str],
    base_dir: str,
    *,
    settings: PipelineSettings | None = None,
    **kwargs,
) -> List[SinglePaperResult]:
    cfg = settings or PipelineSettings.from_env()
    results: List[SinglePaperResult] = []
    for ident in identifiers:
        results.append(run_single_paper(identifier=ident, base_dir=base_dir, settings=cfg, **kwargs))
    return results
