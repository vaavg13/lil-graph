import os
from dataclasses import dataclass


@dataclass(frozen=True)
class PipelineSettings:
    """
    Centralized pipeline configuration. Reads environment variables once so
    orchestrators and adapters do not scatter os.getenv calls.
    """

    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "password"
    crossref_email: str = "your_email@example.com"
    crossref_delay: float = 0.2
    crossref_timeout: int = 10
    ingestion_backend: str = "arxiv"
    parser_backend: str = "latexml"
    resolution_backend: str = "crossref"

    @classmethod
    def from_env(cls) -> "PipelineSettings":
        def _float_env(name: str, default: float) -> float:
            try:
                return float(os.getenv(name, default))
            except Exception:
                return default

        def _int_env(name: str, default: int) -> int:
            try:
                return int(os.getenv(name, default))
            except Exception:
                return default

        return cls(
            neo4j_uri=os.getenv("NEO4J_URI", cls.neo4j_uri),
            neo4j_user=os.getenv("NEO4J_USER", cls.neo4j_user),
            neo4j_password=os.getenv("NEO4J_PASSWORD", cls.neo4j_password),
            crossref_email=os.getenv("CROSSREF_EMAIL", cls.crossref_email),
            crossref_delay=_float_env("CROSSREF_DELAY", cls.crossref_delay),
            crossref_timeout=_int_env("CROSSREF_TIMEOUT", cls.crossref_timeout),
            ingestion_backend=os.getenv("INGESTION_BACKEND", cls.ingestion_backend),
            parser_backend=os.getenv("PARSER_BACKEND", cls.parser_backend),
            resolution_backend=os.getenv("RESOLUTION_BACKEND", cls.resolution_backend),
        )
