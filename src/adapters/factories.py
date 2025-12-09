from ..config.settings import PipelineSettings
from ..ports.ingestion import IngestionPort
from ..ports.parsers import ParserPort
from ..ports.resolution import ResolutionPort
from .ingestion.arxiv_ingestion import ArxivIngestion
from .resolvers.crossref_resolver import CrossRefResolutionAdapter
from .parsers import LaTeXMLParser, PandocParser


class LaTeXMLParserPort(ParserPort):
    def run(self, source_dir: str, paper_dir: str, logs):
        parser = LaTeXMLParser(source_dir, paper_dir)
        return parser.run()


class PandocParserPort(ParserPort):
    def run(self, source_dir: str, paper_dir: str, logs):
        parser = PandocParser(source_dir, paper_dir)
        return parser.run()


def get_ingestion_port(settings: PipelineSettings) -> IngestionPort:
    backend = settings.ingestion_backend
    if backend == "arxiv":
        return ArxivIngestion()
    raise ValueError(f"Unsupported ingestion backend: {backend}")


def get_resolution_port(settings: PipelineSettings) -> ResolutionPort:
    backend = settings.resolution_backend
    if backend == "crossref":
        return CrossRefResolutionAdapter(
            email=settings.crossref_email,
            delay=settings.crossref_delay,
            timeout=settings.crossref_timeout,
        )
    raise ValueError(f"Unsupported resolution backend: {backend}")


def get_parser_port(settings: PipelineSettings) -> ParserPort:
    backend = settings.parser_backend
    if backend == "latexml":
        return LaTeXMLParserPort()
    if backend == "pandoc":
        return PandocParserPort()
    raise ValueError(f"Unsupported parser backend: {backend}")
