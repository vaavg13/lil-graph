import os
import re
import tarfile
from typing import Tuple, Optional, List

import arxiv
from urllib.error import HTTPError

from ...application.types import PipelineError, LogEntry
from ...ports.ingestion import IngestionPort


ARXIV_ABS_URL_PREFIX = "https://arxiv.org/abs/"


_ARXIV_ID_REGEX = re.compile(
    r"^(\d{4}\.\d{4,5})(v\d+)?$|^[a-z\-]+(\.[A-Z]{2})?/\d{7}(v\d+)?$",
    re.IGNORECASE,
)


def _ensure_directory_exists(directory_path: str) -> None:
    if not directory_path:
        return
    os.makedirs(directory_path, exist_ok=True)


def _extract_arxiv_id_from_entry_id(entry_id_url: str) -> str:
    # Example entry_id_url: https://arxiv.org/abs/1706.03762v5
    if not entry_id_url:
        return ""
    if entry_id_url.startswith(ARXIV_ABS_URL_PREFIX):
        return entry_id_url[len(ARXIV_ABS_URL_PREFIX):]
    return entry_id_url.rsplit("/", 1)[-1]


def resolve_arxiv_id(identifier: str) -> str:
    """
    Resolve an identifier (arXiv ID, DOI, or title) to a concrete arXiv ID (possibly with version).

    Requires the 'arxiv' Python package. If unavailable, instructs the user to install it.
    """
    ident = (identifier or "").strip()
    if not ident:
        raise ValueError("Identifier must be a non-empty string")

    if _ARXIV_ID_REGEX.match(ident):
        return ident

    if ident.lower().startswith("10."):
        query = f"doi:{ident}"
    else:
        # Treat as title; quote to bias exact phrase
        query = f"ti:\"{ident}\""

    search = arxiv.Search(query=query, max_results=1, sort_by=arxiv.SortCriterion.Relevance)
    results = list(search.results())
    if not results:
        raise LookupError(f"No arXiv results for query: {query}")
    entry = results[0]
    # arxiv library exposes entry.entry_id like https://arxiv.org/abs/XXXX
    return _extract_arxiv_id_from_entry_id(getattr(entry, "entry_id", ""))


def download_pdf(arxiv_id: str, output_directory: str) -> Tuple[str, str | None, str | None, str]:
    if not arxiv_id:
        raise ValueError("arxiv_id is required")
    _ensure_directory_exists(output_directory)

    # Create a per-paper directory inside a top-level PAPER directory
    paper_base_dir = os.path.join(output_directory, "PAPER")
    _ensure_directory_exists(paper_base_dir)
    paper_dir = os.path.join(paper_base_dir, arxiv_id.replace('/', '_'))
    _ensure_directory_exists(paper_dir)

    search = arxiv.Search(id_list=[arxiv_id], max_results=1)
    results = list(search.results())
    if not results:
        raise LookupError(f"No arXiv entry found for id: {arxiv_id}")

    entry = results[0]
    # Return tuple of (filename, published_date, updated_date, title)
    filename = "paper.pdf"
    entry.download_pdf(dirpath=paper_dir, filename=filename)
    
    pub_date = entry.published.isoformat() if hasattr(entry, 'published') else None
    upd_date = entry.updated.isoformat() if hasattr(entry, 'updated') else None
    title = entry.title if hasattr(entry, 'title') else ""
    
    return os.path.join(paper_dir, filename), pub_date, upd_date, title


def download_source_tarball_if_available(arxiv_id: str, output_directory: str) -> str | None:
    if not arxiv_id:
        raise ValueError("arxiv_id is required")
    _ensure_directory_exists(output_directory)

    # Create a per-paper directory inside a top-level PAPER directory
    paper_base_dir = os.path.join(output_directory, "PAPER")
    _ensure_directory_exists(paper_base_dir)
    paper_dir = os.path.join(paper_base_dir, arxiv_id.replace('/', '_'))
    _ensure_directory_exists(paper_dir)

    search = arxiv.Search(id_list=[arxiv_id], max_results=1)
    results = list(search.results())
    if not results:
        raise LookupError(f"No arXiv entry found for id: {arxiv_id}")

    entry = results[0]
    filename = "source.tar"
    try:
        entry.download_source(dirpath=paper_dir, filename=filename)
        return os.path.join(paper_dir, filename)
    except HTTPError as http_err:
        if http_err.code == 404:
            return None
        raise


def download_content(
    arxiv_id: str,
    out_directory: str,
    logs: List[LogEntry],
) -> Tuple[str, Optional[str], Optional[str], Optional[str], Optional[str]]:
    """
    Download PDF and, when available, the source tarball for an arXiv paper.
    Returns (paper_dir, source_dir, paper_title, published_date, updated_date).
    """
    paper_dir = os.path.join(out_directory, "PAPER", arxiv_id.replace("/", "_"))
    os.makedirs(paper_dir, exist_ok=True)
    
    published_date = None
    updated_date = None
    paper_title = None
    try:
        pdf_path, published_date, updated_date, paper_title = download_pdf(arxiv_id, out_directory)
        logs.append(("ok", f"PDF -> {pdf_path} (Published: {published_date})"))
    except Exception as exc:
        logs.append(("warn", f"PDF download failed: {exc}"))

    source_dir = None
    try:
        src_tar = download_source_tarball_if_available(arxiv_id, out_directory)
        if src_tar:
            source_dir = os.path.join(paper_dir, "source_extracted")
            with tarfile.open(src_tar, "r") as tar:
                tar.extractall(path=source_dir)
            logs.append(("ok", f"Source extracted -> {source_dir}"))
        else:
            logs.append(("info", "No LaTeX source available"))
    except Exception as exc:
        logs.append(("error", f"Source download/extract failed: {exc}"))
        raise PipelineError("Source download/extract failed", logs)

    return paper_dir, source_dir, paper_title, published_date, updated_date


class ArxivIngestion(IngestionPort):
    """
    IngestionPort adapter backed by the arxiv.org API.
    """

    def download_and_extract(
        self, arxiv_id: str, base_dir: str, logs: List[LogEntry]
    ) -> Tuple[str, Optional[str], Optional[str], Optional[str], Optional[str]]:
        return download_content(arxiv_id, base_dir, logs)
