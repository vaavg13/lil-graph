# Critical Architecture Report: The "Hybrid Fidelity" Pipeline

**Date:** Dec 1, 2025
**Status:** Pivot to "Robust, CPU-Efficient Science Engine"

## 1. The Core Problem: The "One-Size-Fits-None" Trap
The current backend relies purely on Regex parsing of LaTeX source. This is fragile because LaTeX is a programming language, not a data format. Conversely, "All-in-One" AI solutions (VLMs) are too expensive and slow for scaling to 2M+ papers.

## 2. The Solution: The "Hybrid Fidelity" Pipeline
To achieve **High Fidelity** (Math, Tables, Citations) with **Low Cost** (CPU-only), we must decompose the problem. We will use three specialized, industry-standard tools, each doing what it does best.

### Component A: Structure & Citations (GROBID)
*   **Role**: Extracts the "Skeleton" of the paper.
*   **Input**: PDF.
*   **Output**: TEI XML.
*   **Why**:
    *   **Robustness**: Semantic Scholar and ResearchGate use this. It doesn't break on bad LaTeX.
    *   **Citations**: Returns fully structured citations (`<biblStruct>`), solving our "Citation Resolution" problem out of the box.
    *   **Speed**: ~10 papers/second on CPU.

### Component B: Visual Assets (pdffigures2)
*   **Role**: Extracts Figures and Tables as **Images**.
*   **Input**: PDF.
*   **Output**: Individual PNG files + JSON mapping (Captions, Page Coordinates).
*   **Why**:
    *   **Accuracy**: Analyzes the PDF's internal object stream to find "Vector/Image" regions.
    *   **Context**: Links the image to its caption and mention in the text.
    *   **Agent-Ready**: Provides the actual image file for an Agent to "see" (Visual QA).

### Component C: Symbolic Math (LaTeX Injection)
*   **Role**: Preserves Equations as high-fidelity Code.
*   **Input**: LaTeX Source Tarball.
*   **Output**: LaTeX strings.
*   **Why**:
    *   GROBID/OCR destroys math.
    *   **Strategy**: We scan the source for `\begin{equation}` environments and inject the raw LaTeX into the corresponding text chunks from GROBID.
    *   **Benefit**: The Agent gets the *exact* formula to reason with, not a hallucinated OCR version.

## 3. The New Data Flow
1.  **Ingest**: Download PDF + Source.
2.  **Parallel Process**:
    *   Run `pdffigures2` -> Save Images.
    *   Run `GROBID` -> Get XML.
3.  **Merge (The "Zipper")**:
    *   Create `PaperNode` tree from GROBID XML.
    *   Attach `pdffigures2` images to `FIGURE` nodes based on caption matching.
    *   Inject LaTeX Math into `TEXT_CHUNK` nodes.
4.  **Graph Persist**: Push the rich tree to Neo4j.

## 4. Immediate Roadmap
1.  **Infrastructure**:
    *   Add `grobid/grobid` to Docker stack.
    *   Install `pdffigures2` (Scala/Java binary).
2.  **Refactor Ingestion**:
    *   Create `src/parsing/grobid_client.py`.
    *   Create `src/parsing/visual_extractor.py`.
3.  **Graph Schema Update**:
    *   Ensure `FIGURE` nodes point to local PNG paths.
    *   Ensure `CITATION` edges are created from GROBID's resolved metadata.

## 5. Decision
This architecture provides **Scale** (CPU/Lightweight), **Robustness** (Standard Tools), and **Fidelity** (Visuals + Math). It avoids the fragility of regex-only parsing and the cost of VLM-only parsing.
