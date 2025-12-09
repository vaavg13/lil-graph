import json
import os
from typing import Dict
from pydantic import TypeAdapter

from .models import GraphNode


def write_tree_json(paper_dir: str, nodes: Dict[str, GraphNode]) -> str:
    index_dir = os.path.join(paper_dir, "index")
    os.makedirs(index_dir, exist_ok=True)
    tree_path = os.path.join(index_dir, "tree.json")
    with open(tree_path, "w", encoding="utf-8") as f:
        # Pydantic models with inheritance are serialized same way
        json.dump({k: v.model_dump() for k, v in nodes.items()}, f, ensure_ascii=False, indent=2)
    return tree_path


def read_tree_json(paper_dir: str) -> Dict[str, GraphNode]:
    tree_path = os.path.join(paper_dir, "index", "tree.json")
    if not os.path.exists(tree_path):
        raise FileNotFoundError(tree_path)
    with open(tree_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    # Use TypeAdapter to handle polymorphic deserialization
    adapter = TypeAdapter(Dict[str, GraphNode])
    return adapter.validate_python(data)
