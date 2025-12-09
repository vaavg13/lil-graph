from ..application.expand_citations import run_parallel_pipeline
from ..config.settings import PipelineSettings


def expand_frontier(
    root_identifier: str,
    base_dir: str,
    *,
    depth: int = 1,
    workers: int = 4,
    settings: PipelineSettings | None = None,
    **kwargs,
):
    cfg = settings or PipelineSettings.from_env()
    return run_parallel_pipeline(
        root_identifier=root_identifier,
        base_dir=base_dir,
        max_depth=depth,
        workers=workers,
        settings=cfg,
        **kwargs,
    )
