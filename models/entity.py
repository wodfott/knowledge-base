"""Entity and relation models for the knowledge graph."""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field

# 13 entity types from the plan
ENTITY_TYPES = [
    "Person", "Organization", "Technology", "Concept",
    "Tool", "Framework", "Language", "Platform",
    "Event", "Location", "Product", "Methodology", "Other",
]

# 12 relation types from the plan
RELATION_TYPES = [
    "uses", "implements", "depends_on", "part_of",
    "prerequisite_of", "supports", "related_to", "derives_from",
    "applied_to", "builds_on", "conflicts_with", "supersedes",
]


class Entity(BaseModel):
    """A knowledge graph entity extracted from documents."""
    id: str = Field(..., description="Unique entity ID")
    name: str
    type: str  # one of ENTITY_TYPES
    aliases: list[str] = Field(default_factory=list)
    description: Optional[str] = None
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    source_doc_ids: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    last_access: datetime = Field(default_factory=datetime.now)
    metadata: dict = Field(default_factory=dict)


class Relation(BaseModel):
    """A relation (triple) between two entities."""
    id: str = Field(..., description="Unique relation ID")
    source_entity_id: str
    target_entity_id: str
    relation_type: str  # one of RELATION_TYPES
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    source_doc_ids: list[str] = Field(default_factory=list)
    evidence: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.now)
    metadata: dict = Field(default_factory=dict)


class KnowledgeGraph(BaseModel):
    """Container for the full knowledge graph."""
    entities: dict[str, Entity] = Field(default_factory=dict)
    relations: list[Relation] = Field(default_factory=list)
    version: int = 1
    updated_at: datetime = Field(default_factory=datetime.now)
