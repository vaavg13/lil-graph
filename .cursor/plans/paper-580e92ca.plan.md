<!-- 580e92ca-ad9b-4e54-ad67-09898c70ed0b 99d13863-b281-45cb-a670-2e8605f74f66 -->
# Paper Tree Indexing — Refactor-First Plan (no wrappers, modify existing code)

### Scope

- Restructure `src` to support a two-stage system: (1) ingestion/normalization and (2) indexing (tree + summaries + embeddings).
- Modify existing modules directly (move + edit); only create new files where functionality is missing.
- Use OpenAI gpt-5 for text summaries, OpenAI multimodal for figures/tables, and FAISS with `BAAI/bge-m3` embeddings via LangChain.

### Source tree refactor (moves + edits)

- Move and edit:
- `src/arxiv_fetcher.py` → `src/ingestion/arxiv.py`
- Keep: `resolve_arxiv_id`, `download_pdf`, `download_source_tarball_if_available`.
- `src/latex_flattener.py` → `src/parsing/latex_flattener.py`
- Edit: after flattening to `flattened.tex`, also produce `paper.md` via `pypandoc` when requested.
- Edit: optionally extract abstract text for later root summary.
- `src/assets_preparer.py` → `src/parsing/assets_preparer.py`
- Edit: rewrite links in `paper.md` and `flattened.tex` (remove references to `flattened.md`).
- Keep: copying assets from `source_extracted/` to `assets/`, `keep_extracted` flag.
- `src/cli.py` (stay in place)
- Edit: switch to subcommands and rewire imports to new module paths.

### New modules (only what’s missing)

- `src/parsing/structure_extractor.py`
- Parse `paper.md` into hierarchy from headings (#, ##, ###, …).
- Split paragraphs into `TEXT_CHUNK`s using a simple length-based splitter.
- `src/parsing/figtable_mapper.py`
- From `flattened.tex`, collect figure/table labels and map to actual files under `assets/`.
- Detect mentions inside chunks via regex (e.g., `\\ref{fig:*}`, `Figure\s+\d+`, `Table\s+\d+`).
- `src/indexing/models.py`
- `NodeType` enum: `ROOT`, `SECTION`, `SUBSECTION`, `TEXT_CHUNK`, `FIGURE`, `TABLE`.
- `PaperNode` (Pydantic): `id`, `paper_id`, `type`, `title?`, `level?`, `text?`, `asset_path?`, `children_ids`, `parent_id?`, `summary?`, `embedding?`, `metadata?`.
- `src/indexing/tree_builder.py`
- Build the `PaperNode` tree from structure + fig/table mapping; root summary initialized from abstract text.
- `src/indexing/persist.py`
- Read/write `PAPER/<id>/index/tree.json`.
- `src/summarization/text_summarizer.py`
- LangChain `ChatOpenAI(model="gpt-5")` summarizing non-text nodes from concatenated children text.
- `src/summarization/vision_summarizer.py`
- OpenAI multimodal (default `gpt-4o-mini`, configurable) to summarize figure/table images.
- `src/embeddings/faiss_index.py`
- `HuggingFaceBgeEmbeddings("BAAI/bge-m3", normalize_embeddings=True)` + `FAISS` store; persist under `PAPER/<id>/index/faiss/`.
- `src/retrieval/query.py`
- Minimal retrieval API with optional filters by `paper_id` and `type`.
- `src/config.py`
- Central config for paths, model names, and `OPENAI_API_KEY` (simple constants/env reads; no extra helpers).

### Paper directory persistence

- `PAPER/<arxiv_id>/`
- `paper.pdf`, `source.tar`, `source_extracted/`, `flattened.tex`, `assets/`, `paper.md`
- `index/tree.json`, `index/faiss/`

### Pipelines

- Ingestion/Normalization (refactor existing code)

1. Resolve/download with `ingestion/arxiv.py`.
2. Extract source; `parsing/latex_flattener.py` → `flattened.tex` (strip-comments optional) and `paper.md` via `pypandoc`.
3. `parsing/assets_preparer.py` copies assets and rewrites links in `paper.md` and `flattened.tex`.

- Structure → Tree (new code)

1. `structure_extractor.py`: headings → sections/subsections; paragraphs → `TEXT_CHUNK`s.
2. `figtable_mapper.py`: labels + mentions → attach `FIGURE`/`TABLE` nodes under the referencing chunk.
3. `tree_builder.py`: produce full tree; set root summary from abstract if available.
4. `persist.py`: write `tree.json`.

- Summaries (new code)
- Root: summary = abstract (no LLM).
- Non-text nodes: summarize children text with `ChatOpenAI(model="gpt-5")`.
- Figures/Tables: multimodal summary on image assets.

- Embeddings + FAISS (new code)
- Compute node embeddings with `BAAI/bge-m3` via LangChain; add metadata (`node_id`, `paper_id`, `type`, `title`, `path`).
- Persist FAISS index per paper under `index/faiss/`.

### CLI (edit in place)

- Subcommands:
- `ingest <identifier> [--flatten --strip-comments --prepare-assets --keep-extracted]`
- `normalize <arxiv_id>` → ensure `paper.md` exists
- `build-index <arxiv_id>` → structure + tree + persist
- `summarize <arxiv_id>` → generate summaries
- `embed <arxiv_id>` → compute embeddings and update FAISS
- `process-all <identifier>` → end-to-end pipeline

### LangChain specifics

- Text LLM: `langchain_openai.ChatOpenAI(model="gpt-5")`.
- Vision: OpenAI multimodal (configurable, default `gpt-4o-mini`).
- Embeddings: `langchain_community.embeddings.HuggingFaceBgeEmbeddings`.
- Vector store: `langchain_community.vectorstores.FAISS`.

### Requirements

- Extend `requirements.txt` with: `pydantic`, `markdown-it-py`, `langchain`, `langchain-openai`, `langchain-community`, `faiss-cpu`, `sentence-transformers`.

### Validation (against attached `PAPER/` samples)

- Run end-to-end on: `1706.03762`, `1709.01507`, `1810.04805`, `1907.10597`.
- Check: `paper.md` quality, `assets/` correctness, `tree.json` shape with figure/table attachments, FAISS index sizes; run a few retrieval queries.

### To-dos

- [x] Create packages and move existing ingestion/parsing modules
- [x] Implement LaTeX→Markdown normalization to produce paper.md
- [x] Parse markdown headings/paragraphs into sections and text chunks
- [x] Map figures/tables and detect mentions in chunks
- [x] Build PaperNode tree and persist to tree.json
- [ ] Implement hierarchical text and vision summaries
- [ ] Compute embeddings for nodes and persist FAISS index
- [ ] Extend CLI with ingest/build-index/summarize/embed
- [ ] Run pipeline on sample PAPER entries and verify outputs
- [ ] 