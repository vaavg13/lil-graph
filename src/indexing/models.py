from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field
from pydantic import field_validator, model_validator
from pydantic.config import ConfigDict
import math


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


class PaperNode(BaseModel):
    id: str
    paper_id: str
    node_type: NodeType = Field(alias="type")

    title: Optional[str] = None
    caption: Optional[str] = None
    level: Optional[int] = None
    text: Optional[str] = None
    asset_path: Optional[str] = None

    children_ids: List[str] = Field(default_factory=list)
    parent_id: Optional[str] = None

    summary: Optional[str] = None
    embedding: Optional[List[float]] = None
    metadata: Optional[Dict[str, Any]] = None
    publication_date: Optional[str] = None  # ISO 8601 format
    update_date: Optional[str] = None      # ISO 8601 format

    # Pydantic v2 configuration
    model_config = ConfigDict(
        extra="forbid",
        validate_assignment=True,
        populate_by_name=True,
    )

    @field_validator("children_ids")
    @classmethod
    def _dedupe_children_ids(cls, value: List[str]) -> List[str]:
        # Preserve order, remove duplicates
        seen: set[str] = set()
        deduped: List[str] = []
        for cid in value or []:
            if cid not in seen:
                seen.add(cid)
                deduped.append(cid)
        return deduped

    @field_validator("level")
    @classmethod
    def _validate_level_non_negative(cls, value: Optional[int]) -> Optional[int]:
        if value is None:
            return value
        if value < 0:
            raise ValueError("level must be non-negative")
        return value

    @field_validator("embedding")
    @classmethod
    def _validate_embedding(cls, value: Optional[List[float]]) -> Optional[List[float]]:
        if value is None:
            return value
        if len(value) == 0:
            raise ValueError("embedding, if provided, must be non-empty")
        for x in value:
            if not isinstance(x, (int, float)) or not math.isfinite(float(x)):
                raise ValueError("embedding must contain only finite numbers")
        return [float(x) for x in value]

    @model_validator(mode="after")
    def _validate_relations_and_type_constraints(self) -> "PaperNode":
        # Parent/child self-consistency
        if self.parent_id is not None and self.parent_id == self.id:
            raise ValueError("parent_id cannot equal id")
        if self.id and self.children_ids and self.id in self.children_ids:
            raise ValueError("children_ids cannot include the node's own id")

        # Per-type invariants
        t = self.node_type
        if t == NodeType.ROOT:
            if self.parent_id is not None:
                raise ValueError("ROOT must have parent_id=None")
            if self.text is not None:
                raise ValueError("ROOT must not have text")
            if self.asset_path is not None:
                raise ValueError("ROOT must not have asset_path")
            if self.level is not None and self.level != 0:
                raise ValueError("ROOT level, if set, must be 0")

        elif t == NodeType.SECTION:
            if not self.title or not self.title.strip():
                raise ValueError("SECTION requires non-empty title")
            if self.level is None or self.level < 1:
                raise ValueError("SECTION requires level >= 1")

        elif t == NodeType.TEXT_CHUNK:
            if not self.text or not str(self.text).strip():
                raise ValueError("TEXT_CHUNK requires non-empty text")
            if self.asset_path is not None:
                raise ValueError("TEXT_CHUNK must not have asset_path")
            if self.level is not None:
                raise ValueError("TEXT_CHUNK must not have level")

        elif t == NodeType.FIGURE:
            if not self.asset_path or not str(self.asset_path).strip():
                raise ValueError(f"{t} requires asset_path")
            if self.level is not None:
                raise ValueError(f"{t} must not have level")

        elif t in (NodeType.TABLE, NodeType.ALGORITHM, NodeType.EQUATION, NodeType.PROOF):
            if not self.text or not str(self.text).strip():
                raise ValueError(f"{t} requires non-empty text")
            if self.level is not None:
                raise ValueError(f"{t} must not have level")

        elif t == NodeType.CITATION:
            if not self.text or not str(self.text).strip():
                raise ValueError(f"{t} requires non-empty text")
            if t != NodeType.CITATION and self.asset_path is not None:
                # Non-asset types must not carry an asset path
                raise ValueError(f"{t} must not have asset_path")
            if self.level is not None:
                raise ValueError(f"{t} must not have level")

        return self

