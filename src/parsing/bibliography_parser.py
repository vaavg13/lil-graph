import os
import re
from typing import Dict, List, Optional, Tuple
import io


def parse_bibliography_entries(bib_text: str) -> List[Dict[str, str]]:
    """
    Parse bibliography text into individual entries.
    
    Returns a list of bibliography entries, where each entry is a dict with:
        - 'text': the full entry text
        - 'authors': extracted author names (if possible)
        - 'year': extracted year (if possible)
        - 'title': extracted title (if possible)
    """
    entries = []
    
    # Split by double newlines (entries are separated by blank lines)
    raw_entries = re.split(r'\n\s*\n', bib_text.strip())
    
    for entry_text in raw_entries:
        entry_text = entry_text.strip()
        if not entry_text or len(entry_text) < 10:
            continue
        
        # Try to extract metadata
        entry = {'text': entry_text}
        
        # Extract year (4-digit number, typically at the end)
        year_match = re.search(r'\b(19|20)\d{2}\b', entry_text)
        if year_match:
            entry['year'] = year_match.group(0)
        
        # Extract authors (names before the first period, typically)
        # Authors usually end with a period followed by the title
        first_sentence = entry_text.split('.', 1)[0] if '.' in entry_text else entry_text
        # Check if this looks like author names (contains "and" or commas)
        if ' and ' in first_sentence or ',' in first_sentence:
            entry['authors'] = first_sentence.strip()
        
        # Try to extract title (text after authors, before year/venue info)
        # This is heuristic and may not work for all formats
        parts = entry_text.split('.', 2)
        if len(parts) >= 2:
            potential_title = parts[1].strip()
            # Remove common prefixes/suffixes
            potential_title = re.sub(r'^(In|Proceedings of|Conference on)\s+', '', potential_title)
            if len(potential_title) > 10 and len(potential_title) < 200:
                entry['title'] = potential_title
        
        entries.append(entry)
    
    return entries


