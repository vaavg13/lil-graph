import os
import re
import shutil
from pathlib import Path


def _rewrite_links_in_file(file_path: Path, prefixes: set[str]) -> None:
    if not file_path.exists():
        return

    try:
        content = file_path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return

    updated = content
    # For each discovered top-level prefix (e.g., Figures, vis, images), rewrite to assets/<prefix>/
    for prefix in prefixes:
        patterns = [
            ("](" + prefix + "/", "](" + "assets/" + prefix + "/"),  # markdown link
            ("src=\"" + prefix + "/", "src=\"assets/" + prefix + "/"),  # html-like src
            ("{" + prefix + "/", "{" + "assets/" + prefix + "/"),  # LaTeX braces
            (") {" + prefix + "/", ") {assets/" + prefix + "/"),  # rare md+tex hybrid
            ("] (" + prefix + "/", "] (assets/" + prefix + "/"),  # spaced markdown
            ("source_extracted/" + prefix + "/", "assets/" + prefix + "/"),
        ]
        for old, new in patterns:
            updated = updated.replace(old, new)

    if updated != content:
        file_path.write_text(updated, encoding="utf-8")


def prepare_assets(paper_dir: str, keep_extracted: bool = False) -> None:
    """
    Prepare portable assets for a paper directory.

    - Creates paper_dir/assets/{Figures,vis}
    - Copies from paper_dir/source_extracted/{Figures,vis} if present
    - Rewrites links in flattened.md and flattened.tex to point to assets/
    - Deletes paper_dir/source_extracted after processing (unless keep_extracted=True)
    - Keeps existing source tarball (e.g., source.tar) and other outputs
    """
    base = Path(paper_dir)
    if not base.exists():
        raise FileNotFoundError(f"Paper directory not found: {paper_dir}")

    source_dir = base / "source_extracted"
    assets_dir = base / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)

    flattened_tex = base / "flattened.tex"
    referenced_paths: list[str] = []
    top_level_prefixes: set[str] = set()

    if flattened_tex.exists():
        try:
            tex_content = flattened_tex.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            tex_content = ""

        # Extract paths from \includegraphics[...] {path} allowing whitespace/newlines before the brace
        for match in re.finditer(r"\\includegraphics(?:\[[^\]]*\])?\s*\{([^}]+)\}", tex_content):
            path_str = match.group(1).strip()
            if path_str:
                referenced_paths.append(path_str)
                # collect top-level prefix (segment before first /)
                prefix = path_str.split("/", 1)[0]
                if prefix:
                    top_level_prefixes.add(prefix)

    # If no prefixes discovered, fall back to common ones
    if not top_level_prefixes:
        for fallback in ("Figures", "vis", "images", "figures"):
            if (source_dir / fallback).exists():
                top_level_prefixes.add(fallback)

    # Also scan paper.md for markdown/HTML image references to catch base-level assets
    paper_md_path = base / "paper.md"
    if paper_md_path.exists():
        try:
            md_content = paper_md_path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            md_content = ""
        for m in re.finditer(r"!\[[^\]]*\]\(([^\)]+)\)", md_content):
            p = m.group(1).strip()
            if p and p not in referenced_paths:
                referenced_paths.append(p)
                prefix = p.split("/", 1)[0]
                if prefix:
                    top_level_prefixes.add(prefix)
        for m in re.finditer(r"src=\"([^\"]+)\"", md_content):
            p = m.group(1).strip()
            if p and p not in referenced_paths:
                referenced_paths.append(p)
                prefix = p.split("/", 1)[0]
                if prefix:
                    top_level_prefixes.add(prefix)

    # Copy all referenced assets from source_extracted to assets/, resolving extensions if omitted
    candidate_exts = ["", ".pdf", ".png", ".jpg", ".jpeg", ".eps"]
    for rel_path in referenced_paths:
        rel_no_ext = rel_path
        ext = Path(rel_path).suffix
        if ext:
            candidate_list = [rel_path]
        else:
            candidate_list = [rel_no_ext + e for e in candidate_exts[1:]]

        found_src: Path | None = None
        found_name: str | None = None
        for candidate in candidate_list:
            src_candidate = source_dir / candidate
            if src_candidate.exists():
                found_src = src_candidate
                found_name = Path(candidate).name
                break

        # If still not found, try original rel_path as-is
        if found_src is None:
            src_candidate = source_dir / rel_path
            if src_candidate.exists():
                found_src = src_candidate
                found_name = Path(rel_path).name

        if found_src is None:
            continue

        # Destination mirrors the same relative directories under assets/
        subdir = Path(rel_path).parent
        dst_dir = assets_dir / subdir
        dst_dir.mkdir(parents=True, exist_ok=True)
        dst_file = dst_dir / (found_name or Path(rel_path).name)
        shutil.copy2(found_src, dst_file)

    # Rewrite links in outputs based on discovered prefixes
    _rewrite_links_in_file(base / "paper.md", top_level_prefixes)
    _rewrite_links_in_file(base / "flattened.tex", top_level_prefixes)

    # Rewrite direct base-level filenames (e.g., Fig1.eps) to assets/Fig1.eps in outputs
    base_level_files = {Path(p).name for p in referenced_paths if "/" not in p}
    if base_level_files:
        for target in (base / "paper.md", base / "flattened.tex"):
            if not target.exists():
                continue
            try:
                content = target.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            updated = content
            for name in base_level_files:
                updated = updated.replace("](" + name, "](assets/" + name)
                updated = updated.replace("src=\"" + name, "src=\"assets/" + name)
                updated = updated.replace("{" + name + "}", "{assets/" + name + "}")
            if updated != content:
                target.write_text(updated, encoding="utf-8")

    # Remove the extracted source directory unless requested to keep it
    if source_dir.exists() and not keep_extracted:
        shutil.rmtree(source_dir)


