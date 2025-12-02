from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, Field, field_validator, model_validator, ConfigDict


class NodeType(str, Enum):
    ROOT = "ROOT"
    SECTION = "SECTION"
    TEXT_CHUNK = "TEXT_CHUNK"
    FIGURE = "FIGURE"
    TABLE = "TABLE"
    CITATION = "CITATION"
    ALGORITHM = "ALGORITHM"
    EQUATION = "EQUATION"
    PROOF = "PROOF"


class BasePaperNode(BaseModel):
    id: str
    paper_id: str
    node_type: NodeType = Field(alias="type")
    
    children_ids: List[str] = Field(default_factory=list)
    parent_id: Optional[str] = None
    
    metadata: Optional[Dict[str, Any]] = None
    publication_date: Optional[str] = None
    update_date: Optional[str] = None

    model_config = ConfigDict(
        extra="forbid",
        validate_assignment=True,
        populate_by_name=True,
    )

    @field_validator("children_ids")
    @classmethod
    def _dedupe_children_ids(cls, value: List[str]) -> List[str]:
        seen: set[str] = set()
        deduped: List[str] = []
        for cid in value or []:
            if cid not in seen:
                seen.add(cid)
                deduped.append(cid)
        return deduped

    @model_validator(mode="after")
    def _validate_relations(self) -> "BasePaperNode":
        if self.parent_id is not None and self.parent_id == self.id:
            raise ValueError("parent_id cannot equal id")
        if self.id and self.children_ids and self.id in self.children_ids:
            raise ValueError("children_ids cannot include the node's own id")
        return self


class RootNode(BasePaperNode):
    node_type: Literal[NodeType.ROOT] = Field(NodeType.ROOT, alias="type")
    title: Optional[str] = None # Paper title
    abstract: Optional[str] = None
    
    @model_validator(mode="after")
    def _validate_root(self) -> "RootNode":
        if self.parent_id is not None:
            raise ValueError("ROOT must have parent_id=None")
        return self


class SectionNode(BasePaperNode):
    node_type: Literal[NodeType.SECTION] = Field(NodeType.SECTION, alias="type")
    title: str
    level: int

    @field_validator("title")
    @classmethod
    def _validate_title(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("SECTION requires non-empty title")
        return v

    @field_validator("level")
    @classmethod
    def _validate_level(cls, v: int) -> int:
        if v < 1:
            raise ValueError("SECTION requires level >= 1")
        return v


class ChunkNode(BasePaperNode):
    node_type: Literal[NodeType.TEXT_CHUNK] = Field(NodeType.TEXT_CHUNK, alias="type")
    text: str

    @field_validator("text")
    @classmethod
    def _validate_text(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("TEXT_CHUNK requires non-empty text")
        return v


class FigureNode(BasePaperNode):
    node_type: Literal[NodeType.FIGURE] = Field(NodeType.FIGURE, alias="type")
    asset_path: str
    caption: Optional[str] = None

    @field_validator("asset_path")
    @classmethod
    def _validate_asset_path(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("FIGURE requires asset_path")
        return v


class TableNode(BasePaperNode):
    node_type: Literal[NodeType.TABLE] = Field(NodeType.TABLE, alias="type")
    table_content: str  # Markdown table
    caption: Optional[str] = None

    @field_validator("table_content")
    @classmethod
    def _validate_table_content(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("TABLE requires non-empty table_content")
        return v


class CitationNode(BasePaperNode):
    node_type: Literal[NodeType.CITATION] = Field(NodeType.CITATION, alias="type")
    
    extracted_data: Dict[str, Any] = Field(default_factory=dict) # Dictionary for raw text and hints
    
    # Resolved fields (simple names, initially None)
    doi: Optional[str] = None
    title: Optional[str] = None
    abstract: Optional[str] = None
    url: Optional[str] = None
    authors: List[str] = Field(default_factory=list)
    venue: Optional[str] = None
    year: Optional[int] = None


class AlgorithmNode(BasePaperNode):
    node_type: Literal[NodeType.ALGORITHM] = Field(NodeType.ALGORITHM, alias="type")
    text: str


class EquationNode(BasePaperNode):
    node_type: Literal[NodeType.EQUATION] = Field(NodeType.EQUATION, alias="type")
    text: str


class ProofNode(BasePaperNode):
    node_type: Literal[NodeType.PROOF] = Field(NodeType.PROOF, alias="type")
    text: str


# Union type for usage
PaperNode = Union[
    RootNode,
    SectionNode,
    ChunkNode,
    FigureNode,
    TableNode,
    CitationNode,
    AlgorithmNode,
    EquationNode,
    ProofNode
]
