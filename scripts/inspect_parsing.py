#!/usr/bin/env python3
"""
Utility script that runs the ingestion + parsing portion of the e2e pipeline
and prints a human-friendly summary of what the parser extracted.

Usage:
    python scripts/inspect_parsing.py 2512.02008 --parser latexml
"""

import argparse
import json
import os
import shutil
import sys
import tarfile
from pathlib import Path
from typing import Any, Dict, Tuple

BASE_DIR = Path(__file__).resolve().parents[1]

if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from src.ingestion.arxiv import (  # type: ignore
    download_pdf,
    download_source_tarball_if_available,
    resolve_arxiv_id,
)
from src.parsing import LaTeXMLParser, PandocParser  # type: ignore


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the parsing stage of the pipeline and inspect the output."
    )
    parser.add_argument("identifier", help="arXiv identifier or URL (e.g. 2512.02008)")
    parser.add_argument(
        "--parser",
        choices=["pandoc", "latexml"],
        default="pandoc",
        help="Parsing backend to use",
    )
    parser.add_argument(
        "--base-dir",
        default=str(BASE_DIR),
        help="Workspace base directory (defaults to repo root)",
    )
    parser.add_argument(
        "--keep-extracted",
        action="store_true",
        help="Keep extracted LaTeX sources after script finishes",
    )
    parser.add_argument(
        "--max-sections",
        type=int,
        default=5,
        help="Number of sections to preview in the summary",
    )
    parser.add_argument(
        "--max-chunks",
        type=int,
        default=3,
        help="Number of chunks per section to preview",
    )
    parser.add_argument(
        "--preview-chars",
        type=int,
        default=200,
        help="Number of characters to show for each chunk preview",
    )
    parser.add_argument(
        "--output-json",
        default=None,
        help="Optional path to write the full parsed JSON (defaults to paper_dir/parsed_document.json)",
    )
    return parser.parse_args()


def ensure_source_tree(arxiv_id: str, base_dir: Path, paper_dir: Path) -> Tuple[Path, Path]:
    source_tar = download_source_tarball_if_available(arxiv_id, str(base_dir))
    if not source_tar:
        raise RuntimeError("No LaTeX source tarball available for this paper.")

    source_dir = paper_dir / "source_extracted"
    if source_dir.exists():
        shutil.rmtree(source_dir)

    with tarfile.open(source_tar, "r") as tar:
        tar.extractall(path=source_dir)

    return paper_dir, source_dir


def summarize(parsed: Dict[str, Any], args: argparse.Namespace) -> None:
    metadata = parsed.get("metadata", {})
    print("\n=== PARSING SUMMARY ===")
    print(f"Title: {metadata.get('title') or 'N/A'}")
    abstract = (parsed.get("abstract") or "").strip()
    if abstract:
        print(f"Abstract: {abstract[: args.preview_chars]}{'...' if len(abstract) > args.preview_chars else ''}")

    sections = parsed.get("sections", [])
    print(f"\nSections extracted: {len(sections)}")
    for section in sections[: args.max_sections]:
        title = section.get("title", "Untitled")
        level = section.get("level")
        chunks = section.get("chunks", [])
        print(f"- {title} (level {level}, {len(chunks)} chunks)")
        for chunk in chunks[: args.max_chunks]:
            text = (chunk.get("text") or "").strip().replace("\n", " ")
            preview = text[: args.preview_chars]
            if len(text) > args.preview_chars:
                preview += "..."
            print(f"    • {chunk.get('chunk_id')}: {preview}")
            cites = chunk.get("citations") or []
            refs = chunk.get("references") or []
            if cites:
                print(f"      citations: {', '.join(cites)}")
            if refs:
                ref_labels = [r.get('full_label') or r.get('label') for r in refs]
                print(f"      references: {', '.join(filter(None, ref_labels))}")

    tables = parsed.get("tables", [])
    images = parsed.get("images", [])
    asset_registry = parsed.get("asset_registry", {})
    print(f"\nTables: {len(tables)} | Images: {len(images)} | Assets tracked: {len(asset_registry)}")

    registry_counts: Dict[str, int] = {}
    for asset in asset_registry.values():
        asset_type = asset.get("type", "unknown")
        registry_counts[asset_type] = registry_counts.get(asset_type, 0) + 1
    if registry_counts:
        print("Asset breakdown:", ", ".join(f"{k}: {v}" for k, v in registry_counts.items()))

    out_path = args.output_json
    if out_path:
        out_path = Path(out_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with out_path.open("w", encoding="utf-8") as f:
            json.dump(parsed, f, indent=2, ensure_ascii=False)
        print(f"\nFull parsed JSON written to {out_path}")


def main() -> int:
    args = parse_args()
    base_dir = Path(args.base_dir).resolve()

    try:
        arxiv_id = resolve_arxiv_id(args.identifier)
        print(f"Resolved identifier: {arxiv_id}")
    except Exception as exc:  # pragma: no cover
        print(f"Failed to resolve identifier: {exc}")
        return 1

    paper_dir = base_dir / "PAPER" / arxiv_id.replace("/", "_")
    paper_dir.mkdir(parents=True, exist_ok=True)

    try:
        pdf_path, published_date, updated_date, paper_title = download_pdf(
            arxiv_id, str(base_dir)
        )
        print(f"PDF downloaded to {pdf_path}")
    except Exception as exc:
        print(f"Warning: PDF download failed ({exc})")

    paper_dir, source_dir = ensure_source_tree(arxiv_id, base_dir, paper_dir)

    ParserClass = LaTeXMLParser if args.parser == "latexml" else PandocParser
    parser = ParserClass(str(source_dir), str(paper_dir))

    parsed = parser.run()

    if args.output_json is None:
        args.output_json = str(paper_dir / "parsed_document.json")
    summarize(parsed, args)

    if not args.keep_extracted and source_dir.exists():
        shutil.rmtree(source_dir)

    return 0


if __name__ == "__main__":
    sys.exit(main())


