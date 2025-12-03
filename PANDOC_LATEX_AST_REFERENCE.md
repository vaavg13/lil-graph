# Pandoc LaTeX → AST Conversion Reference

**Document Purpose:** Reference guide for understanding how Pandoc converts LaTeX documents to JSON AST, based on real-world debugging of academic paper processing.

**Document Version:** 1.0  
**Date:** December 3, 2025  
**Pandoc Version:** 3.x (API version [1, 23, 1])

---

## Table of Contents

1. [Overview](#overview)
2. [Document Structure](#document-structure)
3. [Sections and Headers](#sections-and-headers)
4. [Text Content](#text-content)
5. [Figures](#figures)
6. [Tables](#tables)
7. [Citations](#citations)
8. [References and Labels](#references-and-labels)
9. [Unknown/Raw LaTeX](#unknownraw-latex)
10. [Common Gotchas](#common-gotchas)
11. [Processing Strategy](#processing-strategy)

---

## Overview

### What Pandoc Does

Pandoc converts LaTeX source into a hierarchical JSON AST (Abstract Syntax Tree). The conversion is **lossy** - some LaTeX-specific formatting is lost, but the semantic structure is preserved.

### AST Structure

```json
{
  "pandoc-api-version": [1, 23, 1],
  "meta": { /* document metadata */ },
  "blocks": [ /* array of Block elements */ ]
}
```

**Key Concepts:**
- **Blocks**: Paragraph-level elements (Para, Header, Table, Div, etc.)
- **Inlines**: Inline elements within blocks (Str, Space, Link, Cite, etc.)
- **Attributes**: `[id, classes, key-value pairs]` format

---

## Document Structure

### Top-Level Organization

```
Document
└─ blocks[]
   ├─ Header (sections)
   ├─ Para (text paragraphs)
   ├─ Div (wrappers for complex elements)
   ├─ Figure (images with captions)
   ├─ Table (tables)
   └─ RawBlock (unconverted LaTeX)
```

### Block vs Inline

- **Block elements**: Start on new line, contain other blocks or inlines
  - Examples: Para, Header, Table, Div, Figure
- **Inline elements**: Within text flow
  - Examples: Str, Space, Link, Cite, Image, Math

---

## Sections and Headers

### LaTeX Input

```latex
\section{Introduction}
\subsection{Background}
```

### Pandoc Output

```json
{
  "t": "Header",
  "c": [
    1,                           // level (1 = section, 2 = subsection, etc.)
    ["section-id", [], []],      // attributes [id, classes, keyvals]
    [                            // inlines (title text)
      {"t": "Str", "c": "Introduction"}
    ]
  ]
}
```

### What We Get ✅
- Section level (numeric)
- Section title (as inlines)
- Optional ID if present

### What We Don't Get ❌
- Section numbering (must reconstruct)
- LaTeX-specific formatting commands

### Special Cases

**Abstract Section:**
- May appear in document `meta.abstract` instead of as a Header
- OR as a regular Header with title "Abstract"
- **Strategy**: Check both locations

**Bibliography Section:**
- Often has special processing
- Typically appears as Header with title "References" or "Bibliography"

---

## Text Content

### LaTeX Input

```latex
This is a paragraph with \textbf{bold} and \emph{italic} text.

Another paragraph with a citation~\cite{key2023}.
```

### Pandoc Output

```json
{
  "t": "Para",
  "c": [
    {"t": "Str", "c": "This"},
    {"t": "Space"},
    {"t": "Str", "c": "is"},
    // ... more inlines ...
    {"t": "Strong", "c": [{"t": "Str", "c": "bold"}]},
    // ... etc
  ]
}
```

### Inline Elements Reference

| LaTeX | Pandoc Type | Notes |
|-------|-------------|-------|
| Plain text | `Str` | Split at spaces |
| Space | `Space` | Explicit space |
| `\\` (newline) | `LineBreak` | Hard line break |
| `\textbf{}` | `Strong` | Bold text |
| `\emph{}` / `\textit{}` | `Emph` | Italic text |
| `\cite{}` | `Cite` | Citation (see Citations section) |
| `\ref{}` | `Link` | Reference to label |
| `$...$` | `Math` | Inline math |
| `` `code` `` | `Code` | Code snippet |

### What We Get ✅
- Text content
- Basic formatting (bold, italic, etc.)
- Structure (paragraphs separated)

### What We Don't Get ❌
- Font sizes, colors
- Custom LaTeX commands (unless processed)
- Exact spacing/layout

---

## Figures

### Case 1: Standard Figure Environment

**LaTeX Input:**
```latex
\begin{figure}[h]
    \includegraphics[width=0.8\textwidth]{image.pdf}
    \caption{My caption text}
    \label{fig:myimage}
\end{figure}
```

**Pandoc Output:**
```json
{
  "t": "Figure",
  "c": [
    ["fig:myimage", [], []],     // attr: [id, classes, keyvals]
    [                             // caption (blocks)
      {"t": "Plain", "c": [/* caption inlines */]}
    ],
    [                             // content (blocks)
      {
        "t": "Para",
        "c": [
          {
            "t": "Image",
            "c": [
              ["", [], [["width", "80%"]]],  // image attr
              [],                             // alt text
              ["image.pdf", ""]              // [target, title]
            ]
          }
        ]
      }
    ]
  ]
}
```

**Label Location:** ✅ In Figure's `attr[0]` (first element)

---

### Case 2: Wrapfigure Environment

**LaTeX Input:**
```latex
\begin{wrapfigure}{r}{0.5\textwidth}
    \includegraphics[width=0.48\textwidth]{image.pdf}
    \caption{My caption}
    \label{fig:wrapped}
\end{wrapfigure}
```

**Pandoc Output:**
```json
{
  "t": "Div",
  "c": [
    ["", ["wrapfigure"], []],    // attr: id empty, class="wrapfigure"
    [                             // content blocks
      {
        "t": "Para",
        "c": [
          // Positioning info (r, 0.5) as Span elements
          {"t": "Span", "c": [["", [], []], [{"t": "Str", "c": "r"}]]},
          {"t": "SoftBreak"},
          {
            "t": "Image",
            "c": [/* ... */]
          }
        ]
      },
      {
        "t": "Para",
        "c": [
          {
            "t": "Span",
            "c": [
              ["fig:wrapped", [], [["label", "fig:wrapped"]]],  // Label in Span!
              []
            ]
          }
        ]
      }
    ]
  ]
}
```

**Label Location:** ⚠️ In a `Span` element inside the Div's content blocks!

**Key Difference:** Wrapfigure becomes a Div, not a Figure. Label is NOT in Div's ID.

---

### Image Element Structure

```json
{
  "t": "Image",
  "c": [
    ["id", ["class"], [["key", "val"]]],  // attr
    [/* alt text inlines */],              // alt text
    ["path/to/image.pdf", "title"]        // [target, title]
  ]
}
```

**What We Get ✅**
- Image path (relative or absolute)
- Image attributes (width, height if specified)
- Alt text

**What We Don't Get ❌**
- Exact positioning (t, h, b, etc. are hints, not preserved)
- Wrapfigure positioning details

---

## Tables

### LaTeX Input

```latex
\begin{table}[t]
\centering
\begin{tabular}{lcc}
\toprule
Header1 & Header2 & Header3 \\
\midrule
Data1 & Data2 & Data3 \\
\bottomrule
\end{tabular}
\caption{My table caption}
\label{tab:mytable}
\end{table}
```

### Pandoc Output

**Critical Discovery:** Tables are wrapped in Divs!

```json
{
  "t": "Div",
  "c": [
    ["tab:mytable", [], []],     // ⭐ Label is in Div ID!
    [
      {
        "t": "Table",
        "c": [
          ["", [], []],          // Table attr (usually empty)
          [/* caption */],       // Caption blocks
          [/* table structure */]  // Column specs, headers, rows
        ]
      }
    ]
  ]
}
```

**Label Location:** ✅ In parent Div's `attr[0]`, NOT in Table itself!

### Table Structure Details

```json
{
  "t": "Table",
  "c": [
    ["", [], []],              // attr
    [                          // caption (nullable)
      null,                    // short caption
      [/* caption blocks */]   // long caption
    ],
    [/* column specifications */],
    [/* table head */],
    [/* table bodies */],
    [/* table foot */]
  ]
}
```

**What We Get ✅**
- Table content structure
- Caption text
- Basic alignment

**What We Don't Get ❌**
- Custom column widths (partially lost)
- Complex formatting (colors, custom rules)
- Positioning hints (t, b, h)

**Conversion to Markdown:**
- Pandoc can convert table back to markdown
- Use `pandoc_blocks_to_markdown([table_block], api_version)`
- Useful for storage/display

---

## Citations

### LaTeX Input

```latex
Recent work~\cite{author2023,anotherauthor2024} shows...
```

### Pandoc Output

```json
{
  "t": "Para",
  "c": [
    {"t": "Str", "c": "Recent"},
    {"t": "Space"},
    {"t": "Str", "c": "work"},
    {
      "t": "Cite",
      "c": [
        [                           // citation items
          {
            "citationId": "author2023",
            "citationPrefix": [],
            "citationSuffix": [],
            "citationMode": "NormalCitation",
            "citationNoteNum": 0,
            "citationHash": 0
          },
          {
            "citationId": "anotherauthor2024",
            // ... same structure
          }
        ],
        [/* display inlines */]    // How citation appears in text
      ]
    },
    {"t": "Space"},
    {"t": "Str", "c": "shows"},
    // ...
  ]
}
```

### Citation Extraction

**What We Get ✅**
- Citation keys (author2023, etc.)
- Multiple citations in one cite command
- Citation mode (normal, author-only, etc.)

**What We Don't Get ❌**
- Bibliography data (need to parse .bib files separately)
- Formatted citation appearance (need style processing)

**Processing Strategy:**
1. Extract all citation keys from `Cite` elements
2. Parse `.bib` files separately to get metadata
3. Match citation keys to bib entries
4. Resolve full metadata via external API (e.g., CrossRef)

---

## References and Labels

### LaTeX Input

```latex
See Figure~\ref{fig:myplot} for details.
```

### Pandoc Output

```json
{
  "t": "Link",
  "c": [
    ["", [], []],                    // attr
    [                                // link text (inlines)
      {"t": "Str", "c": "Figure"},
      {"t": "Space"},
      {"t": "Str", "c": "??"}       // Actual number unknown
    ],
    ["#fig:myplot", ""]             // ⭐ [url, title] - url is #label
  ]
}
```

**Key Points:**
- References become `Link` elements
- Target URL is `#labelname` (internal link)
- Display text is preserved but number is `??` or placeholder

### Label Storage Patterns

| Element Type | Label Location | Example |
|--------------|----------------|---------|
| `Figure` | `Figure.attr[0]` | `["fig:label", [], []]` |
| `Table` (in Div) | Parent `Div.attr[0]` | `["tab:label", [], []]` |
| Wrapfigure (in Div) | `Span` inside Div | See Figures section |
| Equation | Usually in Span | `["eq:label", [], []]` |

### Forward References Problem

**Issue:** Reference may appear BEFORE definition in document order.

**Example:**
```
Line 10: "See Figure~\ref{fig:foo}"     ← Reference
Line 50: \begin{figure}...\label{fig:foo}  ← Definition
```

**Solution:** Two-pass processing
1. First pass: Build complete asset registry
2. Second pass: Resolve all references

---

## Unknown/Raw LaTeX

### When Pandoc Outputs RawBlock

Pandoc outputs `RawBlock` for LaTeX it cannot convert:

```json
{
  "t": "RawBlock",
  "c": [
    "latex",                     // format
    "\\begin{unknown}...\end{unknown}"  // content
  ]
}
```

**What Triggers RawBlock:**
- Unknown LaTeX environments
- Complex custom commands
- Packages Pandoc doesn't support

**What We Get ✅**
- Original LaTeX source (can extract labels, commands)
- Preserved for later processing

### Processing Raw LaTeX

**Strategy:**
1. Parse the LaTeX string
2. Extract `\label{}` commands
3. Extract `\includegraphics{}` paths
4. Determine if it should become an asset node:
   - Has image + label → Create FigureNode
   - Has only label → Create RawLatexNode
   - No label → Skip or attach to current chunk

**Our Implementation:**
- `RawLatexProcessor` class handles extraction
- Stores metadata: labels, images, captions, env_type
- Flag `should_create_asset` determines handling

---

## Common Gotchas

### 1. Empty Sections

**Problem:** Section with no direct text (only subsections) may be skipped.

```latex
\section{Methods}           ← No text here!
\subsection{Data Collection}  ← First text here
```

**Solution:** Add section even if chunks are empty (except "Body" placeholder).

---

### 2. Labels Not Where Expected

**Problem:** Labels often in wrapper Divs or Spans, not in main element.

**Examples:**
- Table label in parent Div ID, not in Table
- Wrapfigure label in Span inside Div

**Solution:** Search for labels in multiple locations:
1. Element's own attr[0]
2. Parent Div's attr[0]
3. Span elements in content with IDs

---

### 3. Forward References

**Problem:** Reference appears before definition in document.

**Solution:** Post-process references after building complete asset registry.

---

### 4. Citation vs Reference Confusion

**Citations:** `\cite{}` → `Cite` element (to bibliography entries)  
**References:** `\ref{}` → `Link` element with `#label` (to figures/tables/sections)

Don't mix them up in processing!

---

### 5. Multiple Pandoc Conversions

**Problem:** Converting Table block to markdown, then need to convert back.

**Be Careful:**
- Conversion is lossy
- Store original structure if possible
- Use `pandoc_blocks_to_markdown()` utility

---

## Processing Strategy

### Recommended Pipeline

```
1. Parse LaTeX → Pandoc AST
   ↓
2. First Pass: Extract Structure
   - Build asset registry (labels → assets)
   - Extract citations
   - Track chunk IDs
   ↓
3. Process Content
   - Create section hierarchy
   - Extract text chunks
   - Track references (may be unresolved)
   ↓
4. Post-Process
   - Resolve forward references
   - Attach assets to referencing chunks
   - Handle orphaned assets
   ↓
5. Build Node Graph
   - Create hierarchical nodes
   - Link references to assets
   - Attach citations
```

---

### Context Tracking

While processing blocks, track:

```python
class AstProcessor:
    def __init__(self):
        # Current context
        self._current_figure_label = None   # Label from parent Figure/Div
        self._in_abstract = False            # Inside abstract section?
        self._in_bibliography = False        # Inside bibliography?
        
        # Accumulated data
        self.asset_registry = {}            # label → asset info
        self.sections = []                  # Hierarchical sections
        self.citations = set()              # All citation keys
        
        # Chunk tracking
        self._chunk_counter = 0
        self._current_chunk_id = None
```

**Key Pattern:** Parent elements set context for children.

Example:
```python
# When processing Div:
if div_has_label:
    self._current_figure_label = label
    
# When processing Image inside:
if self._current_figure_label:
    # Associate image with label
    self.asset_registry[self._current_figure_label] = {
        "type": "image",
        "path": image_path
    }
```

---

### Label Extraction Pattern

```python
def extract_label(element, content_blocks):
    """Extract label from multiple sources."""
    
    # 1. Check element's attr[0]
    if element_attr and element_attr[0]:
        return element_attr[0]
    
    # 2. Use context from parent (if set)
    if self._current_figure_label:
        return self._current_figure_label
    
    # 3. Search for Span with ID in content
    label = find_label_in_blocks(content_blocks)
    if label:
        return label
    
    return None
```

---

### Reference Resolution Pattern

```python
def resolve_references():
    """After all blocks processed, resolve forward references."""
    
    for section in sections:
        for chunk in section.chunks:
            for ref in chunk.references:
                if ref.type == "unknown":
                    # Try to resolve now
                    if ref.full_label in asset_registry:
                        asset = asset_registry[ref.full_label]
                        ref.type = asset.type
                        ref.asset_path = asset.path
                        
                        # Update text placeholder
                        old = f"{{{{ref:{ref.label}}}}}"
                        if ref.type == "image":
                            new = f"{{{{fig:{ref.label}}}}}"
                        elif ref.type == "table":
                            new = f"{{{{tbl:{ref.label}}}}}"
                        
                        chunk.text = chunk.text.replace(old, new)
```

---

## Quick Reference Tables

### Block Type Summary

| Pandoc Type | LaTeX Source | Contains | Notes |
|-------------|--------------|----------|-------|
| `Header` | `\section{}`, `\subsection{}` | Level, inlines | Hierarchy builder |
| `Para` | Text paragraphs | Inlines | Main content |
| `Figure` | `\begin{figure}` | Caption, images | Label in attr |
| `Table` | `\begin{table}` (in Div) | Rows, columns | Label in parent Div! |
| `Div` | Various wrappers | Other blocks | Check for labels |
| `RawBlock` | Unknown LaTeX | Raw string | Parse manually |

---

### Inline Type Summary

| Pandoc Type | Meaning | Extract |
|-------------|---------|---------|
| `Str` | Text token | Concatenate |
| `Space` | Whitespace | Add space |
| `Cite` | Citation | Extract keys |
| `Link` | Reference/link | Check for #label |
| `Image` | Image | Get path |
| `Math` | Math formula | Get LaTeX |
| `Strong` | Bold | Recurse inlines |
| `Emph` | Italic | Recurse inlines |
| `Span` | Generic wrapper | Check for ID/label |

---

### Label Location Cheat Sheet

```
Figure environment     → Figure.attr[0]
Wrapfigure            → Span inside Div (search needed)
Table environment     → Parent Div.attr[0]  
Equation              → Span.attr[0] or Math.attr[0]
Section               → Header.attr[0]
```

---

## Debugging Tips

### 1. Dump Raw AST

```python
import json
from parsing.utils import get_pandoc_ast

ast = get_pandoc_ast("path/to/main.tex")
print(json.dumps(ast, indent=2))
```

### 2. Search for Specific Content

```python
# Find where specific text appears
for i, block in enumerate(ast['blocks']):
    if 'search_term' in json.dumps(block):
        print(f"Block {i}: {block.get('t')}")
        print(json.dumps(block, indent=2)[:500])
```

### 3. Track Label Locations

```python
def find_all_labels(blocks, path=""):
    """Recursively find all IDs/labels in AST."""
    labels = []
    for i, block in enumerate(blocks):
        if isinstance(block, dict):
            # Check attr
            if 't' in block:
                c = block.get('c', [])
                if isinstance(c, list) and len(c) > 0:
                    if isinstance(c[0], list) and len(c[0]) > 0:
                        if c[0][0]:  # attr[0] = ID
                            labels.append({
                                'label': c[0][0],
                                'type': block['t'],
                                'path': f"{path}.blocks[{i}]"
                            })
            
            # Recurse
            for key, val in block.items():
                if isinstance(val, list):
                    labels.extend(find_all_labels(val, f"{path}.{key}"))
    
    return labels
```

### 4. Verify Asset Registry

After processing, check:
```python
print("Asset Registry:")
for label, info in processor.asset_registry.items():
    print(f"  {label}: {info['type']} - {info.get('path', 'N/A')}")
```

---

## Appendix: Example Conversions

### Complete Figure Example

**Input:**
```latex
\begin{figure}[h]
    \centering
    \includegraphics[width=0.8\textwidth]{results/plot.pdf}
    \caption{Performance over time. The blue line shows accuracy.}
    \label{fig:performance}
\end{figure}

As shown in Figure~\ref{fig:performance}, accuracy improves.
```

**Output (simplified):**
```json
{
  "t": "Figure",
  "c": [
    ["fig:performance", [], []],
    [{"t": "Plain", "c": [/* "Performance over time..." */]}],
    [{
      "t": "Para",
      "c": [{
        "t": "Image",
        "c": [["", [], []], [], ["results/plot.pdf", ""]]
      }]
    }]
  ]
}

// ... later in document ...

{
  "t": "Para",
  "c": [
    {"t": "Str", "c": "As"},
    // ...
    {"t": "Link", "c": [["", [], []], [/* "Figure ??" */], ["#fig:performance", ""]]},
    // ...
  ]
}
```

---

## Version History

- **v1.0** (2025-12-03): Initial version based on real-world debugging
  - Documented Figure, Table, Citation patterns
  - Added wrapfigure and Div wrapping discoveries
  - Included forward reference resolution
  - Added debugging tips

---

## License

This document is released under CC BY 4.0. Free to use and modify with attribution.

---

**End of Reference Document**

