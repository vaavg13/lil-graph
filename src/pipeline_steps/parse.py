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
        logs.append(("ok", "Parsing pipeline completed successfully"))
        return parsed_data
    except Exception as exc:
        logs.append(("error", f"Parsing pipeline failed: {exc}"))
        raise PipelineError(f"Parsing failed: {exc}", logs)

