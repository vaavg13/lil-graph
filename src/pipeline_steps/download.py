import os
import tarfile
from typing import Tuple, Optional, List
from ..ingestion.arxiv import download_pdf, download_source_tarball_if_available
from ..pipeline_types import PipelineError, LogEntry

def download_content(arxiv_id: str, out_directory: str, logs: List[LogEntry]) -> Tuple[str, Optional[str], Optional[str], Optional[str], Optional[str]]:
    paper_dir = os.path.join(out_directory, "PAPER", arxiv_id.replace("/", "_"))
    os.makedirs(paper_dir, exist_ok=True)
    
    # PDF
    published_date = None
    updated_date = None
    paper_title = None
    try:
        pdf_path, published_date, updated_date, paper_title = download_pdf(arxiv_id, out_directory)
        logs.append(("ok", f"PDF -> {pdf_path} (Published: {published_date})"))
    except Exception as exc:
        logs.append(("warn", f"PDF download failed: {exc}"))

    # Source
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

