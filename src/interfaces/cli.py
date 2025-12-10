import argparse
from pathlib import Path

from ..application.ingest_paper import run_single_paper
from ..application.expand_citations import run_parallel_pipeline
from ..config.settings import PipelineSettings


def _emit_logs(logs):
    for level, message in logs:
        print(f"[{level}] {message}")


def main() -> int:
    parser = argparse.ArgumentParser(description="LILGraph engine CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    ingest_cmd = sub.add_parser("ingest", help="Ingest a single paper")
    ingest_cmd.add_argument("identifier", help="arXiv ID, DOI, or title")
    ingest_cmd.add_argument("--base-dir", default=".", help="Working directory for artifacts")
    ingest_cmd.add_argument("--parser", default="latexml", choices=["latexml", "pandoc"], help="Parser backend")
    ingest_cmd.add_argument("--keep-extracted", action="store_true", help="Keep extracted sources on disk")
    ingest_cmd.add_argument("--no-merge-section-chunks", action="store_false", dest="merge_section_chunks")
    ingest_cmd.add_argument("--verify-graph", action="store_true", help="Run optional graph verifier when available")
    ingest_cmd.add_argument("--resolve-citations", action="store_true", help="Resolve citations via CrossRef during ingest")

    expand_cmd = sub.add_parser("expand", help="Expand citations breadth-first")
    expand_cmd.add_argument("identifier", help="Root arXiv ID / DOI / title")
    expand_cmd.add_argument("--base-dir", default=".", help="Working directory for artifacts")
    expand_cmd.add_argument("--depth", type=int, default=1, help="Citation expansion depth")
    expand_cmd.add_argument("--workers", type=int, default=4, help="Worker threads for parallel ingest")
    expand_cmd.add_argument("--parser", default=None, choices=["latexml", "pandoc"], help="Override parser backend")
    expand_cmd.add_argument("--keep-extracted", action="store_true", help="Keep extracted sources on disk")
    expand_cmd.add_argument("--no-merge-section-chunks", action="store_false", dest="merge_section_chunks")
    expand_cmd.add_argument("--verify-graph", action="store_true", help="Run optional graph verifier when available")

    flush_cmd = sub.add_parser("flush", help="Flush graph store (neo4j or memory)")
    flush_cmd.add_argument("--target", choices=["neo4j", "memory"], default="neo4j", help="Store to flush")

    args = parser.parse_args()

    cfg = PipelineSettings.from_env()
    if args.command == "ingest":
        result = run_single_paper(
            identifier=args.identifier,
            base_dir=str(Path(args.base_dir).resolve()),
            parser_type=args.parser,
            keep_extracted=args.keep_extracted,
            merge_section_chunks=args.merge_section_chunks,
            verify_graph=args.verify_graph,
            resolve_citations=args.resolve_citations,
            settings=PipelineSettings(
                neo4j_uri=cfg.neo4j_uri,
                neo4j_user=cfg.neo4j_user,
                neo4j_password=cfg.neo4j_password,
                crossref_email=cfg.crossref_email,
                crossref_delay=cfg.crossref_delay,
                crossref_timeout=cfg.crossref_timeout,
                ingestion_backend=cfg.ingestion_backend,
                parser_backend=args.parser or cfg.parser_backend,
                resolution_backend=cfg.resolution_backend,
            ),
        )
        _emit_logs(result.logs)
        print(f"status={result.status} paper_dir={result.paper_dir} tree={result.tree_path}")
        return 0 if result.status == "ok" else 1

    if args.command == "expand":
        run_parallel_pipeline(
            root_identifier=args.identifier,
            base_dir=str(Path(args.base_dir).resolve()),
            max_depth=args.depth,
            workers=args.workers,
            keep_extracted=args.keep_extracted,
            merge_section_chunks=args.merge_section_chunks,
            verify_graph=args.verify_graph,
            parser_type=args.parser,
            settings=cfg,
        )
        return 0

    if args.command == "flush":
        from ..application.flush_graph import flush_default_store

        flush_default_store(target=args.target, settings=cfg)
        print(f"Flushed graph store: {args.target}")
        return 0

    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
