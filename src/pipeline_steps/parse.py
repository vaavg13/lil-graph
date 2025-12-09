from typing import Dict, Any, List
from ..parsing import LaTeXMLParser, PandocParser
from ..pipeline_types import PipelineError, LogEntry

def run_parsing(source_dir: str, paper_dir: str, parser_type: str, logs: List[LogEntry]) -> Dict[str, Any]:
    try:
        if parser_type == "latexml":
            logs.append(("info", "Using LaTeXML parser"))
            parsing_pipeline = LaTeXMLParser(source_dir, paper_dir)
        else:
            logs.append(("info", "Using Pandoc parser"))
            parsing_pipeline = PandocParser(source_dir, paper_dir)
            
        parsed_data = parsing_pipeline.run()
        sections = parsed_data.get("sections", []) if isinstance(parsed_data, dict) else []
        chunk_count = sum(len(sec.get("chunks", [])) for sec in sections if isinstance(sec, dict))
        logs.append(("ok", f"Parsing pipeline completed successfully (sections={len(sections)}, chunks={chunk_count})"))

        if not sections or chunk_count == 0:
            logs.append(("error", "Parsing produced no sections/chunks; aborting build"))
            raise PipelineError("Parsing produced no usable content", logs)

        return parsed_data
    except Exception as exc:
        logs.append(("error", f"Parsing pipeline failed: {exc}"))
        raise PipelineError(f"Parsing failed: {exc}", logs)

