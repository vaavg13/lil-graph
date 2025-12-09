from typing import Dict, Any, List, Optional

from ..adapters.factories import get_parser_port
from .types import PipelineError, LogEntry
from ..config.settings import PipelineSettings


def run_parsing(
    source_dir: str,
    paper_dir: str,
    parser_type: str,
    logs: List[LogEntry],
    settings: Optional[PipelineSettings] = None,
) -> Dict[str, Any]:
    """
    Select the parser backend and execute it, recording progress into logs.
    """
    try:
        cfg = settings or PipelineSettings.from_env()
        backend = parser_type or cfg.parser_backend
        parser_port = get_parser_port(
            PipelineSettings(
                parser_backend=backend,
                neo4j_uri=cfg.neo4j_uri,
                neo4j_user=cfg.neo4j_user,
                neo4j_password=cfg.neo4j_password,
                crossref_email=cfg.crossref_email,
                crossref_delay=cfg.crossref_delay,
                crossref_timeout=cfg.crossref_timeout,
                ingestion_backend=cfg.ingestion_backend,
                resolution_backend=cfg.resolution_backend,
            )
        )
        logs.append(("info", f"Using parser backend={backend}"))
        parsed_data = parser_port.run(source_dir, paper_dir, logs)
        sections = parsed_data.get("sections", []) if isinstance(parsed_data, dict) else []
        chunk_count = sum(len(sec.get("chunks", [])) for sec in sections if isinstance(sec, dict))
        logs.append(
            ("ok", f"Parsing pipeline completed successfully (sections={len(sections)}, chunks={chunk_count})")
        )

        if not sections or chunk_count == 0:
            logs.append(("error", "Parsing produced no sections/chunks; aborting build"))
            raise PipelineError("Parsing produced no usable content", logs)

        return parsed_data
    except Exception as exc:
        logs.append(("error", f"Parsing pipeline failed: {exc}"))
        raise PipelineError(f"Parsing failed: {exc}", logs)
