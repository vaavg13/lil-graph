import os
import re
import arxiv
from urllib.error import HTTPError
from typing import Optional, Tuple


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


def download_pdf(arxiv_id: str, output_directory: str) -> Tuple[str, Optional[str], Optional[str], Optional[str]]:
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
    title = entry.title if hasattr(entry, 'title') else None
    
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
 
