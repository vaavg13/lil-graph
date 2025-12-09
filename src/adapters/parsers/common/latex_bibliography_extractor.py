import re
from pathlib import Path
from typing import Dict

BIB_ENV_PATTERN = re.compile(
    r"\\begin\{thebibliography\}.*?\\end\{thebibliography\}",
    re.DOTALL | re.IGNORECASE,
)
BIBITEM_PATTERN = re.compile(
    r"\\bibitem(?:\[[^\]]*\])?\{([^}]+)\}",
    re.IGNORECASE,
)
LATEX_COMMAND_PATTERN = re.compile(
    r"\\[a-zA-Z]+\*?(?:\[[^\]]*\])?(?:\{[^}]*\})?",
    re.MULTILINE,
)

def extract_bibliography_from_latex(
    source_dir: Path,
) -> Dict[str, Dict[str, str]]:
    """
    Extract \\bibitem entries from embedded LaTeX bibliography environments.
    Returns a mapping from citation key -> metadata stub usable downstream.
    """
    entries: Dict[str, Dict[str, str]] = {}

    tex_files = sorted(Path(source_dir).glob("**/*.tex"))
    for tex_file in tex_files:
        try:
            content = tex_file.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue

        for env_match in BIB_ENV_PATTERN.finditer(content):
            env_text = env_match.group(0)
            env_end = env_text.lower().rfind("\\end{thebibliography}")
            body = env_text[:env_end] if env_end != -1 else env_text
            bibitem_matches = list(BIBITEM_PATTERN.finditer(body))

            for idx, bib_match in enumerate(bibitem_matches):
                key = bib_match.group(1).strip()

                entry_start = bib_match.end()
                if idx + 1 < len(bibitem_matches):
                    entry_end = bibitem_matches[idx + 1].start()
                else:
                    entry_end = len(body)

                raw_entry = body[entry_start:entry_end].strip()
                text = _clean_latex_reference_text(raw_entry)

                entries[key] = {
                    "key": key,
                    "text": text or raw_entry,
                    "authors": "",
                    "year": "",
                    "title": "",
                }
            # Do not break; allow later files/environments to add/override entries

    return entries


def _clean_latex_reference_text(raw_text: str) -> str:
    text = re.sub(r"%.*", "", raw_text)
    text = text.replace("\n", " ")
    text = re.sub(r"\\url\{([^}]*)\}", r"\1", text)
    text = LATEX_COMMAND_PATTERN.sub(" ", text)
    text = text.replace("{", "").replace("}", "")
    return " ".join(text.split()).strip()


