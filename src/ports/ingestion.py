from typing import List, Optional, Tuple, Protocol

LogEntry = Tuple[str, str]


class IngestionPort(Protocol):
    """
    Port for fetching and preparing paper source artifacts (PDF, LaTeX tarball).
    """

    def download_and_extract(
        self, arxiv_id: str, base_dir: str, logs: List[LogEntry]
    ) -> Tuple[str, Optional[str], Optional[str], Optional[str], Optional[str]]:
        ...
