import os
import json
import pypandoc
from typing import Dict, List, Optional, Tuple, Set
from pathlib import Path


def parse_bib_file(bib_file: str, cited_keys: Set[str]) -> Dict[str, Dict[str, str]]:
    """
    Parse a .bib file using Pandoc to extract citation metadata.
    Returns a dictionary mapping citation key -> metadata.
    """
    if not os.path.exists(bib_file):
        return {}
        
    try:
        json_str = pypandoc.convert_file(bib_file, to='csljson', format='bibtex')
        entries = json.loads(json_str)
        
        citation_db = {}
        entries_map = {e.get('id', ''): e for e in entries}
        
        for key in cited_keys:
            if key in entries_map:
                entry = entries_map[key]
                authors_list = entry.get('author', [])
                authors_str = ", ".join([f"{a.get('given', '')} {a.get('family', '')}".strip() for a in authors_list])
                
                date_parts = entry.get('issued', {}).get('date-parts', [[None]])
                year = str(date_parts[0][0]) if date_parts and date_parts[0] and date_parts[0][0] else ""
                
                title = entry.get('title', '')
                
                text = f"{authors_str} ({year}). {title}."
                if 'container-title' in entry:
                    text += f" In {entry['container-title']}."
                
                citation_db[key] = {
                    'key': key,
                    'text': text,
                    'authors': authors_str,
                    'year': year,
                    'title': title
                }
            else:
                 citation_db[key] = {
                    'key': key,
                    'text': f'[Citation {key} - entry not found in bib file]',
                    'authors': '',
                    'year': '',
                    'title': '',
                }
        return citation_db
        
    except Exception as e:
        print(f"Error parsing bib file with pandoc: {e}")
        return {}
