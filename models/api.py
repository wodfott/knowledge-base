"""API request/response models."""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


# --- Collection ---
class CollectRequest(BaseModel):
    url: Optional[str] = None
    rss_feed_url: Optional[str] = None
    text: Optional[str] = None
    title: Optional[str] = None
    source_type: str = "manual"


class CollectResponse(BaseModel):
    status: str
    doc_id: Optional[str] = None
    message: str


# --- Graph ---
class GraphQueryRequest(BaseModel):
    entity_name: Optional[str] = None
    entity_id: Optional[str] = None
    max_depth: int = Field(default=1, ge=1, le=3)


class EntityResult(BaseModel):
    id: str
    name: str
    type: str
    description: Optional[str] = None
    confidence: float
    relations: list["RelationResult"] = Field(default_factory=list)


class RelationResult(BaseModel):
    id: str
    relation_type: str
    source_name: str
    target_name: str
    confidence: float


class GraphQueryResponse(BaseModel):
    entity: Optional[EntityResult] = None
    neighbors: list[EntityResult] = Field(default_factory=list)
    text_tree: str = ""


# --- QA ---
class QARequest(BaseModel):
    question: str
    session_id: Optional[str] = None
    top_k: int = Field(default=20, ge=1, le=50)


class SearchResult(BaseModel):
    doc_id: str
    chunk_id: str
    content: str
    score: float
    title: str


class QAResponse(BaseModel):
    answer: str
    sources: list[SearchResult] = Field(default_factory=list)
    cached: bool = False
    session_id: Optional[str] = None


# --- Feedback ---
class FeedbackRequest(BaseModel):
    query_id: str
    rating: str  # "up" or "down"
    comment: Optional[str] = None


# --- Review ---
class ReviewDueResponse(BaseModel):
    reviews: list[dict] = Field(default_factory=list)
    count: int = 0


# --- Recap ---
class RecapRequest(BaseModel):
    period: str = "7d"  # "7d", "30d", "90d"


class RecapResponse(BaseModel):
    period: str
    new_documents: int = 0
    new_entities: int = 0
    new_relations: int = 0
    top_entities: list[str] = Field(default_factory=list)
    summary: str = ""
