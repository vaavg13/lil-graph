from typing import Dict, List, Any, Optional
import os
from pathlib import Path

from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

from src.indexing.models import PaperNode, NodeType

class GraphVerifier:
    def __init__(self, model_name: str = "gpt-5.1"):
        self.llm = ChatOpenAI(model=model_name, temperature=0.0)

    def verify(self, nodes: Dict[str, PaperNode], source_dir: str) -> List[str]:
        """
        Verifies the consistency of the constructed graph against the raw LaTeX source.
        Returns a list of warning messages.
        """
        print(f"Verifying graph with {len(nodes)} nodes against source in {source_dir}...")
        
        # 1. Gather LaTeX Source
        latex_content = self._read_latex_source(source_dir)
        if not latex_content:
            return ["Warning: No LaTeX source content found to verify against."]

        # 2. Serialize Graph
        graph_summary = self._serialize_graph(nodes)

        # 3. Prompt LLM
        warnings = self._check_consistency(latex_content, graph_summary)
        
        return warnings

    def _read_latex_source(self, source_dir: str) -> str:
        """
        Reads and concatenates all .tex files from the source directory.
        """
        content_parts = []
        source_path = Path(source_dir)
        
        # Find all tex files recursively
        tex_files = sorted(source_path.rglob("*.tex"))
        
        for tex_file in tex_files:
            try:
                # Add file header to help LLM distinguish files
                rel_path = tex_file.relative_to(source_path)
                content_parts.append(f"--- START FILE: {rel_path} ---")
                content_parts.append(tex_file.read_text(encoding="utf-8", errors="replace"))
                content_parts.append(f"--- END FILE: {rel_path} ---\n")
            except Exception as e:
                print(f"Warning: Could not read {tex_file}: {e}")
        
        return "\n".join(content_parts)

    def _serialize_graph(self, nodes: Dict[str, PaperNode]) -> str:
        """
        Creates a text representation of the graph structure.
        """
        # Find root
        root = None
        for node in nodes.values():
            if node.node_type == NodeType.ROOT:
                root = node
                break
        
        if not root:
            return "Error: No ROOT node found in graph."

        lines = []
        self._traverse_node(root, nodes, lines, depth=0)
        return "\n".join(lines)

    def _traverse_node(self, node: PaperNode, all_nodes: Dict[str, PaperNode], lines: List[str], depth: int):
        indent = "  " * depth
        
        # Format based on type
        info = f"{node.node_type.value}: {node.id}"
        
        if node.node_type == NodeType.ROOT:
            info += f" Title='{getattr(node, 'title', '')}'"
            if getattr(node, 'abstract', None):
                 info += f"\n{indent}  Abstract: {node.abstract[:100]}..."
        
        elif node.node_type == NodeType.SECTION:
            info += f" Title='{getattr(node, 'title', '')}' Level={getattr(node, 'level', 1)}"
            
        elif node.node_type == NodeType.TEXT_CHUNK:
            text = getattr(node, 'text', '')
            preview = text[:50].replace('\n', ' ')
            info += f" Text='{preview}...' ({len(text)} chars)"
            
        elif node.node_type == NodeType.FIGURE:
             info += f" Asset='{getattr(node, 'asset_path', '')}' Caption='{getattr(node, 'caption', '')}'"
             
        elif node.node_type == NodeType.TABLE:
             info += f" Caption='{getattr(node, 'caption', '')}'"

        elif node.node_type == NodeType.CITATION:
             extracted = getattr(node, 'extracted_data', {})
             key = extracted.get('citation_key', '??')
             info += f" Key='{key}'"

        lines.append(f"{indent}- {info}")

        # Recurse children
        for child_id in node.children_ids:
            child = all_nodes.get(child_id)
            if child:
                self._traverse_node(child, all_nodes, lines, depth + 1)
            else:
                lines.append(f"{indent}  - [Missing Child Node: {child_id}]")

    def _check_consistency(self, latex_content: str, graph_summary: str) -> List[str]:
        """
        Uses LLM to check if the graph summary matches the latex content.
        """
        
        # Truncate content if too large (naive protection, though models have large context now)
        # GPT-4o has 128k context, so we should be okay for most papers. 
        # But let's be safe-ish.
        if len(latex_content) > 300000:
            latex_content = latex_content[:300000] + "\n...[TRUNCATED]..."

        if len(graph_summary) > 100000:
             graph_summary = graph_summary[:100000] + "\n...[TRUNCATED]..."

        prompt = ChatPromptTemplate.from_template("""
You are a QA system for a scientific paper parser. 
Your goal is to verify that a Knowledge Graph (constructed from the paper) accurately represents the content of the raw LaTeX source code.

Raw LaTeX Source (possibly truncated):
========================================
{latex_content}
========================================

Constructed Knowledge Graph Structure:
========================================
{graph_summary}
========================================

Task:
1. Verify if all major sections from the LaTeX source appear in the graph with correct hierarchy.
2. Check if the abstract is captured.
3. Check if Figures and Tables are reasonably captured (mentions of them).
4. Identify any hallucinations (sections in graph that don't exist in text) or major omissions.

Return a list of warnings. If everything looks good, return "No issues found." or an empty list.
Format your response as a bulleted list of issues. Be concise.
""")
        
        chain = prompt | self.llm | StrOutputParser()
        
        try:
            result = chain.invoke({
                "latex_content": latex_content,
                "graph_summary": graph_summary
            })
            
            # Parse result into list
            lines = result.strip().split('\n')
            warnings = [line.strip('- ').strip() for line in lines if line.strip() and "No issues found" not in line]
            return warnings
            
        except Exception as e:
            return [f"LLM Verification failed: {str(e)}"]