def extract_citation_key_components(cite_key: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Extract author and year from a citation key like 'hochreiter1997' or 'bahdanau2014neural'.
    
    Returns (author_name, year) tuple.
    """
    # Pattern: author name(s) followed by 4-digit year, possibly followed by more text
    match = re.match(r'^([a-z]+)(19|20\d{2})', cite_key, re.IGNORECASE)
    if match:
        author = match.group(1).lower()
        year = match.group(2)
        return author, year
    return None, None


def match_citation_to_entry(cite_key: str, bib_entries: List[Dict[str, str]]) -> Optional[Dict[str, str]]:
    """
    Try to match a citation key to a bibliography entry based on author name and year.
    
    Returns the matched entry dict, or None if no match found.
    """
    author_key, year_key = extract_citation_key_components(cite_key)
    if not author_key or not year_key:
        return None
    
    # Try to find a matching entry
    best_match = None
    best_score = 0
    
    for entry in bib_entries:
        score = 0
        
        # Check year match
        if entry.get('year') == year_key:
            score += 10
        
        # Check author match
        authors_text = entry.get('authors', '').lower()
        if author_key in authors_text:
            score += 5
            # Bonus if it's the first author (appears near the start)
            if authors_text.find(author_key) < 30:
                score += 3
        
        if score > best_score:
            best_score = score
            best_match = entry
    
    # Only return if we have a reasonably confident match
    if best_score >= 10:  # At least year must match
        return best_match
    
    return None


def build_citation_database(bib_text: str, cited_keys: set) -> Dict[str, Dict[str, str]]:
    """
    Build a citation database mapping citation keys to bibliography entries.
    
    Args:
        bib_text: The raw bibliography text
        cited_keys: Set of citation keys found in the document (e.g., 'hochreiter1997')
    
    Returns:
        Dict mapping citation_key -> bibliography entry dict
    """
    bib_entries = parse_bibliography_entries(bib_text)
    citation_db = {}
    
    for cite_key in cited_keys:
        matched_entry = match_citation_to_entry(cite_key, bib_entries)
        if matched_entry:
            citation_db[cite_key] = {
                'key': cite_key,
                'text': matched_entry['text'],
                'authors': matched_entry.get('authors', ''),
                'year': matched_entry.get('year', ''),
                'title': matched_entry.get('title', ''),
            }
        else:
            # Create a placeholder entry for unmatched citations
            citation_db[cite_key] = {
                'key': cite_key,
                'text': f'[Citation {cite_key} - entry not found in bibliography]',
                'authors': '',
                'year': '',
                'title': '',
            }
    
    return citation_db


def parse_latex_bibliography(flattened_tex_path: str) -> Dict[str, str]:
    """
    Extract bibliography entries directly from a flattened LaTeX file.

    Looks for a single thebibliography environment and captures each entry
    starting with \\bibitem{key} (or \\bibitem[...]{key}) until the next
    \\bibitem or the end of the environment.

    Returns mapping: citation_key -> raw_entry_text (LaTeX preserved, minus the \bibitem line)
    """
    if not os.path.exists(flattened_tex_path):
        return {}

    entries_by_key: Dict[str, str] = {}

    begin_re = re.compile(r"^\\begin\{thebibliography\}")
    end_re = re.compile(r"^\\end\{thebibliography\}")
    bibitem_re = re.compile(r"^\\bibitem(?:\[[^\]]*\])?\{([^}]+)\}")

    in_bib = False
    current_key: Optional[str] = None
    current_buf: List[str] = []

    with open(flattened_tex_path, "r", encoding="utf-8") as f:
        for raw_line in f:
            line = raw_line.rstrip("\n")
            if not in_bib:
                if begin_re.match(line.strip()):
                    in_bib = True
                continue

            # Inside thebibliography
            if end_re.match(line.strip()):
                # flush last entry
                if current_key is not None:
                    entries_by_key[current_key] = "\n".join(current_buf).strip()
                break

            m = bibitem_re.match(line.strip())
            if m:
                # flush previous
                if current_key is not None:
                    entries_by_key[current_key] = "\n".join(current_buf).strip()
                # start new
                current_key = m.group(1).strip()
                current_buf = []
                continue

            # accumulate content lines for the current entry
            if current_key is not None:
                current_buf.append(line)

    return entries_by_key


def build_citation_database_from_latex(entries_by_key: Dict[str, str], cited_keys: set) -> Dict[str, Dict[str, str]]:
    """
    Build citation database using entries extracted from LaTeX thebibliography.

    For basic metadata, apply the same lightweight heuristics used in
    parse_bibliography_entries to each entry text.
    """
    citation_db: Dict[str, Dict[str, str]] = {}

    for cite_key in cited_keys:
        entry_text = entries_by_key.get(cite_key)
        if not entry_text:
            citation_db[cite_key] = {
                'key': cite_key,
                'text': f'[Citation {cite_key} - entry not found in bibliography]',
                'authors': '',
                'year': '',
                'title': '',
            }
            continue

        # Heuristic metadata extraction (mirror of parse_bibliography_entries)
        authors = ''
        year = ''
        title = ''

        year_match = re.search(r'\b(19|20)\d{2}\b', entry_text)
        if year_match:
            year = year_match.group(0)

        first_sentence = entry_text.split('.', 1)[0] if '.' in entry_text else entry_text
        if ' and ' in first_sentence or ',' in first_sentence:
            authors = first_sentence.strip()

        parts = entry_text.split('.', 2)
        if len(parts) >= 2:
            potential_title = parts[1].strip()
            potential_title = re.sub(r'^(In|Proceedings of|Conference on)\s+', '', potential_title)
            if len(potential_title) > 10 and len(potential_title) < 200:
                title = potential_title

        citation_db[cite_key] = {
            'key': cite_key,
            'text': entry_text.strip(),
            'authors': authors,
            'year': year,
            'title': title,
        }

    return citation_db

