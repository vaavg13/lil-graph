from typing import Any, Dict, List, Protocol

LogEntry = tuple[str, str]


class ParserPort(Protocol):
    """
    Port for parser backends (LaTeXML, Pandoc, OCR, etc.).
    """

    def run(self, source_dir: str, paper_dir: str, logs: List[LogEntry]) -> Dict[str, Any]:
        ...
